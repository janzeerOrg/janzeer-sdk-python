# Sending transactions

Every transaction is built locally, signed locally and submitted as JSON. The node re-checks the hash, the signature,
the sender / public-key match, the nonce, the balance and the fees, and either accepts it into the mempool (HTTP 201 /
RPC `{hash, status: "PENDING"}`) or rejects it with a typed reason.

```python
unsigned = TxBuilder.transfer(sender=me.address, to=to, amount="1.25", nonce=nonce)
signed   = me.sign_tx(unsigned)          # SignedTx: hash, signature, sender_public_key
client.submit(signed)                    # REST
rpc.send(signed)                         # or JSON-RPC — same body, same result
```

## Nonces

Each sender has a nonce that must be consecutive. `client.nonce(address)` (or `rpc.get_account(address)["nextNonce"]`)
returns **committed nonce + pending count**, so you can pipeline several transactions before the first is final:
nonce `n`, `n+1`, `n+2`… A gap or a replay is refused with `NonceMismatchError` (`expected`, `got`) — read `expected`,
rebuild, resend. Sending the *same* signed transaction twice is harmless: the node answers `PENDING` again.

## Network id — mainnet vs testnet

Every transaction is signed for one network: the network id is the first field of the signed bytes, so a transaction
built for `janzeer` (mainnet) is rejected by a `janzeer-testnet` node and vice versa. The builders default to
`NETWORK_ID` (`"janzeer"`); when your app can point at a testnet, read the id from the node once and pass it on:

```python
info = client.info()            # {networkId, genesisHash, version, syncStatus, faucet, …}
tx = me.sign_tx(TxBuilder.transfer(sender=me.address, to=to, amount="1.25", nonce=nonce, network_id=info["networkId"]))
```

## Fees and limits

| Transaction | Fee | Other rule |
|---|---|---|
| transfer | ≥ `MIN_FEE` (0.01) | amount ≥ `MIN_TRANSFER` (0.1) unless a memo is present; memo ≤ 256 UTF-8 bytes |
| register_validator | exactly `VALIDATOR_FEE` (3) | deposit exactly `VALIDATOR_DEPOSIT` (2000), **non-refundable** |
| exit_validator | ≥ 0.01 | — |
| token.create | exactly `TOKEN_CREATE_FEE` (5) | the sender must be a validator wallet |
| token.mint / burn / set_cap / transfer | ≥ 0.01 | issuer-only for mint, burn and set_cap |

`TxBuilder` fills the default fee and refuses locally what the node would refuse for these reasons, so you get a
`ValueError` with a plain message instead of an HTTP 400. `rpc.estimate_fee(kind)` returns the same numbers from the
node. There is no fee market.

## Amounts

Coin amounts are **decimal strings** (`"1.25"`); `int` (whole coins) and `decimal.Decimal` are accepted too. A `float`
raises `TypeError`. Internally an amount is scaled by 10^8 to an integer (`to_scaled("1.25") == 125_000_000`), which
is what gets signed.

```python
format_jnz("1.50000000")                 # '1.5 JNZ'
format_jnz("1234.5", group=True)         # '1,234.5 JNZ'
parse_jnz("1,234.5 JNZ")                 # '1234.5'
add_amounts("0.1", "0.2")                # '0.30000000'  — exact
compare_amounts("0.1", "0.10")           # 0
```

## Transfer

```python
TxBuilder.transfer(sender=me.address, to=to, amount="1.25", data="invoice 42", nonce=nonce, fee="0.01")
```

`data` is an optional memo (≤ 256 bytes). With a memo the amount may be below 0.1, even `"0"`, which makes a transfer
a cheap on-chain note.

## Validator registration and exit

```python
validator_key = client.info()["nodeKey"]                                           # the NODE's public key
TxBuilder.register_validator(sender=me.address, validator_key=validator_key, nonce=nonce)      # fee 3, deposit 2000
TxBuilder.exit_validator(sender=me.address, validator_key=validator_key, nonce=nonce + 1)      # removed at the next epoch
```

The key is the public key of a node you run, never the wallet's own key. The wallet that registers a node becomes its
*validator wallet*: block rewards go there, and only it can create tokens.

## Tokens (JZT-1)

Token amounts are **integer base units** (`int` or a digit string) — the token's `decimals` is display-only.

```python
create   = TxBuilder.token.create(sender=me.address, symbol="DEMO", name="Demo", decimals=2, cap=1_000_000, amount=500_000, nonce=nonce)
token_id = me.sign_tx(create).hash                     # for CREATE the token id IS the transaction hash
TxBuilder.token.mint(sender=me.address, token_id=token_id, amount=100, recipient=to, nonce=nonce)
TxBuilder.token.burn(sender=me.address, token_id=token_id, amount=100, nonce=nonce)
TxBuilder.token.set_cap(sender=me.address, token_id=token_id, cap=2_000_000, nonce=nonce)
TxBuilder.token.transfer(sender=me.address, token_id=token_id, amount=12_345, recipient=to, nonce=nonce)
```

## Waiting for finality

```python
view = wait_for_finality(rpc, signed.hash)      # FINAL view with blockHeight and receipt
view = send_and_wait(rpc, signed)               # submit + wait in one call
```

A transaction in a committed block is final; there is nothing to wait for beyond that. See
[json-rpc-and-subscriptions](json-rpc-and-subscriptions.md#finality).

## Signing elsewhere (hardware wallet, KMS)

```python
unsigned = TxBuilder.transfer(…)
digest   = unsigned.hash()                                   # 32-byte hex to sign (RFC-6979 low-S DER expected)
signed   = unsigned.with_signature(base64_der, public_key_hex)
```
