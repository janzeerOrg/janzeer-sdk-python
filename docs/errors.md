# Errors, nonces and rate limits

Everything the SDK raises for a node or network problem extends `JanzeerError`. Branch on the class, never on message
text. (Local input mistakes — a float amount, a bad address — raise the built-in `TypeError` / `ValueError`.)

```
JanzeerError
├─ NetworkError              node unreachable / non-JSON / socket closed / timeout
├─ TxRejectedError           the node refused a transaction — `type` names the rule
│   └─ NonceMismatchError    `expected`, `got`, `address`
├─ ApiError                  other REST errors: `status`, `type`, `body`
│   ├─ ValidationError       400 with a list of field messages (`messages`)
│   └─ NotFoundError         404
├─ NotSynchronizedError      the node is still syncing (REST 400 / RPC -32002) — retry shortly
├─ RateLimitedError          HTTP 429 / RPC -32004 — `retry_after` (seconds)
├─ RpcError                  `code`, `data`
│   ├─ RpcInvalidParamsError -32602 (data: field messages)
│   ├─ RpcNotFoundError      -32000
│   ├─ RpcLimitError         -32003 (range / timeout above the cap)
│   └─ RpcMethodNotFoundError -32601
└─ FinalityTimeoutError      wait_for_finality deadline (`last` view)
```

`TxRejectedError` and `NonceMismatchError` are the same classes on every transport (`transport` is `"rest"`, `"rpc"`
or `"ws"`, with `http_status` or `rpc_code`).

## Rejection types

| `type` | Meaning | What to do |
|---|---|---|
| `INVALID_NONCE` | nonce ≠ the sender's next nonce (`NonceMismatchError.expected`) | refresh the nonce and rebuild |
| `INCORRECT_SIGNATURE` | the signature does not verify | you signed other bytes — check the fields and the network id |
| `INCORRECT_HASH` | `hash` ≠ double-SHA256 of the signed bytes | same |
| `INCORRECT_ADDRESS` | `senderAddress` is not the address of `senderPublicKey` | derive both from one `Account` |
| `INSUFFICIENT_ACTUAL_BALANCE` / `INSUFFICIENT_BALANCE` | not enough spendable balance for amount + fee | — |
| `INCORRECT_PROMOTER_KEY` / `ALREADY_PROMOTER` | validator key invalid / already registered | — |

A newer node may add types; `e.type` carries the string as received.

## Nonce handling pattern

```python
def send_with_retry(build):                      # build(nonce) -> SignedTx
    nonce = client.nonce(me.address)
    for _ in range(3):
        try:
            return client.submit(build(nonce))
        except NonceMismatchError as e:
            if e.expected is None:
                raise
            nonce = e.expected
    raise RuntimeError("could not agree on a nonce")
```

Pipelining: after submitting nonce `n`, `client.nonce()` already answers `n+1`; you may keep sending. If a pending
transaction is dropped (6 h mempool expiry) the ones behind it become gaps — rebuild from `expected`.

## Rate limits

Nodes throttle `POST /api/v1/transactions/**` and `/rpc` per client IP (default 20 requests/s, burst 40). Reads are
never limited. The clients retry **once** after a 429, honouring `Retry-After` (`retry_on_rate_limit=False` to
disable); resubmitting a transaction is safe because acceptance is idempotent by hash.
