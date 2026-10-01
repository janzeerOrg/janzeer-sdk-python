# Security

## Reporting a vulnerability

Email **security@janzeer.org** with a description and, if possible, a minimal reproduction. Please do not open a public
issue for anything that could affect users' funds. We acknowledge reports within 3 working days.

## What this SDK does and does not do

- The SDK **never transmits private keys or mnemonics**. It derives keys and signs in your process; the node only
  ever receives a signed transaction and read queries. There is no server-side signing endpoint.
- `Account.private_key_hex` exists for backup and export flows. Do not log it; `repr(account)` shows the address
  only. Prefer the vault functions to store a mnemonic at rest.
- Signatures are deterministic (RFC 6979): the same transaction always produces the same signature, so a weak random
  number generator cannot leak the key through signing. Key *generation* (`mnemonic.generate`, `Account.random`)
  uses the operating system's random source through `secrets`.
- Cryptography comes from `coincurve` (bindings of libsecp256k1, the library Bitcoin Core uses), `pycryptodome`
  (keccak-256, AES-GCM) and the Python standard library (SHA-2, HMAC, PBKDF2). The SDK adds no primitive of its own.
- Amounts are never floats: a `float` is refused wherever an amount is expected.
- The SDK trusts the node it talks to for chain data. Use HTTPS/WSS to a node you operate or trust; balances and
  finality answers come from that node.
