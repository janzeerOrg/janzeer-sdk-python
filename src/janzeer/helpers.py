"""High-level flows composed from the clients: next nonce, wait for finality, send and wait.

Blocking versions take :class:`JanzeerRpc` or :class:`JanzeerClient`; the ``a``-prefixed versions take the async
clients (:class:`AsyncJanzeerRpc`, :class:`JanzeerRpcWs`, :class:`AsyncJanzeerClient`).
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

from .constants import LIMITS
from .errors import FinalityTimeoutError, NetworkError, RpcNotFoundError
from .rest import AsyncJanzeerClient, JanzeerClient, _RestBase
from .rpc import RpcMethods
from .tx import SignedTx

_REST_COLLECTIONS = ("transfers", "token_txs", "validator_txs", "exit_validator_txs")


def _rest_view(t: Any) -> dict[str, Any] | None:
    if t is None:
        return None
    return {**t, "status": "FINAL" if t.get("blockHash") else "PENDING"}


def _slice_ms(deadline: float) -> int:
    return int(max(1000, min(LIMITS["wait_for_finality_ms"], (deadline - time.monotonic()) * 1000)))


def next_nonce(source: Any, address: str) -> Any:
    """The sender's next nonce from either transport (awaitable when the client is async)."""
    return source.nonce(address) if isinstance(source, _RestBase) else source.get_nonce(address)


def wait_for_finality(source: JanzeerClient | RpcMethods, hash: str, *, timeout: float = 180.0, poll: float = 1.5) -> dict[str, Any]:
    """Block until ``hash`` is in a committed block and return its FINAL view.

    With a JSON-RPC client it uses the node's long-poll ``janzeer_waitForFinality`` in slices of at most 60 s; with a
    REST client it polls the transaction endpoints. Raises :class:`FinalityTimeoutError` at the deadline.
    """
    deadline = time.monotonic() + timeout
    last: dict[str, Any] | None = None
    while time.monotonic() < deadline:
        if isinstance(source, JanzeerClient):
            for name in _REST_COLLECTIONS:
                last = _rest_view(getattr(source, name).get(hash))
                if last:
                    break
            if last and last["status"] == "FINAL":
                return last
            time.sleep(poll)
            continue
        try:
            last = source.wait_for_finality(hash, _slice_ms(deadline))
        except RpcNotFoundError:
            last = None
        except NetworkError:
            time.sleep(1.0)
            continue
        if last and last.get("status") == "FINAL":
            return last
    raise FinalityTimeoutError(hash, last)


async def await_finality(source: AsyncJanzeerClient | RpcMethods, hash: str, *, timeout: float = 180.0, poll: float = 1.5) -> dict[str, Any]:
    """Async twin of :func:`wait_for_finality` for :class:`AsyncJanzeerRpc`, :class:`JanzeerRpcWs` and :class:`AsyncJanzeerClient`."""
    deadline = time.monotonic() + timeout
    last: dict[str, Any] | None = None
    while time.monotonic() < deadline:
        if isinstance(source, AsyncJanzeerClient):
            for name in _REST_COLLECTIONS:
                last = _rest_view(await getattr(source, name).get(hash))
                if last:
                    break
            if last and last["status"] == "FINAL":
                return last
            await asyncio.sleep(poll)
            continue
        try:
            last = await source.wait_for_finality(hash, _slice_ms(deadline))
        except RpcNotFoundError:
            last = None
        except NetworkError:
            await asyncio.sleep(1.0)
            continue
        if last and last.get("status") == "FINAL":
            return last
    raise FinalityTimeoutError(hash, last)


def send_and_wait(via: JanzeerClient | RpcMethods, tx: SignedTx, *, timeout: float = 180.0) -> dict[str, Any]:
    """Submit a signed transaction and block until it is final."""
    if isinstance(via, JanzeerClient):
        via.submit(tx)
    else:
        via.send(tx)
    return wait_for_finality(via, tx.hash, timeout=timeout)


async def asend_and_wait(via: AsyncJanzeerClient | RpcMethods, tx: SignedTx, *, timeout: float = 180.0) -> dict[str, Any]:
    """Async twin of :func:`send_and_wait`."""
    if isinstance(via, AsyncJanzeerClient):
        await via.submit(tx)
    else:
        await via.send(tx)
    return await await_finality(via, tx.hash, timeout=timeout)
