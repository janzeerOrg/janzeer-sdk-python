# Changelog

All notable changes to this package. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)
and the package follows [Semantic Versioning](https://semver.org/).

## 0.1.0 — 2026-10-01

First release, for node 0.1.0 (API 1.1.0, protocol 3.4.0).

- Keys: BIP39 mnemonics, Janzeer seed and `m/0/0/0` derivation, addresses with the EIP-55 display form, RFC-6979
  low-S signatures.
- Transactions: transfer, validator registration and exit, JZT-1 token operations; unsigned / signed objects.
- Clients: REST and JSON-RPC over HTTP, blocking and `asyncio`; JSON-RPC over WebSocket with `newBlocks` and
  `addressActivity` subscriptions and automatic resubscription.
- Flows: `next_nonce`, `wait_for_finality`, `send_and_wait` and their async twins.
- Vault: PBKDF2-HMAC-SHA256 (250,000 rounds) + AES-256-GCM, interoperable with the TypeScript, Dart and Kotlin SDKs.
- Conformance: all vectors (format v2) and the 14-step end-to-end flow.
