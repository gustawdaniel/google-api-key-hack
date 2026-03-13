import asyncio
from curl_cffi import requests
async def main():
    async with requests.AsyncSession(impersonate="chrome110") as s:
        print(dir(s.get))
        # we can just use regular sync session + asyncio.to_thread if we want iter_content
asyncio.run(main())
