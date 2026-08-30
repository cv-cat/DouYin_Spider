"""Open a visible Douyin login page and save authenticated cookies to .env."""

import argparse
import asyncio

from dy_apis.login_api import DYLoginApi


async def main():
    parser = argparse.ArgumentParser(description="扫码登录抖音并把凭证保存到项目 .env")
    parser.add_argument("--url", default="https://www.douyin.com/", help="登录后要访问的抖音页面")
    parser.add_argument("--timeout", type=int, default=300, help="等待扫码秒数")
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--browser", default=None)
    args = parser.parse_args()

    login = DYLoginApi()
    auth = await login.login_grab_ticket(
        headless=args.headless,
        timeout=args.timeout,
        target_url=args.url,
        executable_path=args.browser,
    )
    print(f"登录成功，凭证已保存到：{login.save_credential(auth)}")


if __name__ == "__main__":
    asyncio.run(main())
