"""JSON-RPC 2.0 over HTTP (``POST /rpc``): :class:`JanzeerRpc` (blocking) and :class:`AsyncJanzeerRpc`.

One typed method per ``janzeer_*`` method of the node. The same method list is shared by the WebSocket client
(:class:`janzeer.JanzeerRpcWs`). Results are plain JSON values; amounts are ``Decimal`` or decimal strings, never floats.
"""

from __future__ import annotations

import asyncio
import itertools
import time
from collections.abc import Callable, Mapping, Sequence
from typing import Any

import httpx

from . import _json
from .errors import JanzeerError, NetworkError, RateLimitedError, RpcError, rpc_error_from
from .tx import SignedTx


def normalize_rpc_url(url: str) -> str:
    """A bare origin or an ``/api/v1`` base is rewritten to ``…/rpc``."""
    u = url.strip().rstrip("/")
    if u.endswith("/api/v1"):
        u = u[: -len("/api/v1")]
    return u if u.endswith("/rpc") else u + "/rpc"


def _clean(params: Mapping[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in params.items() if v is not None}


class RpcMethods:
    """The ``janzeer_*`` methods. ``call`` is the transport: blocking in :class:`JanzeerRpc`, awaitable in the async clients."""

    def call(self, method: str, params: Any = None, *, then: Callable[[Any], Any] | None = None) -> Any:
        """Raw call: ``params`` by name (dict) or by position (list). Raises the mapped SDK error on a JSON-RPC error."""
        raise NotImplementedError

    # -- node --------------------------------------------------------------------------------------------------------
    def methods(self) -> Any:
        return self.call("janzeer_methods")

    def get_info(self) -> Any:
        return self.call("janzeer_getInfo")

    def get_chain_spec(self) -> Any:
        return self.call("janzeer_getChainSpec")

    def get_genesis(self) -> Any:
        return self.call("janzeer_getGenesis")

    def get_stats(self) -> Any:
        return self.call("janzeer_getStats")

    def get_epoch(self) -> Any:
        return self.call("janzeer_getEpoch")

    # -- accounts ----------------------------------------------------------------------------------------------------
    def get_account(self, address: str) -> Any:
        """``{address, balance, nonce, nextNonce, pendingCount, …}``."""
        return self.call("janzeer_getAccount", {"address": address})

    def get_balance(self, address: str) -> Any:
        """Spendable balance as a decimal string."""
        return self.call("janzeer_getBalance", {"address": address}, then=_json.decimal_str)

    def get_nonce(self, address: str) -> Any:
        """Next nonce (committed + pending)."""
        return self.call("janzeer_getNonce", {"address": address}, then=int)

    def get_token_balances(self, address: str, *, page: int | None = None, size: int | None = None) -> Any:
        return self.call("janzeer_getTokenBalances", _clean({"address": address, "page": page, "size": size}))

    def get_transactions_by_address(self, address: str, *, page: int | None = None, size: int | None = None) -> Any:
        return self.call("janzeer_getTransactionsByAddress", _clean({"address": address, "page": page, "size": size}))

    # -- sending -----------------------------------------------------------------------------------------------------
    def send(self, tx: SignedTx) -> Any:
        """Submit a signed transaction through its type's ``janzeer_send*`` method -> ``{hash, status}``."""
        return self.call(tx.rpc_method, tx.to_body())

    def send_raw_transaction(self, type: str, tx: Mapping[str, Any]) -> Any:
        return self.call("janzeer_sendRawTransaction", {"type": type, "tx": dict(tx)})

    # -- transactions ------------------------------------------------------------------------------------------------
    def get_transaction_by_hash(self, hash: str) -> Any:
        """Unified view of any transaction; ``status`` is ``UNKNOWN`` when the node has never seen the hash."""
        return self.call("janzeer_getTransactionByHash", {"hash": hash})

    def wait_for_finality(self, hash: str, timeout_ms: int = 30_000) -> Any:
        """Server-side wait (at most 60,000 ms per call). Prefer the ``janzeer.wait_for_finality`` helper."""
        return self.call("janzeer_waitForFinality", {"hash": hash, "timeoutMs": timeout_ms})

    def estimate_fee(self, kind: str) -> Any:
        return self.call("janzeer_estimateFee", {"kind": kind})

    # -- blocks ------------------------------------------------------------------------------------------------------
    def get_tip(self) -> Any:
        return self.call("janzeer_getTip")

    def get_block_by_number(self, height: int, include_transactions: bool = False) -> Any:
        return self.call("janzeer_getBlockByNumber", {"height": height, "includeTransactions": include_transactions})

    def get_block_by_hash(self, hash: str, include_transactions: bool = False) -> Any:
        return self.call("janzeer_getBlockByHash", {"hash": hash, "includeTransactions": include_transactions})

    def get_blocks(self, from_height: int, to_height: int, include_transactions: bool = False) -> Any:
        """Ascending, at most 100 blocks per call."""
        return self.call("janzeer_getBlocks", {"fromHeight": from_height, "toHeight": to_height, "includeTransactions": include_transactions})

    # -- tokens / validators -----------------------------------------------------------------------------------------
    def get_token(self, token_id: str) -> Any:
        return self.call("janzeer_getToken", {"tokenId": token_id})

    def list_tokens(self, *, page: int | None = None, size: int | None = None) -> Any:
        return self.call("janzeer_listTokens", _clean({"page": page, "size": size}))

    def get_token_holders(self, token_id: str, *, page: int | None = None, size: int | None = None) -> Any:
        return self.call("janzeer_getTokenHolders", _clean({"tokenId": token_id, "page": page, "size": size}))

    def list_validators(self, *, page: int | None = None, size: int | None = None) -> Any:
        return self.call("janzeer_listValidators", _clean({"page": page, "size": size}))

    def get_active_validators(self) -> Any:
        return self.call("janzeer_getActiveValidators")

    def get_validator(self, key: str) -> Any:
        return self.call("janzeer_getValidator", {"key": key})


class _HttpRpcBase(RpcMethods):
    def __init__(self, url: str, *, timeout: float = 65.0, headers: Mapping[str, str] | None = None, retry_on_rate_limit: bool = True) -> None:
        self.url = normalize_rpc_url(url)
        self._timeout = timeout
        self._headers = {"Content-Type": "application/json", "Accept": "application/json", **(headers or {})}
        self._retry_429 = retry_on_rate_limit
        self._ids = itertools.count(1)

    def _envelope(self, method: str, params: Any) -> dict[str, Any]:
        req: dict[str, Any] = {"jsonrpc": "2.0", "id": next(self._ids), "method": method}
        if params is not None:
            req["params"] = params
        return req

    @staticmethod
    def _decode(res: httpx.Response) -> Any:
        if res.status_code == 429:
            try:
                seconds = float(res.headers.get("Retry-After", "1"))
            except ValueError:
                seconds = 1.0
            raise RateLimitedError("Rate limit exceeded", seconds, "rpc")
        if res.status_code == 204 or not res.content:
            return None
        try:
            return _json.loads(res.content)
        except ValueError as e:
            raise NetworkError(f"node returned non-JSON ({res.status_code})") from e

    @staticmethod
    def _result(body: Any, then: Callable[[Any], Any] | None) -> Any:
        if not isinstance(body, dict):
            raise NetworkError("malformed JSON-RPC response")
        if body.get("error"):
            raise rpc_error_from(body["error"])
        out = body.get("result")
        return then(out) if then else out

    @staticmethod
    def _batch_results(body: Any, ids: Sequence[int]) -> list[Any]:
        if not isinstance(body, list):  # a batch-level error (e.g. "Batch too large") comes back as one object
            raise rpc_error_from(body["error"]) if isinstance(body, dict) and body.get("error") else NetworkError("malformed JSON-RPC batch response")
        by_id = {item.get("id"): item for item in body if isinstance(item, dict)}
        out: list[Any] = []
        for i in ids:
            r = by_id.get(i)
            if r is None:
                out.append(RpcError(-32603, "missing batch response"))
            elif r.get("error"):
                out.append(rpc_error_from(r["error"]))
            else:
                out.append(r.get("result"))
        return out


class JanzeerRpc(_HttpRpcBase):
    """Blocking JSON-RPC client. ``JanzeerRpc("https://onion.janzeer.org")``."""

    def __init__(self, url: str, *, timeout: float = 65.0, headers: Mapping[str, str] | None = None, retry_on_rate_limit: bool = True,
                 http: httpx.Client | None = None) -> None:
        super().__init__(url, timeout=timeout, headers=headers, retry_on_rate_limit=retry_on_rate_limit)
        self._http = http or httpx.Client(timeout=timeout, follow_redirects=True)

    def _post(self, payload: Any) -> Any:
        for attempt in (0, 1):
            try:
                res = self._http.post(self.url, content=_json.dumps(payload).encode("utf-8"), headers=self._headers)
            except httpx.HTTPError as e:
                raise NetworkError(f"cannot reach the node at {self.url}: {e}") from e
            try:
                return self._decode(res)
            except RateLimitedError as e:
                if self._retry_429 and attempt == 0:
                    time.sleep(e.retry_after)
                    continue
                raise
        raise JanzeerError("unreachable")  # pragma: no cover

    def call(self, method: str, params: Any = None, *, then: Callable[[Any], Any] | None = None) -> Any:
        return self._result(self._post(self._envelope(method, params)), then)

    def batch(self, requests: Sequence[tuple[str, Any]]) -> list[Any]:
        """Several ``(method, params)`` in one round trip (node cap: 50). Each entry is the result or an error INSTANCE."""
        if not requests:
            return []
        envs = [self._envelope(m, p) for m, p in requests]
        return self._batch_results(self._post(envs), [e["id"] for e in envs])

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> JanzeerRpc:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


class AsyncJanzeerRpc(_HttpRpcBase):
    """Async JSON-RPC client: the same methods, each returning an awaitable."""

    def __init__(self, url: str, *, timeout: float = 65.0, headers: Mapping[str, str] | None = None, retry_on_rate_limit: bool = True,
                 http: httpx.AsyncClient | None = None) -> None:
        super().__init__(url, timeout=timeout, headers=headers, retry_on_rate_limit=retry_on_rate_limit)
        self._http = http or httpx.AsyncClient(timeout=timeout, follow_redirects=True)

    async def _post(self, payload: Any) -> Any:
        for attempt in (0, 1):
            try:
                res = await self._http.post(self.url, content=_json.dumps(payload).encode("utf-8"), headers=self._headers)
            except httpx.HTTPError as e:
                raise NetworkError(f"cannot reach the node at {self.url}: {e}") from e
            try:
                return self._decode(res)
            except RateLimitedError as e:
                if self._retry_429 and attempt == 0:
                    await asyncio.sleep(e.retry_after)
                    continue
                raise
        raise JanzeerError("unreachable")  # pragma: no cover

    async def call(self, method: str, params: Any = None, *, then: Callable[[Any], Any] | None = None) -> Any:
        return self._result(await self._post(self._envelope(method, params)), then)

    async def batch(self, requests: Sequence[tuple[str, Any]]) -> list[Any]:
        if not requests:
            return []
        envs = [self._envelope(m, p) for m, p in requests]
        return self._batch_results(await self._post(envs), [e["id"] for e in envs])

    async def aclose(self) -> None:
        await self._http.aclose()

    async def __aenter__(self) -> AsyncJanzeerRpc:
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.aclose()
