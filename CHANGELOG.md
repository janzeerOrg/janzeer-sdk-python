# Changelog

All notable changes to this package. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)
and the package follows [Semantic Versioning](https://semver.org/).

## 0.1.7 — 2026-11-13

No API change. `SPEC_VERSION["node"]` is **0.1.14** (node 0.1.14: supply endpoints `/api/v1/supply`, `/supply/total`, `/supply/circulating`, and circulating supply counted the standard way; API 1.1.0 / protocol 3.4.0 unchanged, rolling upgrade).

## 0.1.6 — 2026-11-12

No API change; node pin unchanged (**0.1.13**, API 1.1.0, protocol 3.4.0).

- **Asyncio guide and example.** `examples/07_async_quickstart_transfer.py` and [docs/asyncio.md](docs/asyncio.md) show the
  end-to-end asyncio path (`AsyncJanzeerClient` → sign → submit → `await_finality`), the blocking/async name pairs and how to
  share one `httpx.AsyncClient`. Contributed by @HarshRajSinghania (#3, #4).

## 0.1.5 — 2026-11-11

No API change. `SPEC_VERSION["node"]` is **0.1.13** (node hardening release after a full review: a peer is counted only under the key it proved in the handshake, a next-slot vote no longer discards the current slot, one reward transaction per block, format checks at intake, rate limit on `/rpc/ws`; API 1.1.0 / protocol 3.4.0 unchanged, rolling upgrade).

## 0.1.4 — 2026-11-11

Reliability fixes from a code review. Node pin unchanged (**0.1.12**, API 1.1.0 / protocol 3.4.0). No API change.

- **Amounts accept ASCII digits only.** The coin-amount pattern used `\d`, which in a `str` pattern also matches Arabic-Indic and other Unicode digits: `"١٠"` was normalised, signed as 10 JNZ and sent verbatim. The other SDKs and the token path already refused it.
- **`wait_for_finality` / `await_finality` / `send_and_wait` over REST survives a dropped poll.** One transport error while polling (the transaction was already accepted) used to surface as a network error — which a caller can mistake for a failed send and resend. The REST branch now retries until the deadline, like the JSON-RPC branch.
- **WebSocket, resume after a reconnect.** A `newBlocks` stream now resumes right after the last block it delivered. It used to re-send the original `fromHeight`, so the node replayed every block again (thousands of duplicates on a long-lived stream), and a stream without `fromHeight` silently skipped the blocks committed during the outage. Blocks are delivered exactly once by height.
- **WebSocket, a failed resubscribe is retried.** A subscription whose re-creation failed (the socket dropped again, a call timed out) was removed for good with an `error` event as the only trace. It now stays registered and is re-created on the next attempt.

## 0.1.3 — 2026-11-09

No API change. `SPEC_VERSION["node"]` is **0.1.12** (node critical fix F-058: GraalVM native nodes could not sync across a block carrying a token transaction, fixed in 0.1.12 with a build-time guard; API 1.1.0 / protocol 3.4.0 unchanged).

## 0.1.2 — 2026-11-04

No API change; node pin unchanged (**0.1.11**, API 1.1.0, protocol 3.4.0).

- Examples: `examples/06_watch_new_blocks.py` streams newly finalized blocks over the WebSocket (`newBlocks`
  subscription) — contributed by [@SakarPaisen](https://github.com/SakarPaisen) (#2, closes #1). The timeout path catches
  `asyncio.TimeoutError`, which is what `asyncio.wait_for` raises on Python 3.10.

## 0.1.1 — 2026-11-01

No API change. `SPEC_VERSION["node"]` is **0.1.11** (node maintenance release: the `jz` command-line client ships in the
node bundle; `GET /info/version` now returns `version`, `apiVersion` and `protocolVersion` like `/info`; API 1.1.0 / protocol
3.4.0 unchanged).

## 0.1.0 — 2026-10-28

First release on PyPI, for node 0.1.10 (API 1.1.0, protocol 3.4.0); the source has been public since 2026-10-01 and was
verified against every node release from 0.1.0 to 0.1.10.

- Keys: BIP39 mnemonics, Janzeer seed and `m/0/0/0` derivation, addresses with the EIP-55 display form, RFC-6979
  low-S signatures.
- Transactions: transfer, validator registration and exit, JZT-1 token operations; unsigned / signed objects.
- Clients: REST and JSON-RPC over HTTP, blocking and `asyncio`; JSON-RPC over WebSocket with `newBlocks` and
  `addressActivity` subscriptions and automatic resubscription.
- Flows: `next_nonce`, `wait_for_finality`, `send_and_wait` and their async twins.
- Vault: PBKDF2-HMAC-SHA256 (250,000 rounds) + AES-256-GCM, interoperable with the TypeScript, Dart and Kotlin SDKs.
- WebSocket: a subscription is registered when its answer is read, so a notification sent right behind the answer is
  never dropped.
- Conformance: all vectors (format v2) and the 14-step end-to-end flow.
