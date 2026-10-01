"""Error hierarchy. Every error raised by the SDK extends :class:`JanzeerError`.

A transaction the node refuses is a :class:`TxRejectedError` whichever transport carried it (REST 400 with a ``type``,
or JSON-RPC ``-32001``), and a nonce problem is always a :class:`NonceMismatchError`, so callers branch on the class,
never on message strings.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

_NONCE_RE = re.compile(r"Invalid nonce for (0x[0-9a-fA-F]{40}): expected (\d+), got (\d+)")


class JanzeerError(Exception):
    """Base class of every SDK error."""


class NetworkError(JanzeerError):
    """The node could not be reached, the response was not JSON, or the socket died."""


class TxRejectedError(JanzeerError):
    """The node refused a transaction at intake (validation / mempool rule)."""

    def __init__(self, message: str, type: str | None, transport: str, http_status: int | None = None, rpc_code: int | None = None) -> None:
        super().__init__(message)
        #: the node's ``ExceptionType`` (``INCORRECT_SIGNATURE``, ``INSUFFICIENT_BALANCE``, …) or ``UNKNOWN``
        self.type = type or "UNKNOWN"
        self.transport = transport
        self.http_status = http_status
        self.rpc_code = rpc_code


class NonceMismatchError(TxRejectedError):
    """The nonce is not the sender's next nonce: refresh it (``client.nonce(address)``) and rebuild."""

    def __init__(self, message: str, address: str | None, expected: int | None, got: int | None, transport: str,
                 http_status: int | None = None, rpc_code: int | None = None) -> None:
        super().__init__(message, "INVALID_NONCE", transport, http_status, rpc_code)
        self.address, self.expected, self.got = address, expected, got

    @classmethod
    def from_message(cls, message: str, transport: str, http_status: int | None = None, rpc_code: int | None = None) -> NonceMismatchError | None:
        m = _NONCE_RE.search(message)
        return cls(message, m.group(1).lower(), int(m.group(2)), int(m.group(3)), transport, http_status, rpc_code) if m else None


class ApiError(JanzeerError):
    """Any other REST error (``{status, message, type?}`` payload)."""

    def __init__(self, status: int, message: str, type: str | None = None, body: Any = None) -> None:
        super().__init__(message)
        self.status, self.type, self.body = status, type, body


class ValidationError(ApiError):
    """Request-body validation failed (400 with a list of ``{message}``)."""

    def __init__(self, messages: list[str], body: Any) -> None:
        super().__init__(400, "; ".join(messages) or "validation failed", None, body)
        self.messages = messages


class NotFoundError(ApiError):
    """HTTP 404."""


class NotSynchronizedError(JanzeerError):
    """The node is still syncing (REST 400 "Blockchain is synchronizing" / RPC ``-32002``); retry shortly."""

    def __init__(self, message: str, transport: str) -> None:
        super().__init__(message)
        self.transport = transport


class RateLimitedError(JanzeerError):
    """HTTP 429 / RPC ``-32004``; ``retry_after`` in seconds from the ``Retry-After`` header (default 1)."""

    def __init__(self, message: str, retry_after: float, transport: str) -> None:
        super().__init__(message)
        self.retry_after, self.transport = retry_after, transport


class RpcError(JanzeerError):
    """A JSON-RPC error that is not a transaction rejection."""

    def __init__(self, code: int, message: str, data: Any = None) -> None:
        super().__init__(message)
        self.code, self.data = code, data


class RpcInvalidParamsError(RpcError):
    """``-32602`` — the node could not bind the parameters (``data`` lists field messages)."""


class RpcNotFoundError(RpcError):
    """``-32000`` — block / transaction / token / validator does not exist."""


class RpcLimitError(RpcError):
    """``-32003`` — a range or timeout exceeds the server cap."""


class RpcMethodNotFoundError(RpcError):
    """``-32601``."""


class FinalityTimeoutError(JanzeerError):
    """Raised by ``wait_for_finality`` when the deadline passes; ``last`` is the most recent view (or ``None``)."""

    def __init__(self, hash: str, last: Mapping[str, Any] | None) -> None:
        super().__init__(f"transaction {hash} not final within the deadline (last status: {(last or {}).get('status', 'unknown')})")
        self.hash, self.last = hash, last


RPC_REJECTED, RPC_NOT_SYNCHRONIZED, RPC_RATE_LIMITED = -32001, -32002, -32004
_RPC_CLASSES = {-32602: RpcInvalidParamsError, -32000: RpcNotFoundError, -32003: RpcLimitError, -32601: RpcMethodNotFoundError}


def rpc_error_from(err: Mapping[str, Any], transport: str = "rpc") -> JanzeerError:
    """Map a JSON-RPC ``error`` object to the SDK error hierarchy."""
    code = int(err.get("code", -32603))
    message = str(err.get("message") or f"RPC error {code}")
    data = err.get("data")
    if code == RPC_REJECTED:
        type_ = data.get("type") if isinstance(data, Mapping) else None
        nonce = NonceMismatchError.from_message(message, transport, None, code)
        if nonce:
            return nonce
        if type_ == "INVALID_NONCE":
            return NonceMismatchError(message, None, None, None, transport, None, code)
        return TxRejectedError(message, type_, transport, None, code)
    if code == RPC_NOT_SYNCHRONIZED:
        return NotSynchronizedError(message, transport)
    if code == RPC_RATE_LIMITED:
        return RateLimitedError(message, 1.0, transport)
    return _RPC_CLASSES.get(code, RpcError)(code, message, data)


def rest_error_from(status: int, body: Any, retry_after: str | None = None) -> JanzeerError:
    """Map a non-2xx REST response. Rule: a body with ``payload`` -> use it (the envelope wraps errors too); else the body itself."""
    p = body["payload"] if isinstance(body, Mapping) and "payload" in body else body
    if status == 429:
        try:
            seconds = float(retry_after) if retry_after else 1.0
        except ValueError:
            seconds = 1.0
        return RateLimitedError((p.get("message") if isinstance(p, Mapping) else None) or "Rate limit exceeded", seconds, "rest")
    if isinstance(p, list):
        return ValidationError([str(x.get("message")) if isinstance(x, Mapping) and "message" in x else str(x) for x in p], p)
    message = (p.get("message") if isinstance(p, Mapping) and isinstance(p.get("message"), str) else None) or f"Request failed ({status})"
    type_ = p.get("type") if isinstance(p, Mapping) and isinstance(p.get("type"), str) else None
    if status == 404:
        return NotFoundError(status, message, type_, p)
    if status == 400:
        if message == "Blockchain is synchronizing":
            return NotSynchronizedError(message, "rest")
        nonce = NonceMismatchError.from_message(message, "rest", status)
        if nonce:
            return nonce
        if type_ == "INVALID_NONCE":
            return NonceMismatchError(message, None, None, None, "rest", status)
        if type_:
            return TxRejectedError(message, type_, "rest", status)
    return ApiError(status, message, type_, p)
