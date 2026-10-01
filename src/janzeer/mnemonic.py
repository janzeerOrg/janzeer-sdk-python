"""BIP39 English mnemonics (standard word list and checksum). Only the SEED derivation is Janzeer-specific."""

from __future__ import annotations

import hashlib
import secrets
from functools import lru_cache
from importlib import resources

from .crypto import mnemonic_to_seed

_STRENGTHS = (128, 160, 192, 224, 256)


@lru_cache(maxsize=1)
def wordlist() -> tuple[str, ...]:
    """The 2048 English words."""
    words = tuple(resources.files(__package__).joinpath("bip39_english.txt").read_text(encoding="utf-8").split())
    if len(words) != 2048:
        raise RuntimeError("corrupt BIP39 word list")
    return words


def normalize(mnemonic: str) -> str:
    """Normalize whitespace and case so equivalent phrases derive the same seed."""
    return " ".join(mnemonic.strip().lower().split())


def from_entropy(entropy: bytes) -> str:
    """Entropy bytes (16, 20, 24, 28 or 32) -> mnemonic."""
    bits = len(entropy) * 8
    if bits not in _STRENGTHS:
        raise ValueError("entropy must be 16, 20, 24, 28 or 32 bytes")
    checksum_bits = bits // 32
    value = (int.from_bytes(entropy, "big") << checksum_bits) | (hashlib.sha256(entropy).digest()[0] >> (8 - checksum_bits))
    count = (bits + checksum_bits) // 11
    words = wordlist()
    return " ".join(words[(value >> (11 * (count - 1 - i))) & 0x7FF] for i in range(count))


def to_entropy(mnemonic: str) -> bytes:
    """Mnemonic -> entropy bytes. Raises ``ValueError`` for an unknown word, a bad length or a bad checksum."""
    parts = normalize(mnemonic).split(" ")
    if len(parts) not in (12, 15, 18, 21, 24):
        raise ValueError("a mnemonic has 12, 15, 18, 21 or 24 words")
    index = {w: i for i, w in enumerate(wordlist())}
    value = 0
    for w in parts:
        if w not in index:
            raise ValueError("unknown word in mnemonic")
        value = (value << 11) | index[w]
    checksum_bits = len(parts) * 11 // 33
    bits = len(parts) * 11 - checksum_bits
    entropy = (value >> checksum_bits).to_bytes(bits // 8, "big")
    if (hashlib.sha256(entropy).digest()[0] >> (8 - checksum_bits)) != (value & ((1 << checksum_bits) - 1)):
        raise ValueError("bad mnemonic checksum")
    return entropy


def generate(strength: int = 128) -> str:
    """A fresh mnemonic from the OS random source: 12 words (128-bit, default) up to 24 (256-bit)."""
    if strength not in _STRENGTHS:
        raise ValueError("strength must be 128, 160, 192, 224 or 256")
    return from_entropy(secrets.token_bytes(strength // 8))


def validate(mnemonic: str) -> bool:
    """Word-list membership + checksum. Client-side only — the node never sees a mnemonic."""
    try:
        to_entropy(mnemonic)
        return True
    except ValueError:
        return False


def to_seed(mnemonic: str, passphrase: str = "") -> bytes:
    """Janzeer seed (PBKDF2-HMAC-SHA512, salt ``@_Janzeer_Blockchain_@`` + passphrase) — NOT the BIP39 standard seed."""
    return mnemonic_to_seed(normalize(mnemonic), passphrase)
