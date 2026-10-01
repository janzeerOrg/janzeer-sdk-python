"""JSON-RPC 2.0 over the node's WebSocket (``/rpc/ws``): the same methods plus live subscriptions.

Needs the ``websockets`` package (``pip install "janzeer-sdk[ws]"``). The client reconnects with exponential backoff
and re-issues every live subscription, so a handler keeps receiving events across a dropped connection.
"""

from __future__ import annotations

import asyncio
import functools
import itertools
from collections.abc import Awaitable, Callable, Sequence
from typing import Any

from . import _json
from .constants import LIMITS
from .errors import NetworkError, rpc_error_from
from .rpc import RpcMethods

Handler = Callable[[Any], Any]


def normalize_ws_url(url: str) -> str:
    """An ``http(s)://`` origin, an ``/api/v1`` base or a ``/rpc`` URL is rewritten to ``ws(s)://…/rpc/ws``."""
    u = url.strip().rstrip("/")
    if u.startswith("http:"):
        u = "ws:" + u[5:]
    elif u.startswith("https:"):
        u = "wss:" + u[6:]
    for suffix in ("/api/v1", "/rpc"):
        if u.endswith(suffix):
            u = u[: -len(suffix)]
    return u if u.endswith("/rpc/ws") else u + "/rpc/ws"


class Subscription:
    """A live subscription. ``id`` is the node's subscription id and changes after a reconnect."""

    def __init__(self, client: JanzeerRpcWs, id: str, kind: str, params: Any, handler: Handler) -> None:
        self._client, self.id, self.kind, self._params, self._handler = client, id, kind, params, handler

    async def unsubscribe(self) -> bool:
        return await self._client._unsubscribe(self)


