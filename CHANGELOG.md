# Changelog

All notable changes to this package. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)
and the package follows [Semantic Versioning](https://semver.org/).

## Unreleased

- Docs/examples: `examples/07_async_quickstart_transfer.py` and [docs/asyncio.md](docs/asyncio.md) show the end-to-end
  asyncio path (`AsyncJanzeerClient` → sign → submit → `await_finality`). (#3)

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
