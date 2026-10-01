# Wallet and keys

Janzeer wallets are BIP39-shaped but use the chain's own constants, so a stock bip32 or Ethereum library derives a
**different** key from the same phrase. Always derive with the SDK (or a client that passes the
[conformance vectors](conformance.md)).

## Create or import

```python
from janzeer import Account, mnemonic

phrase  = mnemonic.generate()                 # 12 words (pass 256 for 24)
account = Account.from_mnemonic(phrase)       # optional second argument: BIP39 passphrase
account.address            # canonical, lowercase — what the chain stores and what you sign with
account.checksum_address   # EIP-55 mixed case — for display and typo detection
account.public_key_hex     # compressed secp256k1, 66 hex chars

Account.from_private_key("6dea…8efc")                       # raw key import
Account.from_seed(mnemonic.to_seed(phrase), "m/0/1/0")      # another non-hardened path (advanced)
```

`mnemonic.validate(phrase)` checks the word list and the checksum; `Account.from_mnemonic` raises `ValueError` on an
invalid phrase. `repr(account)` shows the address only — the private key is never printed by the SDK.

## How derivation works (so you can audit it)

| Step | Janzeer | Standard BIP39/32 |
|---|---|---|
| seed | PBKDF2-HMAC-SHA512, 2048 rounds, salt `"@_Janzeer_Blockchain_@" + passphrase` | salt `"mnemonic" + passphrase` |
| master key | HMAC-SHA512 keyed with `"@_Janzeer_Blockchain_@"` | keyed with `"Bitcoin seed"` |
| path | `m/0/0/0`, all non-hardened | varies |
| address | `0x` + first 20 bytes of keccak256(**compressed** public key), lowercase | Ethereum hashes the uncompressed key |

The low-level functions live in `janzeer.crypto`: `mnemonic_to_seed`, `seed_to_master_key`, `derive_child`,
`derive_path`, `public_key_to_address`. Keccak-256 here is the Ethereum variant, **not** `hashlib.sha3_256`.

## Addresses

```python
from janzeer import is_valid_address, normalize_address, to_checksum_address

is_valid_address("0x06e1c0FA9955A700876f8cB0Acc7f13fBA9FB8BA")   # True  (correct EIP-55 casing)
is_valid_address("0x06E1c0fa9955a700876f8cb0acc7f13fba9fb8ba")   # False (mis-cased: likely a typo)
normalize_address("0x06e1c0FA…")                                 # '0x06e1c0fa…'
```

The node accepts lowercase or correctly cased addresses and always answers lowercase. Sign and store the lowercase
form; show the checksum form.

## Signing

`account.sign(hash_hex)` produces an RFC-6979 deterministic, low-S, DER-encoded, Base64 signature over the 32-byte
digest — exactly what the node verifies. You rarely call it directly: `account.sign_tx(unsigned_tx)` hashes and signs
a transaction built by `TxBuilder`. A hardware wallet or KMS can sign `unsigned_tx.hash()` externally and attach it
with `unsigned_tx.with_signature(signature, public_key_hex)`.

## Keeping the phrase at rest

Use the [vault](vault.md) functions or your platform's secure storage. Never send the phrase or a private key to any
server: the node has no endpoint that would accept one.
