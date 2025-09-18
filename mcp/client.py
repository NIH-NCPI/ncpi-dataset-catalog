import asyncio
from fastmcp import Client

client = Client("http://localhost:8000/mcp")


async def call_tool(text: str):
    async with client:
        result = await client.call_tool("echo", {"text": text})
        print(result)


asyncio.run(call_tool("yo"))
