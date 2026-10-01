"""Chain constants. Every value mirrors the node and is pinned by the conformance vectors or the e2e flow."""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType
from typing import Final

#: ``consensus.network-id`` — bound into every signed transaction preimage (cross-network replay protection).
NETWORK_ID: Final = "janzeer"
#: Native coin decimals: amounts are scaled x10^8 into an int64 on the wire (:func:`janzeer.to_scaled`).
DECIMALS: Final = 8
#: Display ticker of the native coin.
TICKER: Final = "JNZ"
#: Minimum fee of every transaction, in JNZ.
MIN_FEE: Final = "0.01"
#: Minimum transfer amount in JNZ unless the transfer carries a memo (``data``).
MIN_TRANSFER: Final = "0.1"
#: Maximum memo (``data``) length in UTF-8 bytes.
MAX_MEMO_BYTES: Final = 256
#: Exact fee of a validator registration.
VALIDATOR_FEE: Final = "3"
#: Exact, NON-REFUNDABLE deposit of a validator registration.
VALIDATOR_DEPOSIT: Final = "2000"
#: Exact fee of a token CREATE; every other token operation pays :data:`MIN_FEE`.
TOKEN_CREATE_FEE: Final = "5"

#: The node / API / wire-protocol versions this SDK release was built and tested against.
SPEC_VERSION: Final[Mapping[str, object]] = MappingProxyType({"node": "0.1.0", "api": "1.1.0", "protocol": "3.4.0", "vectors": 2})


class TokenOp:
    """JZT-1 token operation codes carried in the ``op`` byte."""

    CREATE: Final = 0
    MINT: Final = 1
    BURN: Final = 2
    SETCAP: Final = 3
    TRANSFER: Final = 4


#: ``op`` byte -> name, as the node reports it.
TOKEN_OP_NAMES: Final = ("CREATE", "MINT", "BURN", "SETCAP", "TRANSFER")

#: Server-side limits (informational; the node enforces them).
LIMITS: Final[Mapping[str, int]] = MappingProxyType(
    {
        "page_size": 100,
        "block_range": 100,
        "wait_for_finality_ms": 60_000,
        "subscriptions_per_session": 16,
        "watched_addresses": 1000,
        "rpc_batch": 50,
        "rpc_body_bytes": 524_288,
    }
)
