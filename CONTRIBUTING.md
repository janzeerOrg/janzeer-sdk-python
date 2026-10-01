# Contributing

```bash
python -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"
ruff check . && mypy && pytest          # lint, types, unit tests + conformance vectors (no network)
python -m build                         # sdist + wheel in dist/
```

## End-to-end tests and examples

They need a running Janzeer network with the faucet-funded test wallet. With the private node repository checked out
next to the conformance kit:

```bash
../sdk_conformance/e2e/node-up.sh            # starts the 4-anchor dev net
eval "$(../sdk_conformance/e2e/node-up.sh --env)"
pytest -m e2e                                # tests/e2e — the 14-step SPEC flow
for f in examples/*.py; do python "$f"; done
../sdk_conformance/e2e/node-down.sh
```

Against any other network set `JANZEER_NODE_URL`, `JANZEER_RPC_URL`, `JANZEER_WS_URL`, `JANZEER_E2E_MNEMONIC`
(a funded wallet) and `JANZEER_E2E_RECIPIENT` yourself.

## Conformance vectors

`tests/vectors/` is a vendored copy of `sdk_conformance/vectors/`. Never edit it by hand: `sdk_conformance/sync.sh
--regen` regenerates the vectors from the node and copies them here; `sync.sh --check` (and CI, through the
`SHA256SUMS` in that folder) fails on drift.

## Style

- Amounts are decimal strings at the API boundary; never `float`, and no arithmetic on coin values outside
  `janzeer.amounts`.
- Every new node method gets a wrapper in `rpc.py` or `rest.py`, a unit test with a mocked transport, and a line in
  `CHANGELOG.md`.
- Public API says *validator*; the node's internal word *promoter* does not appear in it.
