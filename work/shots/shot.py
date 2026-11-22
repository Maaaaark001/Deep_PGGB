import asyncio, pathlib
from playwright.async_api import async_playwright

async def main():
    out = pathlib.Path("work/shots"); out.mkdir(parents=True, exist_ok=True)
    async with async_playwright() as p:
        b = await p.chromium.launch(channel="msedge")
        pg = await b.new_page(viewport={"width": 1440, "height": 900}, device_scale_factor=2)
        await pg.goto("http://127.0.0.1:8099/", wait_until="networkidle")
        await pg.wait_for_timeout(1800)
        await pg.screenshot(path=str(out / "workbench_1440.png"))
        await b.close()

asyncio.run(main())
print("shot ok")
