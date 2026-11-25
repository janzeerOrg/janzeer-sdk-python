"""Accept a payment: watch an address for a matching transfer, confirm finality, then exit."""

import asyncio
import os
import secrets
import sys
from typing import Any

from janzeer import Account, AsyncJanzeerClient, JanzeerRpcWs, TxBuilder, await_finality, compare_amounts

NODE = os.environ.get("JANZEER_NODE_URL", "http://localhost:7019")
WS = os.environ.get("JANZEER_WS_URL", NODE)
TIMEOUT = int(os.environ.get("EXAMPLE_SECONDS", "90"))
me = Account.from_mnemonic(
    os.environ.get(
        "JANZEER_E2E_MNEMONIC",
        "abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon about",
    )
)
to = os.environ.get("JANZEER_E2E_RECIPIENT", "0x598b1301acef3baba6ce25e38dd17b723f7b98b1")
invoice_amount = "0.5"
reference = f"inv-{secrets.token_hex(3)}"


def is_match(tx: dict[str, Any]) -> bool:
    return (
        tx.get("type") == "transfer"
        and str(tx.get("recipientAddress", "")).lower() == to.lower()
        and tx.get("data") == reference
        and compare_amounts(tx.get("amount", "0"), invoice_amount) >= 0
    )


async def main() -> None:
    matched: asyncio.Future[dict[str, Any]] = asyncio.get_running_loop().create_future()

    def on_event(ev: dict[str, Any]) -> None:
        tx = ev.get("transaction") or {}
        if not matched.done() and is_match(tx):
            matched.set_result(ev)

    async with await JanzeerRpcWs.connect(WS) as ws, AsyncJanzeerClient(NODE) as client:
        sub = await ws.subscribe_address_activity([to], on_event)
        try:
            network_id = (await client.info())["networkId"]
            tx = me.sign_tx(
                TxBuilder.transfer(
                    sender=me.address,
                    to=to,
                    amount=invoice_amount,
                    nonce=await client.nonce(me.address),
                    data=reference,
                    network_id=network_id,
                )
            )
            await client.submit(tx)
            try:
                ev = await asyncio.wait_for(matched, TIMEOUT)
            except asyncio.TimeoutError:
                print(f"no matching payment for {reference} within {TIMEOUT}s", file=sys.stderr)
                raise SystemExit(1) from None
            final = await await_finality(client, ev["transaction"]["hash"], timeout=float(TIMEOUT))
            if final.get("status") != "FINAL":
                print(f"payment not final: {final.get('status')}", file=sys.stderr)
                raise SystemExit(1)
            print(f"paid: {reference} {invoice_amount} JNZ in block {final.get('blockHeight')}")
        finally:
            await sub.unsubscribe()


asyncio.run(main())
