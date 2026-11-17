"""Accept a payment: watch an address for a matching transfer, confirm finality, then exit."""

import asyncio
import os
import sys

from janzeer import Account, AsyncJanzeerClient, JanzeerRpcWs, TxBuilder, await_finality, compare_amounts

NODE = os.environ.get("JANZEER_NODE_URL", "http://localhost:7019")
WS = os.environ.get("JANZEER_WS_URL", NODE)
EXAMPLE_SECONDS = int(os.environ.get("EXAMPLE_SECONDS", "90"))
me = Account.from_mnemonic(
    os.environ.get(
        "JANZEER_E2E_MNEMONIC",
        "abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon about",
    )
)
recipient = os.environ.get(
    "JANZEER_E2E_RECIPIENT",
    "0x598b1301acef3baba6ce25e38dd17b723f7b98b1",
).lower()
invoice_amount = "0.5"
reference = "inv-3f9a2c"


def _first(tx, *names):
    for name in names:
        if name in tx and tx[name] is not None:
            return tx[name]
    return None


def matches_payment(tx) -> bool:
    """True only for a transfer to our recipient carrying the reference and >= amount."""
    if not isinstance(tx, dict):
        return False
    kind = _first(tx, "type", "kind", "txType")
    if kind is not None and str(kind).lower() != "transfer":
        return False
    to = _first(tx, "recipientAddress", "to", "recipient", "recipient_address")
    if to is None or str(to).lower() != recipient:
        return False
    memo = _first(tx, "data", "memo", "reference")
    if memo is None or str(memo) != reference:
        return False
    amount = _first(tx, "amount")
    if amount is None:
        return False
    try:
        return compare_amounts(amount, invoice_amount) >= 0
    except (TypeError, ValueError):
        return False


async def main() -> None:
    matched = asyncio.get_running_loop().create_future()

    def on_event(ev) -> None:
        if not matched.done() and matches_payment(ev.get("transaction") or {}):
            matched.set_result(ev)

    async with await JanzeerRpcWs.connect(WS) as ws, AsyncJanzeerClient(NODE) as client:
        sub = await ws.subscribe_address_activity([recipient], on_event)
        network_id = (await client.info())["networkId"]
        tx = me.sign_tx(
            TxBuilder.transfer(
                sender=me.address,
                to=recipient,
                amount=invoice_amount,
                nonce=await client.nonce(me.address),
                data=reference,
                network_id=network_id,
            )
        )
        await client.submit(tx)
        try:
            ev = await asyncio.wait_for(matched, EXAMPLE_SECONDS)
        except asyncio.TimeoutError:
            await sub.unsubscribe()
            print(f"no matching payment for {reference} within {EXAMPLE_SECONDS}s", file=sys.stderr)
            raise SystemExit(1) from None
        final = await await_finality(client, ev["transaction"]["hash"], timeout=EXAMPLE_SECONDS)
        if final.get("status") != "FINAL":
            await sub.unsubscribe()
            print(f"payment not final: {final.get('status')}", file=sys.stderr)
            raise SystemExit(1) from None
        print(f"paid: {reference} {invoice_amount} JNZ in block {final.get('blockHeight')}")
        await sub.unsubscribe()


asyncio.run(main())
