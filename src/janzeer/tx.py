"""Transactions: the signed-bytes layouts, the unsigned / signed objects and the builders.

Every multi-byte integer is big-endian; strings and addresses are their UTF-8 bytes (an address is signed as text,
not decoded). The builders validate what the node validates at intake, so a mistake fails locally with a clear
message instead of an HTTP 400.
"""

from __future__ import annotations

import re
import time
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from .amounts import AmountLike, compare_amounts, is_valid_amount, normalize_amount, to_scaled
from .constants import MAX_MEMO_BYTES, MIN_FEE, MIN_TRANSFER, NETWORK_ID, TOKEN_CREATE_FEE, VALIDATOR_DEPOSIT, VALIDATOR_FEE, TokenOp
from .crypto import hash_preimage, i64be, len_prefixed, normalize_address, ser32

#: REST path (relative to the API base) and JSON-RPC method that accept each transaction type.
TX_ROUTES: Mapping[str, tuple[str, str]] = {
    "transfer": ("transactions/transfers", "janzeer_sendTransfer"),
    "token": ("transactions/tokens", "janzeer_sendToken"),
    "registerValidator": ("transactions/validators", "janzeer_sendRegisterValidator"),
    "exitValidator": ("transactions/exit-validators", "janzeer_sendExitValidator"),
}


# ---- signed-bytes layouts --------------------------------------------------------------------------------------------
def transaction_bytes(network_id: str, timestamp: int, fee: AmountLike, nonce: int, sender_address: str, payload: bytes) -> bytes:
    """``networkId || timestamp(8) || scaled(fee)(8) || nonce(8) || senderAddress || payload``."""
    return network_id.encode("utf-8") + i64be(timestamp) + i64be(to_scaled(fee)) + i64be(nonce) + sender_address.encode("utf-8") + payload


def transfer_payload(amount: AmountLike, recipient_address: str, data: str | None = None) -> bytes:
    """``scaled(amount)(8) || recipientAddress || (data or "")``."""
    return i64be(to_scaled(amount)) + recipient_address.encode("utf-8") + (data or "").encode("utf-8")


def register_validator_payload(amount: AmountLike, validator_key: str) -> bytes:
    """``scaled(amount)(8) || validatorKey``."""
    return i64be(to_scaled(amount)) + validator_key.encode("utf-8")


def exit_validator_payload(validator_key: str) -> bytes:
    """``validatorKey`` only (the deposit is non-refundable, so no amount)."""
    return validator_key.encode("utf-8")


def token_payload(
    op: int,
    token_id: str | None = None,
    symbol: str | None = None,
    name: str | None = None,
    decimals: int | None = None,
    cap: str | int | None = None,
    amount: str | int | None = None,
    recipient: str | None = None,
) -> bytes:
    """``op(1) || LP(tokenId) || LP(symbol) || LP(name) || int32(decimals) || LP(cap) || LP(amount) || LP(recipient)``."""
    return (
        bytes([op & 0xFF])
        + len_prefixed(token_id)
        + len_prefixed(symbol)
        + len_prefixed(name)
        + ser32(decimals or 0)
        + len_prefixed("" if cap is None else str(cap))
        + len_prefixed("" if amount is None else str(amount))
        + len_prefixed(recipient)
    )


# ---- objects ---------------------------------------------------------------------------------------------------------
@dataclass(frozen=True)
class UnsignedTx:
    """A transaction that is fully specified but not yet signed. Sign it with ``account.sign_tx(tx)``."""

    type: str
    network_id: str
    timestamp: int
    fee: str
    nonce: int
    sender_address: str
    #: the type-specific fields exactly as they go into the request body
    fields: Mapping[str, Any]
    #: the type-specific payload bytes
    payload: bytes

    def preimage(self) -> bytes:
        """The exact bytes that are hashed and signed."""
        return transaction_bytes(self.network_id, self.timestamp, self.fee, self.nonce, self.sender_address, self.payload)

    def hash(self) -> str:
        """Double-SHA256 of the preimage, lowercase hex — the transaction id."""
        return hash_preimage(self.preimage())

    def with_signature(self, signature: str, sender_public_key: str) -> SignedTx:
        """Attach a signature made elsewhere (hardware wallet, KMS). Prefer ``Account.sign_tx``."""
        return SignedTx(self, self.hash(), signature, sender_public_key)


