"""Watch newly finalized blocks over the WebSocket and print their height and hash.

Runs until ``MAX_BLOCKS`` blocks arrive or ``TIMEOUT`` seconds pass. Like the other examples it reads the
``JANZEER_*`` environment variables described in CONTRIBUTING; no account or credentials are needed.
"""

import asyncio
import os
from typing import Any

from janzeer import JanzeerRpcWs

NODE = os.environ.get("JANZEER_NODE_URL", "http://localhost:7019")
WS = os.environ.get("JANZEER_WS_URL", NODE)
MAX_BLOCKS = 3
TIMEOUT = 90


async def main() -> None:
    remaining = MAX_BLOCKS
    done: asyncio.Future[None] = asyncio.get_running_loop().create_future()

    def on_block(block: dict[str, Any]) -> None:
        nonlocal remaining
        print("block", block["height"], block["hash"], "txs", block["transactionsCount"])
        remaining -= 1
        if remaining <= 0 and not done.done():
            done.set_result(None)

    async with await JanzeerRpcWs.connect(WS) as ws:
        sub = await ws.subscribe_new_blocks(on_block)
        print("subscribed", sub.id, "waiting for", MAX_BLOCKS, "blocks")
        try:
            await asyncio.wait_for(done, TIMEOUT)
        except TimeoutError:
            print("timed out after", TIMEOUT, "s")
        await sub.unsubscribe()


asyncio.run(main())
