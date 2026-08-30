from __future__ import annotations

import asyncio
import importlib.util
from pathlib import Path

from playwright.async_api import async_playwright


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "clean_douyin_gender_playwright.py"
SPEC = importlib.util.spec_from_file_location("gender_tool", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


CASES = (
    (
        "male-color-first",
        """<div data-e2e='user-detail'><span class='rTzhSEM4'>
        <svg><path fill='#168EF9'></path></svg><span>女</span></span></div>""",
        "男",
        "svg-color",
    ),
    (
        "female-color-first",
        """<div data-e2e='user-detail'><span class='rTzhSEM4'>
        <svg><g stroke='#F5588E'><path></path></g></svg><span>男</span></span></div>""",
        "女",
        "svg-color",
    ),
    (
        "text-fallback",
        """<div data-e2e='user-detail'><span class='rTzhSEM4'>
        <svg><path fill='#999999'></path></svg><span>女</span></span></div>""",
        "女",
        ".rTzhSEM4",
    ),
)


async def main() -> None:
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(channel="msedge", headless=True)
        page = await browser.new_page()
        for name, html, expected_gender, expected_selector in CASES:
            await page.set_content(html)
            gender, selector, evidence = await MODULE.exact_gender_from_profile(page, 0)
            assert gender == expected_gender, (name, gender, selector, evidence)
            assert expected_selector in selector, (name, gender, selector, evidence)
            print(f"{name}: {gender} | {selector} | {evidence}")
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
