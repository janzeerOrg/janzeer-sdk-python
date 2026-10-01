"""Client of the node's REST API (``/api/v1/``): :class:`JanzeerClient` (blocking) and :class:`AsyncJanzeerClient`.

Both expose the same methods; the async one returns awaitables. Results are the envelope ``payload`` as plain JSON
values (``dict`` / ``list`` / ``str`` / ``int`` / ``Decimal``): amounts are never floats.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable, Mapping
from typing import Any

import httpx

from . import _json
from .errors import JanzeerError, NetworkError, RateLimitedError, rest_error_from
from .tx import SignedTx

_MISSING: Any = object()


def normalize_rest_url(base_url: str) -> str:
    """``http://host:7019`` or ``…/api/v1`` -> ``…/api/v1/``."""
    u = base_url.strip().rstrip("/")
    if not u.endswith("/api/v1"):
        u += "/api/v1"
    return u + "/"


def _query(params: Mapping[str, Any] | None) -> dict[str, str]:
    out: dict[str, str] = {}
    for k, v in (params or {}).items():
        if v is None or v == "":
            continue
        out[k] = ("true" if v else "false") if isinstance(v, bool) else ",".join(v) if isinstance(v, (list, tuple)) else str(v)
    return out


def _page(page: int | None, size: int | None, sort_by: Any, sort_direction: str | None, **extra: Any) -> dict[str, Any]:
    return {"page": page, "size": size, "sortBy": sort_by, "sortDirection": sort_direction, **extra}


class _Collection:
    """``client.transfers`` and its siblings: ``list(...)`` and ``get(hash)``."""

    def __init__(self, client: _RestBase, path: str, filters: tuple[str, ...] = ()) -> None:
        self._c, self._path, self._filters = client, path, filters

    def list(self, *, page: int | None = None, size: int | None = None, sort_by: Any = None, sort_direction: str | None = None, **filters: Any) -> Any:
        """One page ``{total, list, page, pageSize, totalPages}``. Filters depend on the collection (``address``, ``unconfirmed``, ``token_id``, ``node_key``)."""
        unknown = set(filters) - set(self._filters)
        if unknown:
            raise TypeError(f"unknown filter(s) for {self._path}: {', '.join(sorted(unknown))}")
        names = {"token_id": "tokenId", "node_key": "nodeKey"}
        q = _page(page, size, sort_by, sort_direction, **{names.get(k, k): (v or None) if k == "unconfirmed" else v for k, v in filters.items()})
        return self._c._request("GET", self._path, query=q, not_found={"total": 0, "list": [], "page": 0, "pageSize": 0, "totalPages": 0})

    def get(self, hash: str) -> Any:
        """One item by hash, or ``None``."""
        return self._c._request("GET", f"{self._path}/{hash}", not_found=None)


class _Blocks:
    def __init__(self, client: _RestBase, kind: str) -> None:
        self._c, self._path = client, f"blocks/{kind}"

    def list(self, *, page: int | None = None, size: int | None = None, sort_by: Any = None, sort_direction: str | None = None) -> Any:
        return self._c._request("GET", self._path, query=_page(page, size, sort_by, sort_direction), not_found={"total": 0, "list": [], "page": 0, "pageSize": 0, "totalPages": 0})

    def get(self, hash: str) -> Any:
        return self._c._request("GET", f"{self._path}/{hash}", not_found=None)

    def previous(self, hash: str) -> Any:
        return self._c._request("GET", f"{self._path}/{hash}/previous", not_found=None)

    def next(self, hash: str) -> Any:
        return self._c._request("GET", f"{self._path}/{hash}/next", not_found=None)


