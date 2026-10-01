"""REST and JSON-RPC clients against a mocked transport: URL rules, envelope handling, error mapping, lossless numbers."""

import json
from decimal import Decimal

import httpx
import pytest

from janzeer import (
    Account,
    ApiError,
    AsyncJanzeerClient,
    AsyncJanzeerRpc,
    JanzeerClient,
    JanzeerRpc,
    NetworkError,
    NonceMismatchError,
    NotFoundError,
    NotSynchronizedError,
    RateLimitedError,
    RpcInvalidParamsError,
    RpcNotFoundError,
    TxBuilder,
    TxRejectedError,
    ValidationError,
    wait_for_finality,
)
from janzeer.rest import normalize_rest_url
from janzeer.rpc import normalize_rpc_url
from janzeer.ws import normalize_ws_url

ADDR = "0x74d2bedc03ae5deb6fc63fbf7bb87e86f034b274"


def env(payload):
    return {"timestamp": 1, "version": "1.1.0", "payload": payload}


def rest(handler):
    return JanzeerClient("http://node:7019", http=httpx.Client(transport=httpx.MockTransport(handler)))


def rpc(handler):
    return JanzeerRpc("http://node:7019", http=httpx.Client(transport=httpx.MockTransport(handler)))


def test_url_rules():
    assert normalize_rest_url("http://h:7019") == normalize_rest_url("http://h:7019/api/v1/") == "http://h:7019/api/v1/"
    assert normalize_rpc_url("http://h:7019/api/v1/") == normalize_rpc_url("http://h:7019") == "http://h:7019/rpc"
    assert normalize_ws_url("https://h/api/v1") == normalize_ws_url("wss://h/rpc") == "wss://h/rpc/ws"


def test_envelope_and_lossless_numbers():
    seen = []

    def handler(req: httpx.Request) -> httpx.Response:
        seen.append(str(req.url))
        if req.url.path.endswith("/nonce"):
            return httpx.Response(200, json=env(7))
        if "/wallets/" in req.url.path:
            return httpx.Response(200, content=b'{"timestamp":1,"version":"1.1.0","payload":77499900.00200001}')
        return httpx.Response(200, content=b'{"timestamp":1,"version":"1.1.0","payload":{"total":1,"list":[{"amount":0.10000000,"fee":1E-2}]}}')

    c = rest(handler)
    assert c.balance(ADDR) == "77499900.00200001"           # a float would have printed 77499900.00200002
    assert c.nonce(ADDR) == 7 and c.last_envelope["version"] == "1.1.0"
    page = c.transfers.list(address=ADDR, size=5, unconfirmed=True)
    assert page["list"][0]["amount"] == Decimal("0.10000000") and isinstance(page["list"][0]["fee"], Decimal)
    assert "address=" + ADDR in seen[-1] and "size=5" in seen[-1] and "unconfirmed=true" in seen[-1]
    with pytest.raises(TypeError):
        c.transfers.list(token_id="x")


def test_404_defaults():
    c = rest(lambda r: httpx.Response(404, json=env({"status": 404, "message": "not found"})))
    assert c.balance(ADDR) == "0" and c.nonce(ADDR) == 0 and c.transfers.get("ab") is None and c.receipt("ab") is None
    with pytest.raises(NotFoundError):
        c.info()


@pytest.mark.parametrize(
    "status,body,exc,check",
    [
        (400, env({"status": 400, "message": f"Invalid nonce for {ADDR}: expected 3, got 13", "type": "INVALID_NONCE"}), NonceMismatchError, lambda e: (e.expected, e.got, e.http_status) == (3, 13, 400)),
        (400, env({"status": 400, "message": "Incorrect signature", "type": "INCORRECT_SIGNATURE"}), TxRejectedError, lambda e: e.type == "INCORRECT_SIGNATURE" and e.transport == "rest"),
        (400, env([{"message": "amount: must not be null"}, {"message": "fee: too small"}]), ValidationError, lambda e: e.messages == ["amount: must not be null", "fee: too small"]),
        (400, env({"status": 400, "message": "Blockchain is synchronizing"}), NotSynchronizedError, lambda e: True),
        (500, env({"status": 500, "message": "boom"}), ApiError, lambda e: e.status == 500),
        (413, {"status": 413, "message": "too large"}, ApiError, lambda e: e.status == 413),   # flat body: no envelope
    ],
)
def test_rest_error_mapping(status, body, exc, check):
    tx = Account.random()
    signed = tx.sign_tx(TxBuilder.transfer(sender=tx.address, to=ADDR, amount="1", nonce=0))
    with pytest.raises(exc) as e:
        rest(lambda r: httpx.Response(status, json=body)).submit(signed)
    assert type(e.value) is exc and check(e.value)


def test_rate_limit_retries_once():
    calls = []

    def handler(req):
        calls.append(1)
        return httpx.Response(429, headers={"Retry-After": "0"}, json={"status": 429, "message": "slow down"}) if len(calls) == 1 else httpx.Response(200, json=env(5))

    assert rest(handler).nonce(ADDR) == 5 and len(calls) == 2
    c = JanzeerClient("http://n", retry_on_rate_limit=False, http=httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(429, headers={"Retry-After": "2"}, json={"message": "x"}))))
    with pytest.raises(RateLimitedError) as e:
        c.nonce(ADDR)
    assert e.value.retry_after == 2.0


