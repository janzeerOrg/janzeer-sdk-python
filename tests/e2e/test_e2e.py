"""The conformance flow (sdk_conformance/e2e/SPEC.md) against a running network.

Skipped unless JANZEER_NODE_URL is set: start the local 4-anchor net with ``sdk_conformance/e2e/node-up.sh`` and
``eval "$(… --env)"``, then ``pytest -m e2e``.
"""

import asyncio
import os
import re
import time

import pytest

from janzeer import (
    SPEC_VERSION,
    Account,
    JanzeerClient,
    JanzeerRpc,
    JanzeerRpcWs,
    NonceMismatchError,
    RpcInvalidParamsError,
    TxBuilder,
    TxRejectedError,
    await_finality,
    sub_amounts,
)

NODE_URL = os.environ.get("JANZEER_NODE_URL")
RPC_URL = os.environ.get("JANZEER_RPC_URL") or NODE_URL
WS_URL = os.environ.get("JANZEER_WS_URL") or NODE_URL
MNEMONIC = os.environ.get("JANZEER_E2E_MNEMONIC", "abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon about")
RECIPIENT = os.environ.get("JANZEER_E2E_RECIPIENT", "0x598b1301acef3baba6ce25e38dd17b723f7b98b1")

pytestmark = [pytest.mark.e2e, pytest.mark.skipif(not NODE_URL, reason="JANZEER_NODE_URL is not set")]


async def test_all_14_steps():
    client, rpc = JanzeerClient(NODE_URL), JanzeerRpc(RPC_URL)

    # 1 derive
    acct = Account.from_mnemonic(MNEMONIC)
    assert acct.address == "0x06e1c0fa9955a700876f8cb0acc7f13fba9fb8ba"

    # 2 version + network gate: every tx below is built for the node's own network id
    info = client.info()
    assert info["version"] == SPEC_VERSION["node"]
    assert client.last_envelope["version"] == SPEC_VERSION["api"]
    network_id = info["networkId"]
    if os.environ.get("JANZEER_NETWORK_ID"):
        assert network_id == os.environ["JANZEER_NETWORK_ID"]
    assert re.fullmatch(r"[0-9a-f]{64}", info["genesisHash"])

    # 3 account
    a0 = rpc.get_account(acct.address)
    assert a0["balance"] > 0
    nonce = a0["nextNonce"]
    balance0 = format(a0["balance"], "f") if not isinstance(a0["balance"], (int, str)) else str(a0["balance"])

    # 4 subscribe first (on ANOTHER node than the one the tx is sent to: proves gossip)
    ws = await JanzeerRpcWs.connect(WS_URL)
    seen = []
    sub = await ws.subscribe_address_activity([RECIPIENT], seen.append)
    assert re.fullmatch(r"[0-9a-f]{16}", sub.id)

    # 5 build + sign
    tx = acct.sign_tx(TxBuilder.transfer(sender=acct.address, to=RECIPIENT, amount="1.25", fee="0.01", data="sdk-e2e-python", nonce=nonce, network_id=network_id))
    assert acct.verify(tx.hash, tx.signature)

    # 6 REST submit (201)
    assert client.submit(tx)["hash"] == tx.hash

    # 7 RPC resubmit is idempotent
    assert rpc.send(tx) == {"hash": tx.hash, "status": "PENDING"}
    assert rpc.get_account(acct.address)["pendingCount"] <= 1

    # 8 status
    assert rpc.get_transaction_by_hash(tx.hash)["status"] in ("PENDING", "FINAL")

    # 9 finality, via the WebSocket transport
    fin = await await_finality(ws, tx.hash, timeout=120)
    assert fin["status"] == "FINAL" and fin["blockHeight"] > 0 and fin["receipt"]["successful"] is True

    # 10 exact balance (decimal strings, never floats)
    expected = sub_amounts(sub_amounts(balance0, "1.25"), "0.01")
    assert sub_amounts(client.balance(acct.address), "0") == expected

    # 11 notification
    deadline = time.monotonic() + 60
    while not any(e["transaction"]["hash"] == tx.hash for e in seen) and time.monotonic() < deadline:
        await asyncio.sleep(0.25)
    hit = next((e for e in seen if e["transaction"]["hash"] == tx.hash), None)
    assert hit is not None and hit["blockHeight"] == fin["blockHeight"]
    assert await sub.unsubscribe() is True
    await ws.close()

    # 12 nonce gap -> NonceMismatchError (REST and RPC)
    gap = acct.sign_tx(TxBuilder.transfer(sender=acct.address, to=RECIPIENT, amount="1", nonce=nonce + 10, network_id=network_id))
    with pytest.raises(NonceMismatchError) as e_rest:
        client.submit(gap)
    assert e_rest.value.type == "INVALID_NONCE" and e_rest.value.got == nonce + 10
    with pytest.raises(NonceMismatchError) as e_rpc:
        rpc.send(gap)
    assert e_rpc.value.rpc_code == -32001

    # 13 bad signature -> TxRejectedError INCORRECT_SIGNATURE
    nxt = client.nonce(acct.address)
    good = acct.sign_tx(TxBuilder.transfer(sender=acct.address, to=RECIPIENT, amount="1", nonce=nxt, network_id=network_id))
    forged = TxBuilder.transfer(sender=acct.address, to=RECIPIENT, amount="2", nonce=nxt, network_id=network_id).with_signature(good.signature, acct.public_key_hex)
    with pytest.raises(TxRejectedError) as e_sig:
        client.submit(forged)
    assert e_sig.value.type == "INCORRECT_SIGNATURE"

    # 14 bad address -> -32602
    with pytest.raises(RpcInvalidParamsError):
        rpc.get_balance("0x12")
    client.close()
    rpc.close()