class _RestBase:
    """Everything except the transport: URL, method list, response handling. Subclasses implement ``_request``."""

    def __init__(self, base_url: str, *, timeout: float = 15.0, headers: Mapping[str, str] | None = None, retry_on_rate_limit: bool = True) -> None:
        self.base_url = normalize_rest_url(base_url)
        self._timeout = timeout
        self._headers = {"Accept": "application/json", **(headers or {})}
        self._retry_429 = retry_on_rate_limit
        #: envelope of the last successful response: ``{"timestamp": …, "version": "1.1.0"}``
        self.last_envelope: dict[str, Any] | None = None
        self.transfers = _Collection(self, "transactions/transfers", ("address", "unconfirmed"))
        self.validator_txs = _Collection(self, "transactions/validators", ("address", "unconfirmed", "node_key"))
        self.exit_validator_txs = _Collection(self, "transactions/exit-validators", ("address", "unconfirmed"))
        self.token_txs = _Collection(self, "transactions/tokens", ("token_id", "unconfirmed"))
        self.rewards = _Collection(self, "transactions/rewards", ("address",))
        self.main_blocks = _Blocks(self, "main")
        self.genesis_blocks = _Blocks(self, "genesis")

    # -- transport contract ------------------------------------------------------------------------------------------
    def _request(self, method: str, path: str, *, query: Mapping[str, Any] | None = None, body: Any = _MISSING, not_found: Any = _MISSING,
                 then: Callable[[Any], Any] | None = None) -> Any:
        raise NotImplementedError

    def _prepare(self, method: str, path: str, query: Mapping[str, Any] | None, body: Any) -> dict[str, Any]:
        kw: dict[str, Any] = {"method": method, "url": self.base_url + path.lstrip("/"), "params": _query(query), "headers": dict(self._headers)}
        if body is not _MISSING:
            kw["content"] = _json.dumps(body).encode("utf-8")
            kw["headers"]["Content-Type"] = "application/json"
        return kw

    def _handle(self, res: httpx.Response, not_found: Any) -> Any:
        """Return the payload, or raise the mapped error. A :class:`RateLimitedError` is raised for the caller to retry."""
        if res.status_code == 404 and not_found is not _MISSING:
            return not_found
        parsed: Any = None
        if res.content:
            try:
                parsed = _json.loads(res.content)
            except ValueError as e:
                if res.is_success:
                    raise NetworkError(f"node returned non-JSON ({res.status_code})") from e
        if not res.is_success:
            raise rest_error_from(res.status_code, parsed, res.headers.get("Retry-After"))
        if isinstance(parsed, dict) and "payload" in parsed:
            self.last_envelope = {"timestamp": parsed.get("timestamp"), "version": str(parsed.get("version"))}
            return parsed.get("payload")
        return parsed

    # -- node --------------------------------------------------------------------------------------------------------
    def info(self) -> Any:
        """``GET info``: node key, network id, genesis hash, versions, sync status."""
        return self._request("GET", "info")

    def version(self) -> Any:
        return self._request("GET", "info/version")

    def uptime(self) -> Any:
        """Milliseconds since the node started."""
        return self._request("GET", "info/uptime")

    def genesis(self) -> Any:
        """The network's public genesis document."""
        return self._request("GET", "info/genesis")

    def explorer_info(self) -> Any:
        return self._request("GET", "explorer/info")

    # -- wallet ------------------------------------------------------------------------------------------------------
    def balance(self, address: str) -> Any:
        """Spendable balance (committed minus pending debits) as a decimal string; ``"0"`` for an unknown address."""
        return self._request("GET", f"wallets/{address}", not_found="0", then=_json.decimal_str)

    def nonce(self, address: str) -> Any:
        """The next nonce to sign with (committed nonce + pending count); ``0`` for an unknown address."""
        return self._request("GET", f"wallets/{address}/nonce", not_found=0, then=int)

    # -- transactions ------------------------------------------------------------------------------------------------
    def submit(self, tx: SignedTx) -> Any:
        """Submit a signed transaction (HTTP 201) and return the node's echo. Raises :class:`TxRejectedError` / :class:`NonceMismatchError`."""
        return self._request("POST", tx.rest_path, body=tx.to_body())

    def receipt(self, hash: str) -> Any:
        """Execution receipt of a committed transaction (``None`` if unknown or still pending)."""
        return self._request("GET", f"transactions/{hash}/receipt", not_found=None)

    # -- validators / tokens -----------------------------------------------------------------------------------------
    def validators(self, *, active: bool = False, page: int | None = None, size: int | None = None) -> Any:
        """Every registered validator, or with ``active=True`` the current epoch's producer set."""
        return self._request("GET", "validators/active" if active else "validators", query=_page(page, size, None, None), not_found={"total": 0, "list": []})

    def tokens(self, *, page: int | None = None, size: int | None = None) -> Any:
        return self._request("GET", "tokens", query=_page(page, size, None, None), not_found={"total": 0, "list": []})

    def token(self, token_id: str) -> Any:
        return self._request("GET", f"tokens/{token_id}", not_found=None)

    def token_holders(self, token_id: str, *, page: int | None = None, size: int | None = None) -> Any:
        return self._request("GET", f"tokens/{token_id}/holders", query=_page(page, size, None, None), not_found={"total": 0, "list": []})

    def token_balances(self, address: str, *, page: int | None = None, size: int | None = None) -> Any:
        return self._request("GET", f"tokens/balances/{address}", query=_page(page, size, None, None), not_found={"total": 0, "list": []})

    # -- raw ---------------------------------------------------------------------------------------------------------
    def get(self, path: str, query: Mapping[str, Any] | None = None, *, not_found: Any = _MISSING) -> Any:
        """``GET path`` -> the envelope payload. Pass ``not_found=`` to turn a 404 into a value."""
        return self._request("GET", path, query=query, not_found=not_found)

    def post(self, path: str, body: Any) -> Any:
        """``POST path`` with a JSON body -> the envelope payload."""
        return self._request("POST", path, body=body)