def test_network_errors():
    def boom(req):
        raise httpx.ConnectError("refused")

    with pytest.raises(NetworkError):
        rest(boom).info()
    with pytest.raises(NetworkError):
        rest(lambda r: httpx.Response(200, content=b"<html>")).info()


def test_request_bodies_never_carry_floats():
    captured = {}

    def handler(req):
        captured["body"] = json.loads(req.content)
        return httpx.Response(201, json=env({"hash": captured["body"]["hash"]}))

    acct = Account.random()
    tx = acct.sign_tx(TxBuilder.transfer(sender=acct.address, to=ADDR, amount="1.25", nonce=4, timestamp=1700000000000))
    assert rest(handler).submit(tx)["hash"] == tx.hash
    b = captured["body"]
    assert b["amount"] == "1.25" and b["fee"] == "0.01" and b["nonce"] == 4 and "data" not in b
    with pytest.raises(TypeError):
        rest(handler).post("x", {"amount": 0.1})


def test_rpc_calls_errors_and_batches():
    def handler(req):
        body = json.loads(req.content)
        if isinstance(body, list):
            return httpx.Response(200, json=[{"jsonrpc": "2.0", "id": b["id"], "result": b["id"]} if b["method"] != "bad" else {"jsonrpc": "2.0", "id": b["id"], "error": {"code": -32000, "message": "nope"}} for b in reversed(body)])
        m = body["method"]
        if m == "janzeer_getBalance":
            return httpx.Response(200, content=f'{{"jsonrpc":"2.0","id":{body["id"]},"result":12.50000000}}'.encode())
        if m == "janzeer_getNonce":
            assert body["params"] == {"address": ADDR}
            return httpx.Response(200, json={"jsonrpc": "2.0", "id": body["id"], "result": 9})
        if m == "janzeer_sendTransfer":
            return httpx.Response(200, json={"jsonrpc": "2.0", "id": body["id"], "error": {"code": -32001, "message": f"Invalid nonce for {ADDR}: expected 1, got 11", "data": {"type": "INVALID_NONCE"}}})
        if m == "janzeer_getToken":
            return httpx.Response(200, json={"jsonrpc": "2.0", "id": body["id"], "error": {"code": -32000, "message": "token not found"}})
        return httpx.Response(200, json={"jsonrpc": "2.0", "id": body["id"], "error": {"code": -32602, "message": "bad address", "data": ["address"]}})

    r = rpc(handler)
    assert r.get_balance(ADDR) == "12.50000000" and r.get_nonce(ADDR) == 9
    with pytest.raises(RpcInvalidParamsError) as e:
        r.get_account("0x12")
    assert e.value.code == -32602 and e.value.data == ["address"]
    with pytest.raises(RpcNotFoundError):
        r.get_token("ab")
    acct = Account.random()
    with pytest.raises(NonceMismatchError) as n:
        r.send(acct.sign_tx(TxBuilder.transfer(sender=acct.address, to=ADDR, amount="1", nonce=11)))
    assert n.value.rpc_code == -32001 and n.value.transport == "rpc" and n.value.expected == 1
    out = r.batch([("a", None), ("bad", None), ("c", {"x": 1})])
    assert isinstance(out[0], int) and isinstance(out[1], RpcNotFoundError) and isinstance(out[2], int) and out[0] != out[2]


def test_wait_for_finality_over_rest_and_rpc():
    states = iter([None, {"hash": "ab", "blockHash": None}, {"hash": "ab", "blockHash": "cd"}])

    def rest_handler(req):
        if req.url.path.endswith("/transactions/transfers/ab"):
            s = next(states)
            return httpx.Response(404, json=env({"message": "x"})) if s is None else httpx.Response(200, json=env(s))
        return httpx.Response(404, json=env({"message": "x"}))

    assert wait_for_finality(rest(rest_handler), "ab", timeout=10, poll=0.01)["status"] == "FINAL"

    views = iter([{"hash": "ab", "status": "PENDING", "timedOut": True}, {"hash": "ab", "status": "FINAL", "blockHeight": 5}])
    r = rpc(lambda req: httpx.Response(200, json={"jsonrpc": "2.0", "id": json.loads(req.content)["id"], "result": next(views)}))
    assert wait_for_finality(r, "ab", timeout=10)["blockHeight"] == 5


async def test_async_clients_share_the_method_list():
    async def handler(req):
        if req.url.path.endswith("/rpc"):
            return httpx.Response(200, json={"jsonrpc": "2.0", "id": json.loads(req.content)["id"], "result": {"height": 3}})
        return httpx.Response(200, json=env(42))

    async with AsyncJanzeerClient("http://n", http=httpx.AsyncClient(transport=httpx.MockTransport(handler))) as c:
        assert await c.nonce(ADDR) == 42 and await c.balance(ADDR) == "42"
    async with AsyncJanzeerRpc("http://n", http=httpx.AsyncClient(transport=httpx.MockTransport(handler))) as r:
        assert (await r.get_tip())["height"] == 3
