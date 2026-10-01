# Reading chain data

`JanzeerClient` wraps the `/api/v1` endpoints. Results are the node's JSON as `dict` / `list` values with the node's
field names; amounts arrive as `decimal.Decimal` (or decimal strings where noted), never as floats.

```python
client = JanzeerClient("https://onion.janzeer.org")      # '/api/v1/' is appended automatically
```

`AsyncJanzeerClient` has the same methods; each returns an awaitable.

## Node

```python
client.info()            # {nodeKey, networkId, genesisHash, chainSpecDigest, version, apiVersion, protocolVersion, syncStatus, faucet}
client.version()
client.uptime()          # ms
client.genesis()         # the network's public genesis document
client.explorer_info()   # counts, TPS, epoch, supply
client.last_envelope     # {timestamp, version} of the last response
```

## Accounts

```python
client.balance(addr)            # spendable balance as a decimal string; "0" for an unknown address
client.nonce(addr)              # next nonce to sign with; 0 for an unknown address
client.validate_address(addr)
client.token_balances(addr)
```

`rpc.get_account(addr)` returns all of it in one call (`balance`, `committedBalance`, `nextNonce`, `committedNonce`,
`pendingCount`, `isValidatorWallet`).

## Pagination

Every list takes `page` (0-based), `size` (1–100), `sort_by`, `sort_direction` and returns
`{total, list, page, pageSize, totalPages}`.

```python
p = client.transfers.list(address=addr, page=0, size=20)
for t in p["list"]:
    print(t["hash"], t["amount"], t.get("blockHash") or "pending")
```

## Transactions

```python
client.transfers.list(address=addr, unconfirmed=True)     # unconfirmed=True -> the mempool
client.transfers.get(hash)                                # None when unknown
client.validator_txs.list(address=addr, node_key=key)     # registrations
client.exit_validator_txs.list(address=addr)
client.token_txs.list(token_id=token_id)
client.rewards.list(address=addr)                         # block rewards paid to addr
client.receipt(hash)                                      # execution receipt of a committed transaction
```

For one view of *any* transaction with its status (`FINAL | PENDING | UNKNOWN`), block and receipt, use
`rpc.get_transaction_by_hash(hash)`.

## Blocks

```python
client.main_blocks.list(size=5)           # newest first
client.main_blocks.get(hash); client.main_blocks.previous(hash); client.main_blocks.next(hash)
client.genesis_blocks.list()              # one per epoch: pins the epoch's validator set
```

`rpc.get_tip()`, `rpc.get_block_by_number(h, True)` and `rpc.get_blocks(a, b)` (at most 100) give richer views with
the transactions inline.

## Validators and tokens

```python
client.validators()                 # every registered validator {address, nodeKey}
client.validators(active=True)      # the current epoch's producer set
client.tokens(); client.token(token_id); client.token_holders(token_id)
```

## Anything else

`client.get(path, query)` and `client.post(path, body)` reach any endpoint and return the envelope payload.

## Choosing REST or JSON-RPC

Both talk to the same services. REST suits explorers and dashboards (paged, cacheable GETs). JSON-RPC adds batches,
unified transaction and block views, the finality long-poll and the WebSocket feeds.