@dataclass(frozen=True)
class SignedTx:
    """A signed transaction ready for ``client.submit(tx)`` / ``rpc.send(tx)``."""

    unsigned: UnsignedTx
    hash: str
    #: Base64 DER ECDSA signature over ``hash``
    signature: str
    #: compressed secp256k1 public key, hex
    sender_public_key: str

    @property
    def type(self) -> str:
        return self.unsigned.type

    @property
    def rest_path(self) -> str:
        return TX_ROUTES[self.unsigned.type][0]

    @property
    def rpc_method(self) -> str:
        return TX_ROUTES[self.unsigned.type][1]

    def to_body(self) -> dict[str, Any]:
        """The JSON body the node's REST endpoints and ``janzeer_send*`` methods accept. Amounts are strings."""
        u = self.unsigned
        body: dict[str, Any] = {
            "timestamp": u.timestamp,
            "fee": u.fee,
            "nonce": u.nonce,
            "hash": self.hash,
            "senderAddress": u.sender_address,
            "senderPublicKey": self.sender_public_key,
            "senderSignature": self.signature,
        }
        body.update(_fields_to_body(u.type, u.fields))
        return body


def _fields_to_body(tx_type: str, f: Mapping[str, Any]) -> dict[str, Any]:
    if tx_type == "transfer":
        body = {"amount": f["amount"], "recipientAddress": f["recipientAddress"]}
        if f.get("data") is not None:
            body["data"] = f["data"]
        return body
    if tx_type == "registerValidator":
        return {"amount": f["amount"], "validatorKey": f["validatorKey"]}
    if tx_type == "exitValidator":
        return {"validatorKey": f["validatorKey"]}
    body = {"op": f["op"]}
    for key in ("tokenId", "symbol", "name", "recipient"):
        if f.get(key):
            body[key] = f[key]
    for key in ("decimals", "cap", "amount"):
        if f.get(key) is not None:
            body[key] = f[key]
    return body


# ---- builders --------------------------------------------------------------------------------------------------------
_KEY_RE = re.compile(r"^0[23][0-9a-fA-F]{64}$")
_TOKEN_ID_RE = re.compile(r"^[0-9a-fA-F]{64}$")


def _base(sender: str, nonce: int, fee: AmountLike | None, default_fee: str, timestamp: int | None, network_id: str | None) -> tuple[str, int, str, int, str]:
    fee_s = normalize_amount(default_fee if fee is None else fee)
    if not is_valid_amount(fee_s) or compare_amounts(fee_s, MIN_FEE) < 0:
        raise ValueError(f"fee must be a decimal >= {MIN_FEE}, got {fee_s}")
    if isinstance(nonce, bool) or not isinstance(nonce, int) or nonce < 0:
        raise ValueError(f"nonce must be a non-negative integer, got {nonce!r}")
    ts = int(time.time() * 1000) if timestamp is None else timestamp
    return (network_id or NETWORK_ID, ts, fee_s, nonce, normalize_address(sender))


def _units(value: str | int, what: str) -> str:
    if isinstance(value, bool) or isinstance(value, float):
        raise TypeError(f"{what} must be an integer of base units")
    s = str(value).strip()
    if not s.isascii() or not s.isdigit():
        raise ValueError(f"{what} must be a non-negative integer of base units, got {value!r}")
    return s


def _check_key(key: str) -> str:
    if not _KEY_RE.match(key):
        raise ValueError("validator_key must be a compressed secp256k1 public key (66 hex chars)")
    return key.lower()


