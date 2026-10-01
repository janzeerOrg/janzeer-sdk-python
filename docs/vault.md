# Vault — a secret at rest

`encrypt_vault` seals a mnemonic (or any string) under a password so an application can keep it in a file, a database
row or a keychain entry.

```python
import json
from janzeer import VaultError, decrypt_vault, encrypt_vault

blob = encrypt_vault(phrase, password)          # {"v": 1, "salt", "iv", "ct"} — JSON-safe, base64 fields
open("wallet.vault", "w").write(json.dumps(blob))

try:
    phrase = decrypt_vault(json.load(open("wallet.vault")), password)
except VaultError:
    ...                                         # wrong password or tampered blob
```

## Format (v1)

| Field | Value |
|---|---|
| key | PBKDF2-HMAC-SHA256, 250,000 rounds, 16-byte random `salt`, 32-byte key |
| cipher | AES-256-GCM, 12-byte random `iv`, `ct` = ciphertext ‖ 16-byte tag |
| encoding | all three fields base64 |

Blobs are interchangeable with the TypeScript, Dart and Kotlin SDKs and with the Janzeer wallets (the conformance
kit's `vault-fixture.json` pins it).

## Notes

- The password stretching runs in OpenSSL through `hashlib` and takes roughly 0.1 s on a laptop.
- A vault protects a phrase at rest; it does not make a weak password strong.
