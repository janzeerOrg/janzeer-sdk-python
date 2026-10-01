"""A signing identity: private key -> public key -> address. The node never sees the private key."""

from __future__ import annotations

import secrets

from coincurve import PrivateKey

from . import mnemonic as _mnemonic
from .crypto import DEFAULT_PATH, derive_path, hex_to_bytes, is_valid_private_key, public_key_to_address, sign_hash, to_checksum_address, verify_hash
from .tx import SignedTx, UnsignedTx


class Account:
    """Holds one private key. ``repr()`` shows the address only; the key is never printed or logged by the SDK."""

    __slots__ = ("_priv", "public_key_hex", "address", "checksum_address")

    def __init__(self, private_key: bytes) -> None:
        if len(private_key) != 32 or not is_valid_private_key(private_key.hex()):
            raise ValueError("invalid secp256k1 private key")
        self._priv = private_key
        pub = PrivateKey(private_key).public_key.format(compressed=True)
        #: compressed secp256k1 public key, hex (66 chars)
        self.public_key_hex: str = pub.hex()
        #: canonical lowercase address
        self.address: str = public_key_to_address(pub)
        #: EIP-55 display form of ``address``
        self.checksum_address: str = to_checksum_address(self.address)

    @classmethod
    def from_mnemonic(cls, mnemonic: str, passphrase: str = "") -> Account:
        """Wallet account from a BIP39 mnemonic (Janzeer seed, path ``m/0/0/0``)."""
        if not _mnemonic.validate(mnemonic):
            raise ValueError("invalid mnemonic (unknown word or bad checksum)")
        return cls.from_seed(_mnemonic.to_seed(mnemonic, passphrase))

    @classmethod
    def from_seed(cls, seed: bytes, path: str = DEFAULT_PATH) -> Account:
        """Account from a 64-byte seed (any non-hardened path; default ``m/0/0/0``)."""
        return cls(derive_path(seed, path).priv)

    @classmethod
    def from_private_key(cls, private_key_hex: str) -> Account:
        """Account from a raw private key (hex, optional ``0x``)."""
        if not is_valid_private_key(private_key_hex):
            raise ValueError("invalid secp256k1 private key")
        return cls(hex_to_bytes(private_key_hex))

    @classmethod
    def random(cls) -> Account:
        """A fresh random key (not mnemonic-backed; prefer ``mnemonic.generate()`` for user wallets)."""
        while True:
            raw = secrets.token_bytes(32)
            if is_valid_private_key(raw.hex()):
                return cls(raw)

    @property
    def private_key_hex(self) -> str:
        """The private key as hex. Handle with care: never log or send it."""
        return self._priv.hex()

    def sign(self, hash_hex: str) -> str:
        """RFC-6979 low-S DER signature (Base64) over a 32-byte digest given as hex."""
        return sign_hash(hash_hex, self._priv.hex())

    def verify(self, hash_hex: str, signature_base64: str) -> bool:
        """Verify a signature made by this account."""
        return verify_hash(hash_hex, signature_base64, self.public_key_hex)

    def sign_tx(self, tx: UnsignedTx) -> SignedTx:
        """Hash and sign a transaction. Raises if the transaction names another sender."""
        if tx.sender_address != self.address:
            raise ValueError(f"tx sender {tx.sender_address} is not this account ({self.address})")
        return tx.with_signature(self.sign(tx.hash()), self.public_key_hex)

    def __repr__(self) -> str:
        return f"Account({self.address})"