def _check_token_id(token_id: str) -> str:
    if not _TOKEN_ID_RE.match(token_id):
        raise ValueError("token_id must be a 64-hex transaction hash")
    return token_id.lower()


def _token_tx(base: tuple[str, int, str, int, str], **f: Any) -> UnsignedTx:
    fields = {
        "op": f["op"],
        "tokenId": f.get("token_id") or "",
        "symbol": f.get("symbol") or "",
        "name": f.get("name") or "",
        "decimals": f.get("decimals") or 0,
        "cap": f.get("cap"),
        "amount": f.get("amount"),
        "recipient": f.get("recipient"),
    }
    payload = token_payload(fields["op"], fields["tokenId"], fields["symbol"], fields["name"], fields["decimals"], fields["cap"], fields["amount"], fields["recipient"])
    return UnsignedTx("token", *base, fields, payload)


class _TokenBuilder:
    """JZT-1 token operations. Token amounts are integer base units (strings or ints), never scaled."""

    @staticmethod
    def create(*, sender: str, nonce: int, symbol: str, name: str, decimals: int = 0, cap: str | int | None = None, amount: str | int | None = None,
               fee: AmountLike | None = None, timestamp: int | None = None, network_id: str | None = None) -> UnsignedTx:
        """Create a token; the new ``tokenId`` is the transaction hash. Fee is exactly :data:`TOKEN_CREATE_FEE`."""
        b = _base(sender, nonce, fee, TOKEN_CREATE_FEE, timestamp, network_id)
        if compare_amounts(b[2], TOKEN_CREATE_FEE) != 0:
            raise ValueError(f"token create fee must be exactly {TOKEN_CREATE_FEE}")
        if isinstance(decimals, bool) or not isinstance(decimals, int) or not 0 <= decimals <= 18:
            raise ValueError("decimals must be an integer 0-18")
        if not symbol.strip() or not name.strip():
            raise ValueError("symbol and name are required")
        return _token_tx(b, op=TokenOp.CREATE, symbol=symbol.strip(), name=name.strip(), decimals=decimals,
                         cap=None if cap is None else _units(cap, "cap"), amount=None if amount is None else _units(amount, "amount"))

    @staticmethod
    def mint(*, sender: str, nonce: int, token_id: str, amount: str | int, recipient: str | None = None,
             fee: AmountLike | None = None, timestamp: int | None = None, network_id: str | None = None) -> UnsignedTx:
        b = _base(sender, nonce, fee, MIN_FEE, timestamp, network_id)
        return _token_tx(b, op=TokenOp.MINT, token_id=_check_token_id(token_id), amount=_units(amount, "amount"),
                         recipient=normalize_address(recipient) if recipient else None)

    @staticmethod
    def burn(*, sender: str, nonce: int, token_id: str, amount: str | int,
             fee: AmountLike | None = None, timestamp: int | None = None, network_id: str | None = None) -> UnsignedTx:
        b = _base(sender, nonce, fee, MIN_FEE, timestamp, network_id)
        return _token_tx(b, op=TokenOp.BURN, token_id=_check_token_id(token_id), amount=_units(amount, "amount"))

    @staticmethod
    def set_cap(*, sender: str, nonce: int, token_id: str, cap: str | int,
                fee: AmountLike | None = None, timestamp: int | None = None, network_id: str | None = None) -> UnsignedTx:
        b = _base(sender, nonce, fee, MIN_FEE, timestamp, network_id)
        return _token_tx(b, op=TokenOp.SETCAP, token_id=_check_token_id(token_id), cap=_units(cap, "cap"))

    @staticmethod
    def transfer(*, sender: str, nonce: int, token_id: str, amount: str | int, recipient: str,
                 fee: AmountLike | None = None, timestamp: int | None = None, network_id: str | None = None) -> UnsignedTx:
        b = _base(sender, nonce, fee, MIN_FEE, timestamp, network_id)
        return _token_tx(b, op=TokenOp.TRANSFER, token_id=_check_token_id(token_id), amount=_units(amount, "amount"), recipient=normalize_address(recipient))

    @staticmethod
    def raw(*, sender: str, nonce: int, op: int, token_id: str | None = None, symbol: str | None = None, name: str | None = None, decimals: int | None = None,
            cap: str | None = None, amount: str | None = None, recipient: str | None = None,
            fee: AmountLike | None = None, timestamp: int | None = None, network_id: str | None = None) -> UnsignedTx:
        """Escape hatch: any operation with raw fields (no validation beyond the payload layout)."""
        b = _base(sender, nonce, fee, TOKEN_CREATE_FEE if op == TokenOp.CREATE else MIN_FEE, timestamp, network_id)
        return _token_tx(b, op=op, token_id=token_id, symbol=symbol, name=name, decimals=decimals, cap=cap, amount=amount, recipient=recipient)


