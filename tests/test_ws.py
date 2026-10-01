"""The WebSocket client against a local server that behaves like the node."""

import asyncio
import json

import websockets

from janzeer import JanzeerRpcWs, RpcNotFoundError

ADDR = "0x74d2bedc03ae5deb6fc63fbf7bb87e86f034b274"
NOTIFY = {"jsonrpc": "2.0", "method": "janzeer_subscription", "params": {"subscription": "00112233aabbccdd", "kind": "addressActivity",
                                                                          "result": {"blockHeight": 7, "blockHash": "cd", "transaction": {"hash": "ab", "status": "FINAL"}}}}


async def serve(handler):
    server = await websockets.serve(handler, "127.0.0.1", 0)
    return server, f"ws://127.0.0.1:{server.sockets[0].getsockname()[1]}"


async def test_calls_errors_and_a_notification_right_behind_the_subscribe_answer():
    connections = 0

    async def node(ws):
        nonlocal connections
        connections += 1
        first = connections == 1
        async for raw in ws:
            q = json.loads(raw)
            if q["method"] == "janzeer_getTip":
                await ws.send(json.dumps({"jsonrpc": "2.0", "id": q["id"], "result": {"height": 42}}))
            elif q["method"] == "janzeer_getToken":
                await ws.send(json.dumps({"jsonrpc": "2.0", "id": q["id"], "error": {"code": -32000, "message": "token not found"}}))
            elif q["method"] == "janzeer_subscribe":
                # the answer and the first notification in ONE frame batch: nothing may be lost in between
                await ws.send(json.dumps([{"jsonrpc": "2.0", "id": q["id"], "result": "00112233aabbccdd"}, NOTIFY]))
                if first:
                    await ws.close()          # drop the first connection: the client must come back and resubscribe
            else:
                await ws.send(json.dumps({"jsonrpc": "2.0", "id": q["id"], "result": True}))

    server, url = await serve(node)
    events, got = [], asyncio.Queue()
    try:
        ws = await JanzeerRpcWs.connect(url, reconnect_delay=0.02, on_event=lambda e: events.append(e["type"]))
        assert (await ws.get_tip())["height"] == 42
        try:
            await ws.get_token("ab")
            raise AssertionError("expected RpcNotFoundError")
        except RpcNotFoundError as e:
            assert e.code == -32000
        sub = await ws.subscribe_address_activity([ADDR.upper().replace("0X", "0x")], got.put_nowait)
        assert sub.id == "00112233aabbccdd"
        for _ in range(2):                    # one before the drop, one after the automatic resubscription
            ev = await asyncio.wait_for(got.get(), 5)
            assert ev["blockHeight"] == 7 and ev["transaction"]["hash"] == "ab"
        for _ in range(100):
            if "resubscribed" in events:
                break
            await asyncio.sleep(0.02)
        assert "resubscribed" in events and connections == 2
        assert await sub.unsubscribe() is True
        await ws.close()
    finally:
        server.close()
        await server.wait_closed()


async def test_async_handlers_are_awaited():
    async def node(ws):
        async for raw in ws:
            q = json.loads(raw)
            await ws.send(json.dumps([{"jsonrpc": "2.0", "id": q["id"], "result": "00112233aabbccdd"}, NOTIFY]))

    server, url = await serve(node)
    done = asyncio.Event()

    async def handler(ev):
        await asyncio.sleep(0)
        done.set()

    try:
        async with await JanzeerRpcWs.connect(url, reconnect=False) as ws:
            await ws.subscribe_address_activity([ADDR], handler)
            await asyncio.wait_for(done.wait(), 5)
    finally:
        server.close()
        await server.wait_closed()
