import asyncio
import sys
import websockets

async def main():
    port = sys.argv[1] if len(sys.argv) > 1 else "8000"
    token = sys.argv[2]
    uri = f"ws://127.0.0.1:{port}/ws/notifications?token={token}"
    async with websockets.connect(uri) as ws:
        print(f"Connected to instance on port {port}. Waiting for notifications...")
        async for message in ws:
            print(f"\n>>> [port {port}] RECEIVED: {message}\n")

asyncio.run(main())