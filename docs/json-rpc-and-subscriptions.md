# JSON-RPC and subscriptions

The node serves JSON-RPC 2.0 at `POST /rpc` and over WebSocket at `/rpc/ws` (the same methods, plus subscriptions).
`JanzeerRpc`, `AsyncJanzeerRpc` and `JanzeerRpcWs` expose **one method per `janzeer_*` method**; `call()` sends
anything else.

```python
rpc = JanzeerRpc("https://onion.janzeer.org")                 # '/rpc' appended automatically
rpc.get_info(); rpc.get_chain_spec(); rpc.get_stats(); rpc.get_epoch(); rpc.get_genesis()
rpc.get_account(addr); rpc.get_balance(addr); rpc.get_nonce(addr)
rpc.get_transactions_by_address(addr, size=20)               # {list, pending, total…}
rpc.get_transaction_by_hash(hash)                            # status FINAL | PENDING | UNKNOWN
rpc.get_tip(); rpc.get_block_by_number(12, True); rpc.get_blocks(1, 100)
rpc.list_validators(); rpc.get_active_validators(); rpc.get_validator(key)
rpc.list_tokens(); rpc.get_token(token_id); rpc.get_token_holders(token_id)
rpc.estimate_fee("transfer")                                 # {fee, rule: 'minimum' | 'exact'}
rpc.send(signed_tx)
rpc.call("janzeer_methods")                                  # raw
```

## Batches

```python
nonce, tip = rpc.batch([("janzeer_getNonce", {"address": addr}), ("janzeer_getTip", None)])
```

Up to 50 requests per batch, 512 KiB per body. Results keep the request order. One failing entry does not raise: its
slot holds the error **instance** (`isinstance(x, JanzeerError)`), the others hold their results.

## Finality

`rpc.wait_for_finality(hash, timeout_ms)` is the node's long-poll (at most 60 s per call). The helper
`wait_for_finality(rpc_or_client, hash, timeout=180)` chains calls until a client-side deadline, tolerates a dropped
connection, and raises `FinalityTimeoutError` (with the last view) on expiry. Given a REST client it polls the
transaction endpoints. `await_finality` is the async twin and also accepts a `JanzeerRpcWs`.

A `FINAL` view carries `blockHash`, `blockHeight` and `receipt["successful"]`. The chain has instant finality (2f+1
BFT commit), so no confirmation counting exists anywhere in the API.

## WebSocket

Install the extra: `pip install "janzeer-sdk[ws]"`.

```python
ws = await JanzeerRpcWs.connect("wss://onion.janzeer.org")         # http(s) URLs are converted
await ws.get_tip()                                                 # every method works over the socket

blocks = await ws.subscribe_new_blocks(print, from_height=100, include_transactions=True)
watch  = await ws.subscribe_address_activity([addr1, addr2], lambda ev: print(ev["blockHeight"], ev["transaction"]["hash"]))
await watch.unsubscribe()
await ws.close()
```

- `newBlocks` replays committed blocks from `from_height`, then streams live ones — exactly once per height.
- `addressActivity` fires for every **final** transaction whose sender, recipient or token recipient is in the list
  (at most 1000 addresses, 16 subscriptions per socket).
- A handler may be a plain function or an `async def`.
- **Reconnect**: on a dropped socket the client reconnects with exponential backoff (1 s up to 30 s) and re-issues
  every subscription; `subscription.id` changes, handlers stay. Pass `reconnect=False` to opt out and `on_event=` to
  log `open` / `close` / `error` / `resubscribed`.
- The node disconnects slow consumers (2 MiB send buffer, 5 s send timeout): keep handlers fast.

## Errors

JSON-RPC errors map to the same classes as REST — see [errors](errors.md).
