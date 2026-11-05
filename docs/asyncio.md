# Asyncio path

The SDK ships blocking clients (`JanzeerClient`, `JanzeerRpc`) and matching async clients (`AsyncJanzeerClient`, `AsyncJanzeerRpc`). Method names, argument shapes, and return values are identical; the async variants simply return awaitables.

| Blocking | Async |
|---|---|
| `JanzeerClient` | `AsyncJanzeerClient` |
| `JanzeerRpc` | `AsyncJanzeerRpc` |
| `wait_for_finality` | `await_finality` |
| `send_and_wait` | `asend_and_wait` |
| `next_nonce` | `next_nonce` (returns an awaitable when given an async client) |

`JanzeerRpcWs` is already async (WebSocket subscriptions). It can be used in the same event loop as the HTTP async clients.

## Sharing an `httpx.AsyncClient`

Both async HTTP clients accept an optional `http=` argument of type `httpx.AsyncClient`. Pass the same instance to share connection pooling, timeouts, and headers:

```python
import httpx
from janzeer import AsyncJanzeerClient, AsyncJanzeerRpc

async with httpx.AsyncClient(timeout=30.0) as http:
    client = AsyncJanzeerClient(NODE, http=http)
    rpc = AsyncJanzeerRpc(RPC_URL, http=http)
    # ... use client and rpc ...
```

If you do not pass `http`, each client creates and owns its own `httpx.AsyncClient` and closes it when used as an async context manager (or when you call `aclose()`).

## Finality helpers

`await_finality(source, hash)` is the async twin of `wait_for_finality`. It accepts `AsyncJanzeerClient`, `AsyncJanzeerRpc`, or `JanzeerRpcWs`.

`asend_and_wait(via, tx)` submits and then waits for finality, again accepting either an async REST or RPC client.

See `examples/07_async_quickstart_transfer.py` for a complete end-to-end transfer on the async path, and `examples/02_subscribe_address_activity.py` / `examples/06_watch_new_blocks.py` for WebSocket usage in an asyncio loop.
