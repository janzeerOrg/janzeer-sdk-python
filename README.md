# janzeer-sdk (Python)

Official Python SDK for the [Janzeer](https://janzeer.org) blockchain — a stake-free, permissionless Layer-1 with
instant finality. Wallet keys and signing, transaction builders, a REST client, JSON-RPC over HTTP and WebSocket
subscriptions, blocking and `asyncio`. Non-custodial by construction: keys never leave your process, the node only
verifies.

![license](https://img.shields.io/badge/license-Apache--2.0-blue)
![python](https://img.shields.io/badge/python-3.10%20%E2%80%93%203.13-blue)

```bash
pip install janzeer-sdk            # add [ws] for WebSocket subscriptions: pip install "janzeer-sdk[ws]"
```

> **Not on PyPI yet.** The package follows shortly after the mainnet launch. Until then, install from the repository:
>
> ```bash
> pip install "janzeer-sdk[ws] @ git+https://github.com/janzeerorg/janzeer-sdk-python"
> ```

## 60-second quickstart

```python
from janzeer import Account, JanzeerClient, JanzeerRpc, TxBuilder, format_jnz, wait_for_finality

client = JanzeerClient("https://onion.janzeer.org")        # REST  (/api/v1)
rpc    = JanzeerRpc("https://onion.janzeer.org")           # JSON-RPC (/rpc)
me     = Account.from_mnemonic("abandon abandon … about")  # 12/24-word BIP39 phrase

print(me.checksum_address, format_jnz(client.balance(me.address)))

tx = me.sign_tx(TxBuilder.transfer(
    sender=me.address, to="0x598b1301acef3baba6ce25e38dd17b723f7b98b1",
    amount="1.25", data="hello", nonce=client.nonce(me.address),
))
client.submit(tx)                                          # HTTP 201, or a typed error
final = wait_for_finality(rpc, tx.hash)                    # one or two 15-second slots
print("final in block", final["blockHeight"])
```

That is the whole integration: derive → nonce → build → sign → submit → wait. A committed block is final
(2f+1 BFT commit), so there is no confirmation count.

The same with `asyncio`: `AsyncJanzeerClient`, `AsyncJanzeerRpc`, `JanzeerRpcWs` and `await_finality` have the same
methods and return awaitables.

## What is in the box

| Area | Entry points | Guide |
|---|---|---|
| Keys & addresses | `mnemonic`, `Account`, `to_checksum_address`, `is_valid_address` | [wallet-and-keys](docs/wallet-and-keys.md) |
| Transactions | `TxBuilder.transfer / register_validator / exit_validator / token.*` → `UnsignedTx` → `SignedTx` | [sending-transactions](docs/sending-transactions.md) |
| Amounts | `to_scaled`, `from_scaled`, `format_jnz`, `parse_jnz`, `add_amounts`… | [sending-transactions](docs/sending-transactions.md#amounts) |
| REST | `JanzeerClient` / `AsyncJanzeerClient`: balances, nonces, transactions, blocks, validators, tokens | [reading-chain-data](docs/reading-chain-data.md) |
| JSON-RPC | `JanzeerRpc` / `AsyncJanzeerRpc` (HTTP, batches) and `JanzeerRpcWs` (WebSocket + `newBlocks` / `addressActivity`) | [json-rpc-and-subscriptions](docs/json-rpc-and-subscriptions.md) |
| Flows | `wait_for_finality`, `send_and_wait`, `next_nonce` (and `await_finality`, `asend_and_wait`) | [json-rpc-and-subscriptions](docs/json-rpc-and-subscriptions.md#finality) |
| Errors | `TxRejectedError`, `NonceMismatchError`, `RateLimitedError`, `RpcError`… | [errors](docs/errors.md) |
| Vault | `encrypt_vault` / `decrypt_vault` (PBKDF2 + AES-GCM, compatible with the other SDKs) | [vault](docs/vault.md) |

## Money is never a float

Amounts are decimal **strings** (`"1.25"`), `int` (whole coins) or `decimal.Decimal`. A `float` is refused with a
`TypeError` everywhere — in the builders, in the amount helpers and in request bodies — because `0.1` is not
representable in binary and a payment must not depend on how a float prints. Responses are parsed losslessly:
numbers with a fraction arrive as `Decimal`, `client.balance()` returns a decimal string.

## Results are plain JSON

Network calls return the node's JSON as `dict` / `list` values with the field names the node uses
(`blockHeight`, `senderAddress`, …), documented in the
[API reference](https://github.com/janzeerorg/janzeer-docs/blob/master/en/api-reference.md). Keys, transactions and
errors are typed classes; the package ships `py.typed`.

## Requirements

- Python 3.10 – 3.13 on Linux, macOS or Windows.
- `coincurve` (libsecp256k1), `pycryptodome` (keccak-256, AES-GCM), `httpx`; `websockets` for subscriptions.
  Wheels exist for all three systems: no compiler is needed.

## Compatibility

| SDK | Node | REST envelope `version` | Wire protocol | Vectors |
|---|---|---|---|---|
| 0.1.x | 0.1.0 | 1.1.0 | 3.4.0 | v2 |

`SPEC_VERSION` exports these values; the e2e test checks them against the node on the first call.

## Examples

Runnable scripts in [`examples/`](examples): a transfer to finality, an address-activity subscription, the token
life cycle, a validator registration, and a vault round trip. They read the `JANZEER_*` environment variables
described in [CONTRIBUTING](CONTRIBUTING.md).

## Conformance

This SDK reproduces, byte for byte, the public test vectors every Janzeer SDK is tested against (key derivation,
addresses, every transaction preimage, hash and signature, the vault fixture) and passes the shared 14-step
end-to-end flow: <https://github.com/janzeerorg/janzeer-sdk-conformance>. See [docs/conformance.md](docs/conformance.md).

## Other SDKs

[TypeScript](https://github.com/janzeerorg/janzeer-sdk-ts) · [Dart / Flutter](https://github.com/janzeerorg/janzeer-sdk-dart) ·
[Kotlin / JVM / Android](https://github.com/janzeerorg/janzeer-sdk-kotlin) · [Go](https://github.com/janzeerorg/janzeer-sdk-go)

## Licence

Apache License 2.0 — see [LICENSE](LICENSE). Security reports: see [SECURITY](SECURITY.md).
