import asyncio
import websockets

async def handle_connection(websocket):
    print("客户端已连接")
    try:
        await websocket.send("你好！我是Python WebSocket服务器")
        async for message in websocket:
            print(f"收到客户端消息: {message}")
            await websocket.send(f"服务器回复: {message}")
    except websockets.exceptions.ConnectionClosed:
        print("客户端断开连接")

async def main():
    # 绑定到 0.0.0.0 并明确指定 WebSocket 子协议
    async with websockets.serve(
        handle_connection, 
        "0.0.0.0",  # 允许外部访问
        8765,
        ping_interval=None  # 禁用自动 Ping/Pong（可选）
    ):
        print("WebSocket 服务器已启动，端口 8765")
        await asyncio.Future()  # 永久运行

if __name__ == "__main__":
    asyncio.run(main())  # 正确启动事件循环