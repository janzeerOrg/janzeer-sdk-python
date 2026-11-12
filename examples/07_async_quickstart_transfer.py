"""Send a transfer and wait until it is final, on the asyncio path.

Reads the JANZEER_* environment (see CONTRIBUTING.md).
"""

import asyncio
import os

from janzeer import Account, AsyncJanzeerClient, AsyncJanzeerRpc, TxBuilder, await_finality, format_jnz

NODE = os.environ.get("JANZEER_NODE_URL", "http://localhost:7019")
RPC_URL = os.environ.get("JANZEER_RPC_URL", NODE)


async def main() -> None:
    async with AsyncJanzeerClient(NODE) as client, AsyncJanzeerRpc(RPC_URL) as rpc:
        me = Account.from_mnemonic(
            os.environ.get(
                "JANZEER_E2E_MNEMONIC",
                "abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon about",
            )
        )
        to = os.environ.get("JANZEER_E2E_RECIPIENT", "0x598b1301acef3baba6ce25e38dd17b723f7b98b1")

        info = await client.info()
        print(f"node {info['version']} on network {info['networkId']}")
        print(me.checksum_address, format_jnz(await client.balance(me.address)))

        tx = me.sign_tx(
            TxBuilder.transfer(
                sender=me.address,
                to=to,
                amount="1.25",
                data="hello from python (async)",
                nonce=await client.nonce(me.address),
                network_id=info["networkId"],
            )
        )
        await client.submit(tx)
        print("submitted", tx.hash)
        final = await await_finality(rpc, tx.hash)
        print("final in block", final["blockHeight"], "| balance now", format_jnz(await client.balance(me.address)))


if __name__ == "__main__":
    asyncio.run(main())
