"""Open Douyin in a visible browser using DY_COOKIES from .env."""

import argparse
import asyncio
import os

from dotenv import load_dotenv
from playwright.async_api import async_playwright


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("url")
    parser.add_argument("--timeout", type=int, default=300)
    args = parser.parse_args()
    load_dotenv()
    cookie_str = os.getenv("DY_COOKIES", "").strip().strip("'\"")
    cookies = []
    for part in cookie_str.split(";"):
        name, separator, value = part.strip().partition("=")
        if separator and name:
            cookies.append({"name": name, "value": value, "domain": ".douyin.com", "path": "/"})

    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=False)
        context = await browser.new_context()
        await context.add_cookies(cookies)
        page = await context.new_page()
        await page.goto(args.url)
        await page.wait_for_timeout(args.timeout * 1000)
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
