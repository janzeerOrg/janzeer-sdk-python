"""The node's cryptography, byte for byte: hashes, key derivation, addresses and signatures.

It is BIP39/BIP32-SHAPED but uses Janzeer's own constants, so stock bip32 or Ethereum libraries will NOT reproduce it:
the PBKDF2 salt and the root HMAC key are both ``@_Janzeer_Blockchain_@``, the path is ``m/0/0/0`` (non-hardened),
an address is the first 20 bytes of keccak256 over the COMPRESSED public key, and signatures are RFC-6979, low-S,
DER, Base64, over the raw 32-byte digest. The conformance vectors pin every function here.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import re
from typing import NamedTuple

from coincurve import PrivateKey, PublicKey
from Crypto.Hash import keccak as _keccak

#: Used BOTH as the PBKDF2 salt base (instead of BIP39's ``"mnemonic"``) AND as the root HMAC key.
HD_SALT = "@_Janzeer_Blockchain_@"
#: The only derivation path wallets use; all three levels are non-hardened.
DEFAULT_PATH = "m/0/0/0"
_N = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364141
_ADDRESS_RE = re.compile(r"^0x[0-9a-fA-F]{40}$")


# ---- bytes -----------------------------------------------------------------------------------------------------------
def hex_to_bytes(text: str) -> bytes:
    """Lenient hex -> bytes: an optional ``0x`` prefix and either case."""
    return bytes.fromhex(text[2:] if text[:2] in ("0x", "0X") else text)


def i64be(value: int) -> bytes:
    """8-byte big-endian two's complement (Java ``putLong``)."""
    return (value & 0xFFFFFFFFFFFFFFFF).to_bytes(8, "big")


def ser32(value: int) -> bytes:
    """4-byte big-endian (BIP32 ``ser32`` / Java ``putInt``)."""
    return (value & 0xFFFFFFFF).to_bytes(4, "big")


def len_prefixed(text: str | None) -> bytes:
    """``int32(len) || utf8(s)`` — the node's length-prefixed string. ``None`` is the empty string."""
    b = (text or "").encode("utf-8")
    return ser32(len(b)) + b


# ---- hashes ----------------------------------------------------------------------------------------------------------
def sha256(data: bytes) -> bytes:
    return hashlib.sha256(data).digest()


def double_sha256(data: bytes) -> bytes:
    """``HashUtils.doubleSha256`` — the transaction hash function."""
    return sha256(sha256(data))


def hash_preimage(preimage: bytes) -> str:
    """Double-SHA256 as lowercase hex — what the node calls the transaction ``hash``."""
    return double_sha256(preimage).hex()


def keccak256(data: bytes) -> bytes:
    """Keccak-256 (the Ethereum variant). NOT ``hashlib.sha3_256``: NIST SHA3 uses a different padding."""
    return _keccak.new(digest_bits=256, data=data).digest()


# ---- key derivation --------------------------------------------------------------------------------------------------
class HdNode(NamedTuple):
    """An extended private key: 32-byte private key + 32-byte chain code."""

    priv: bytes
    chain_code: bytes


def mnemonic_to_seed(mnemonic: str, passphrase: str = "") -> bytes:
    """``SeedCalculator.calculateSeed`` — PBKDF2-HMAC-SHA512, 2048 rounds, 64 bytes, salt ``HD_SALT + passphrase``."""
    import unicodedata

    password = unicodedata.normalize("NFKD", mnemonic).encode("utf-8")
    salt = (HD_SALT + unicodedata.normalize("NFKD", passphrase)).encode("utf-8")
    return hashlib.pbkdf2_hmac("sha512", password, salt, 2048, 64)


def seed_to_master_key(seed: bytes) -> HdNode:
    """``ExtendedKey.root`` — ``I = HMAC-SHA512(key=HD_SALT, msg=seed)``; left half = key, right half = chain code."""
    i = hmac.new(HD_SALT.encode("utf-8"), seed, hashlib.sha512).digest()
    return HdNode(i[:32], i[32:])


