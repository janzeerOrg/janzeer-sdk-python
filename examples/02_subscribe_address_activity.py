"""Watch an address over the WebSocket, send it a transfer, and print the notification."""

import asyncio
import os

from janzeer import Account, AsyncJanzeerClient, JanzeerRpcWs, TxBuilder

NODE = os.environ.get("JANZEER_NODE_URL", "http://localhost:7019")
WS = os.environ.get("JANZEER_WS_URL", NODE)
me = Account.from_mnemonic(os.environ.get("JANZEER_E2E_MNEMONIC", "abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon about"))
to = os.environ.get("JANZEER_E2E_RECIPIENT", "0x598b1301acef3baba6ce25e38dd17b723f7b98b1")


async def main() -> None:
    got: asyncio.Future[dict] = asyncio.get_running_loop().create_future()
    async with await JanzeerRpcWs.connect(WS) as ws, AsyncJanzeerClient(NODE) as client:
        sub = await ws.subscribe_address_activity([to], lambda ev: got.done() or got.set_result(ev))
        print("subscribed", sub.id)
        network_id = (await client.info())["networkId"]
        tx = me.sign_tx(TxBuilder.transfer(sender=me.address, to=to, amount="0.5", nonce=await client.nonce(me.address), network_id=network_id))
        await client.submit(tx)
        ev = await asyncio.wait_for(got, 90)
        print("block", ev["blockHeight"], "tx", ev["transaction"]["hash"], "amount", ev["transaction"]["amount"])
        await sub.unsubscribe()


asyncio.run(main())