class TxBuilder:
    """Transaction builders. Each returns an :class:`UnsignedTx`; ``nonce`` comes from the node (``client.nonce``)."""

    token = _TokenBuilder

    @staticmethod
    def transfer(*, sender: str, to: str, amount: AmountLike, nonce: int, data: str | None = None,
                 fee: AmountLike | None = None, timestamp: int | None = None, network_id: str | None = None) -> UnsignedTx:
        """A native-coin transfer. Fee defaults to :data:`MIN_FEE`. With a memo the amount may be below the minimum."""
        b = _base(sender, nonce, fee, MIN_FEE, timestamp, network_id)
        amount_s = normalize_amount(amount)
        if not is_valid_amount(amount_s) or amount_s.startswith("-"):
            raise ValueError(f"amount must be a decimal with <= 8 fractional digits, got {amount_s}")
        memo = None if data is None or data == "" else data
        if memo is not None and len(memo.encode("utf-8")) > MAX_MEMO_BYTES:
            raise ValueError(f"memo exceeds {MAX_MEMO_BYTES} UTF-8 bytes")
        if memo is None and compare_amounts(amount_s, MIN_TRANSFER) < 0:
            raise ValueError(f"amount must be >= {MIN_TRANSFER} unless the transfer carries a memo")
        recipient = normalize_address(to)
        fields = {"amount": amount_s, "recipientAddress": recipient, "data": memo}
        return UnsignedTx("transfer", *b, fields, transfer_payload(amount_s, recipient, memo))

    @staticmethod
    def register_validator(*, sender: str, nonce: int, validator_key: str, amount: AmountLike | None = None,
                           fee: AmountLike | None = None, timestamp: int | None = None, network_id: str | None = None) -> UnsignedTx:
        """Register a validator node: the exact :data:`VALIDATOR_FEE` and the NON-REFUNDABLE :data:`VALIDATOR_DEPOSIT`."""
        b = _base(sender, nonce, fee, VALIDATOR_FEE, timestamp, network_id)
        if compare_amounts(b[2], VALIDATOR_FEE) != 0:
            raise ValueError(f"validator registration fee must be exactly {VALIDATOR_FEE}")
        amount_s = normalize_amount(VALIDATOR_DEPOSIT if amount is None else amount)
        if compare_amounts(amount_s, VALIDATOR_DEPOSIT) != 0:
            raise ValueError(f"validator deposit must be exactly {VALIDATOR_DEPOSIT}")
        key = _check_key(validator_key)
        return UnsignedTx("registerValidator", *b, {"amount": amount_s, "validatorKey": key}, register_validator_payload(amount_s, key))

    @staticmethod
    def exit_validator(*, sender: str, nonce: int, validator_key: str,
                       fee: AmountLike | None = None, timestamp: int | None = None, network_id: str | None = None) -> UnsignedTx:
        """Gracefully exit a validator (removed at the next epoch; the deposit stays locked)."""
        b = _base(sender, nonce, fee, MIN_FEE, timestamp, network_id)
        key = _check_key(validator_key)
        return UnsignedTx("exitValidator", *b, {"validatorKey": key}, exit_validator_payload(key))