def derive_child(node: HdNode, index: int) -> HdNode:
    """``ExtendedKey.getChild`` — standard BIP32 non-hardened CKDpriv (``index`` < 2^31)."""
    if not isinstance(index, int) or isinstance(index, bool) or not 0 <= index < 0x80000000:
        raise ValueError("non-hardened index expected")
    pub = PrivateKey(node.priv).public_key.format(compressed=True)
    i = hmac.new(node.chain_code, pub + ser32(index), hashlib.sha512).digest()
    child = (int.from_bytes(i[:32], "big") + int.from_bytes(node.priv, "big")) % _N
    return HdNode(child.to_bytes(32, "big"), i[32:])


def derive_path(seed: bytes, path: str = DEFAULT_PATH) -> HdNode:
    """Derive a path like ``m/0/0/0`` (non-hardened segments only)."""
    parts = path.split("/")
    if parts[0] != "m":
        raise ValueError(f"path must start with m/: {path}")
    node = seed_to_master_key(seed)
    for p in parts[1:]:
        if p[-1:] in ("'", "h", "H"):
            raise ValueError("hardened derivation is not part of the Janzeer scheme")
        node = derive_child(node, int(p))
    return node


# ---- addresses -------------------------------------------------------------------------------------------------------
def public_key_to_address(compressed_public_key: bytes) -> str:
    """CANONICAL address: ``"0x"`` + lowercase hex of the first 20 bytes of keccak256(compressed public key)."""
    if len(compressed_public_key) != 33:
        raise ValueError("compressed (33-byte) public key expected")
    return "0x" + keccak256(compressed_public_key)[:20].hex()


def to_checksum_address(address: str) -> str:
    """EIP-55 mixed-case display form. Presentation only — never sign or store it."""
    body = address.lower().removeprefix("0x")
    digest = keccak256(body.encode("ascii")).hex()
    return "0x" + "".join(c.upper() if c in "abcdef" and int(digest[i], 16) >= 8 else c for i, c in enumerate(body))


def is_valid_address(address: object) -> bool:
    """Shape + checksum — what the node accepts: all-lowercase, all-uppercase, or correctly cased EIP-55."""
    if not isinstance(address, str) or not _ADDRESS_RE.match(address):
        return False
    body = address[2:]
    if body == body.lower() or body == body.upper():
        return True
    return to_checksum_address(address) == address


def normalize_address(address: str) -> str:
    """Canonical lowercase form; raises ``ValueError`` on an invalid address."""
    if not is_valid_address(address):
        raise ValueError(f"invalid address: {address}")
    return address.lower()


# ---- signatures ------------------------------------------------------------------------------------------------------
def is_valid_private_key(private_key_hex: str) -> bool:
    """True for a valid secp256k1 scalar (32 bytes, 0 < k < n)."""
    try:
        raw = hex_to_bytes(private_key_hex)
    except ValueError:
        return False
    return len(raw) == 32 and 0 < int.from_bytes(raw, "big") < _N


def private_to_public(private_key_hex: str) -> str:
    """Compressed (33-byte) public key, hex, from a private key (hex)."""
    return PrivateKey(hex_to_bytes(private_key_hex)).public_key.format(compressed=True).hex()


def sign_hash(hash_hex: str, private_key_hex: str) -> str:
    """Sign a 32-byte digest (hex): RFC-6979 deterministic, low-S, DER, Base64. The digest is signed as-is."""
    digest = hex_to_bytes(hash_hex)
    if len(digest) != 32:
        raise ValueError("a 32-byte digest is expected")
    der = PrivateKey(hex_to_bytes(private_key_hex)).sign(digest, hasher=None)
    return base64.b64encode(der).decode("ascii")


def verify_hash(hash_hex: str, signature_base64: str, public_key_hex: str) -> bool:
    """Verify a Base64 DER signature over a digest (hex) with a compressed public key (hex). High-S is refused."""
    try:
        der = base64.b64decode(signature_base64, validate=True)
        if not _is_low_s(der):
            return False
        return bool(PublicKey(hex_to_bytes(public_key_hex)).verify(der, hex_to_bytes(hash_hex), hasher=None))
    except Exception:
        return False


def _is_low_s(der: bytes) -> bool:
    # DER: 0x30 len 0x02 rlen r 0x02 slen s
    if len(der) < 8 or der[0] != 0x30 or der[2] != 0x02:
        return False
    rlen = der[3]
    if der[4 + rlen] != 0x02:
        return False
    slen = der[5 + rlen]
    s = int.from_bytes(der[6 + rlen : 6 + rlen + slen], "big")
    return 0 < s <= _N // 2
