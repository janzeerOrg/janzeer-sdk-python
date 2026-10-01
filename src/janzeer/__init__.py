"""Official Python SDK of the Janzeer blockchain.

Wallet keys and signing, transaction builders, a REST client, JSON-RPC over HTTP and WebSocket subscriptions.
Non-custodial by construction: keys never leave your process; the node only verifies.

    from janzeer import Account, JanzeerClient, TxBuilder, wait_for_finality

    me = Account.from_mnemonic("abandon … about")
    client = JanzeerClient("https://onion.janzeer.org")
    tx = me.sign_tx(TxBuilder.transfer(sender=me.address, to="0x…", amount="1.25", nonce=client.nonce(me.address)))
    client.submit(tx)
    print(wait_for_finality(client, tx.hash)["status"])
"""

from . import mnemonic
from .account import Account
from .amounts import add_amounts, compare_amounts, format_jnz, from_scaled, is_valid_amount, normalize_amount, parse_jnz, sub_amounts, to_scaled
from .constants import (
    DECIMALS,
    LIMITS,
    MAX_MEMO_BYTES,
    MIN_FEE,
    MIN_TRANSFER,
    NETWORK_ID,
    SPEC_VERSION,
    TICKER,
    TOKEN_CREATE_FEE,
    TOKEN_OP_NAMES,
    VALIDATOR_DEPOSIT,
    VALIDATOR_FEE,
    TokenOp,
)
from .crypto import is_valid_address, normalize_address, to_checksum_address
from .errors import (
    ApiError,
    FinalityTimeoutError,
    JanzeerError,
    NetworkError,
    NonceMismatchError,
    NotFoundError,
    NotSynchronizedError,
    RateLimitedError,
    RpcError,
    RpcInvalidParamsError,
    RpcLimitError,
    RpcMethodNotFoundError,
    RpcNotFoundError,
    TxRejectedError,
    ValidationError,
)
from .helpers import asend_and_wait, await_finality, next_nonce, send_and_wait, wait_for_finality
from .rest import AsyncJanzeerClient, JanzeerClient
from .rpc import AsyncJanzeerRpc, JanzeerRpc
from .tx import SignedTx, TxBuilder, UnsignedTx
from .vault import VaultError, decrypt_vault, encrypt_vault
from .ws import JanzeerRpcWs, Subscription

__version__ = "0.1.0"

__all__ = [
    "Account", "mnemonic", "TxBuilder", "UnsignedTx", "SignedTx",
    "JanzeerClient", "AsyncJanzeerClient", "JanzeerRpc", "AsyncJanzeerRpc", "JanzeerRpcWs", "Subscription",
    "next_nonce", "wait_for_finality", "await_finality", "send_and_wait", "asend_and_wait",
    "to_scaled", "from_scaled", "format_jnz", "parse_jnz", "normalize_amount", "is_valid_amount", "compare_amounts", "add_amounts", "sub_amounts",
    "is_valid_address", "normalize_address", "to_checksum_address",
    "encrypt_vault", "decrypt_vault", "VaultError",
    "NETWORK_ID", "DECIMALS", "TICKER", "MIN_FEE", "MIN_TRANSFER", "MAX_MEMO_BYTES", "VALIDATOR_FEE", "VALIDATOR_DEPOSIT", "TOKEN_CREATE_FEE", "SPEC_VERSION", "TokenOp", "TOKEN_OP_NAMES", "LIMITS",
    "JanzeerError", "NetworkError", "ApiError", "ValidationError", "NotFoundError", "NotSynchronizedError", "RateLimitedError", "TxRejectedError", "NonceMismatchError",
    "RpcError", "RpcInvalidParamsError", "RpcNotFoundError", "RpcLimitError", "RpcMethodNotFoundError", "FinalityTimeoutError",
    "__version__",
]
