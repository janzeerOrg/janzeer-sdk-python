"""Seal a recovery phrase under a password and open it again."""

from janzeer import Account, VaultError, decrypt_vault, encrypt_vault, mnemonic

phrase = mnemonic.generate()
blob = encrypt_vault(phrase, "correct horse battery staple")
print("vault:", {k: (v if k == "v" else v[:12] + "…") for k, v in blob.items()})

assert decrypt_vault(blob, "correct horse battery staple") == phrase
print("opened; address", Account.from_mnemonic(phrase).checksum_address)
try:
    decrypt_vault(blob, "wrong password")
except VaultError as e:
    print("wrong password ->", e)