class JanzeerClient(_RestBase):
    """Blocking REST client. ``JanzeerClient("https://onion.janzeer.org")`` — a missing ``/api/v1/`` is added."""

    def __init__(self, base_url: str, *, timeout: float = 15.0, headers: Mapping[str, str] | None = None, retry_on_rate_limit: bool = True,
                 http: httpx.Client | None = None) -> None:
        super().__init__(base_url, timeout=timeout, headers=headers, retry_on_rate_limit=retry_on_rate_limit)
        self._http = http or httpx.Client(timeout=timeout, follow_redirects=True)

    def _request(self, method: str, path: str, *, query: Mapping[str, Any] | None = None, body: Any = _MISSING, not_found: Any = _MISSING,
                 then: Callable[[Any], Any] | None = None) -> Any:
        for attempt in (0, 1):
            try:
                res = self._http.request(**self._prepare(method, path, query, body))
            except httpx.HTTPError as e:
                raise NetworkError(f"cannot reach the node at {self.base_url}: {e}") from e
            try:
                out = self._handle(res, not_found)
            except RateLimitedError as e:
                if self._retry_429 and attempt == 0:
                    time.sleep(e.retry_after)
                    continue
                raise
            return then(out) if then and out is not not_found else out
        raise JanzeerError("unreachable")  # pragma: no cover

    def validate_address(self, address: str) -> bool:
        """Server-side address validation (shape + EIP-55)."""
        try:
            self.post("wallets/validateAddress", {"address": address})
            return True
        except NetworkError:
            raise
        except JanzeerError:
            return False

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> JanzeerClient:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


class AsyncJanzeerClient(_RestBase):
    """Async REST client: the same methods, each returning an awaitable."""

    def __init__(self, base_url: str, *, timeout: float = 15.0, headers: Mapping[str, str] | None = None, retry_on_rate_limit: bool = True,
                 http: httpx.AsyncClient | None = None) -> None:
        super().__init__(base_url, timeout=timeout, headers=headers, retry_on_rate_limit=retry_on_rate_limit)
        self._http = http or httpx.AsyncClient(timeout=timeout, follow_redirects=True)

    async def _request(self, method: str, path: str, *, query: Mapping[str, Any] | None = None, body: Any = _MISSING, not_found: Any = _MISSING,
                       then: Callable[[Any], Any] | None = None) -> Any:
        for attempt in (0, 1):
            try:
                res = await self._http.request(**self._prepare(method, path, query, body))
            except httpx.HTTPError as e:
                raise NetworkError(f"cannot reach the node at {self.base_url}: {e}") from e
            try:
                out = self._handle(res, not_found)
            except RateLimitedError as e:
                if self._retry_429 and attempt == 0:
                    await asyncio.sleep(e.retry_after)
                    continue
                raise
            return then(out) if then and out is not not_found else out
        raise JanzeerError("unreachable")  # pragma: no cover

    async def validate_address(self, address: str) -> bool:
        try:
            await self.post("wallets/validateAddress", {"address": address})
            return True
        except NetworkError:
            raise
        except JanzeerError:
            return False

    async def aclose(self) -> None:
        await self._http.aclose()

    async def __aenter__(self) -> AsyncJanzeerClient:
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.aclose()