class JanzeerRpcWs(RpcMethods):
    """``ws = await JanzeerRpcWs.connect("wss://onion.janzeer.org")``; every ``janzeer_*`` method returns an awaitable."""

    def __init__(self, url: str, *, reconnect: bool = True, reconnect_delay: float = 1.0, timeout: float = 65.0, connect_timeout: float = 10.0,
                 on_event: Callable[[dict[str, Any]], None] | None = None) -> None:
        self.url = normalize_ws_url(url)
        self._reconnect, self._delay0, self._timeout, self._connect_timeout, self._on_event = reconnect, reconnect_delay, timeout, connect_timeout, on_event
        self._ws: Any = None
        self._reader: asyncio.Task[None] | None = None
        self._pending: dict[int, asyncio.Future[Any]] = {}
        # Run when the answer of a call arrives, inside the reader, BEFORE the next message is handled. A subscription
        # is registered this way: a notification can follow its subscribe answer in the same batch of frames, and it
        # must find the subscription already known.
        self._hooks: dict[int, Callable[[Any], None]] = {}
        self._subs: dict[str, Subscription] = {}
        self._ids = itertools.count(1)
        self._closed = False
        self._open_lock = asyncio.Lock()

    @classmethod
    async def connect(cls, url: str, **options: Any) -> JanzeerRpcWs:
        """Open a socket; returns once connected."""
        c = cls(url, **options)
        await c._open()
        return c

    @property
    def connected(self) -> bool:
        return self._ws is not None

    def _emit(self, event: dict[str, Any]) -> None:
        if self._on_event:
            try:
                self._on_event(event)
            except Exception:  # a diagnostics callback must never break the client
                pass

    async def _open(self) -> None:
        async with self._open_lock:
            if self._ws is not None:
                return
            if self._closed:
                raise NetworkError("socket closed by client")
            try:
                import websockets
            except ImportError as e:  # pragma: no cover
                raise NetworkError('the WebSocket client needs the "websockets" package: pip install "janzeer-sdk[ws]"') from e
            try:
                self._ws = await asyncio.wait_for(websockets.connect(self.url, max_size=None), self._connect_timeout)
            except Exception as e:
                raise NetworkError(f"cannot open the WebSocket {self.url}: {e}") from e
            self._reader = asyncio.create_task(self._read(self._ws))
            self._emit({"type": "open"})

    async def _read(self, ws: Any) -> None:
        try:
            async for raw in ws:
                self._on_message(raw if isinstance(raw, str) else raw.decode("utf-8", "replace"))
        except Exception as e:
            self._emit({"type": "error", "error": e})
        finally:
            if self._ws is ws:
                self._ws = None
            self._fail_pending(NetworkError("socket closed"))
            will = self._reconnect and not self._closed
            self._emit({"type": "close", "will_reconnect": will})
            if will:
                asyncio.create_task(self._reconnect_loop())

    async def _reconnect_loop(self) -> None:
        delay = self._delay0
        while not self._closed and self._ws is None:
            await asyncio.sleep(delay)
            delay = min(delay * 2, 30.0)
            try:
                await self._open()
            except NetworkError:
                continue
            await self._resubscribe()

    async def _resubscribe(self) -> None:
        old = list(self._subs.values())
        self._subs.clear()
        count = 0
        for s in old:
            try:
                await self.call("janzeer_subscribe", {"kind": s.kind, "params": s._params}, _hook=functools.partial(self._register, s))
                count += 1
            except Exception as e:
                self._emit({"type": "error", "error": e})
        if count:
            self._emit({"type": "resubscribed", "count": count})

    def _on_message(self, text: str) -> None:
        try:
            msg = _json.loads(text)
        except ValueError:
            return
        for m in msg if isinstance(msg, list) else [msg]:
            if not isinstance(m, dict):
                continue
            if m.get("method") == "janzeer_subscription" and isinstance(m.get("params"), dict):
                p = m["params"]
                sub = self._subs.get(str(p.get("subscription")))
                if sub is not None and "result" in p:
                    try:
                        out = sub._handler(p["result"])
                        if asyncio.iscoroutine(out):
                            asyncio.create_task(out)
                    except Exception as e:
                        self._emit({"type": "error", "error": e})
                continue
            mid = m.get("id")
            fut = self._pending.pop(mid, None) if isinstance(mid, int) else None
            hook = self._hooks.pop(mid, None) if isinstance(mid, int) else None
            if hook is not None and not m.get("error"):
                hook(m.get("result"))
            if fut is None or fut.done():
                continue
            if m.get("error"):
                fut.set_exception(rpc_error_from(m["error"], "ws"))
            else:
                fut.set_result(m.get("result"))

    def _fail_pending(self, err: Exception) -> None:
        for fut in self._pending.values():
            if not fut.done():
                fut.set_exception(err)
        self._pending.clear()
        self._hooks.clear()

    async def call(self, method: str, params: Any = None, *, then: Callable[[Any], Any] | None = None, _hook: Callable[[Any], None] | None = None) -> Any:
        if self._ws is None:
            await self._open()
        id_ = next(self._ids)
        req: dict[str, Any] = {"jsonrpc": "2.0", "id": id_, "method": method}
        if params is not None:
            req["params"] = params
        fut: asyncio.Future[Any] = asyncio.get_running_loop().create_future()
        self._pending[id_] = fut
        if _hook is not None:
            self._hooks[id_] = _hook
        try:
            await self._ws.send(_json.dumps(req))
            out = await asyncio.wait_for(fut, self._timeout)
        except asyncio.TimeoutError as e:
            raise NetworkError(f"RPC {method} timed out after {self._timeout} s") from e
        except NetworkError:
            raise
        except Exception as e:
            if isinstance(e, Exception) and e.__class__.__module__.startswith("janzeer"):
                raise
            raise NetworkError(f"send failed: {e}") from e
        finally:
            self._pending.pop(id_, None)
            self._hooks.pop(id_, None)
        return then(out) if then else out

    async def _subscribe(self, kind: str, params: Any, handler: Handler) -> Subscription:
        if len(self._subs) >= LIMITS["subscriptions_per_session"]:
            raise ValueError(f"at most {LIMITS['subscriptions_per_session']} subscriptions per session")
        sub = Subscription(self, "", kind, params, handler)
        await self.call("janzeer_subscribe", {"kind": kind, "params": params}, _hook=functools.partial(self._register, sub))
        return sub

    def _register(self, sub: Subscription, result: Any) -> None:
        sub.id = str(result)
        self._subs[sub.id] = sub

    async def _unsubscribe(self, sub: Subscription) -> bool:
        self._subs.pop(sub.id, None)
        if self._ws is None:
            return True
        try:
            return bool(await self.call("janzeer_unsubscribe", {"subscription": sub.id}))
        except Exception:
            return False

    def subscribe_new_blocks(self, handler: Handler, *, from_height: int | None = None, include_transactions: bool = False) -> Awaitable[Subscription]:
        """Stream committed blocks (optionally replaying from ``from_height``). ``handler(block)`` may be sync or async."""
        params: dict[str, Any] = {"includeTransactions": include_transactions}
        if from_height is not None:
            params["fromHeight"] = from_height
        return self._subscribe("newBlocks", params, handler)

    def subscribe_address_activity(self, addresses: Sequence[str], handler: Handler) -> Awaitable[Subscription]:
        """``handler({blockHeight, blockHash, transaction})`` when a FINAL transaction involves any of ``addresses``."""
        if not 1 <= len(addresses) <= LIMITS["watched_addresses"]:
            raise ValueError(f"1-{LIMITS['watched_addresses']} addresses")
        return self._subscribe("addressActivity", {"addresses": [a.lower() for a in addresses]}, handler)

    async def close(self) -> None:
        """Close the socket; no reconnect. Pending calls fail, subscriptions are dropped."""
        self._closed = True
        self._subs.clear()
        ws, self._ws = self._ws, None
        if ws is not None:
            await ws.close()
        self._fail_pending(NetworkError("socket closed by client"))

    async def __aenter__(self) -> JanzeerRpcWs:
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.close()
