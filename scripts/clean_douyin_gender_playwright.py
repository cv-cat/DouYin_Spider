from __future__ import annotations

import argparse
import asyncio
import json
import shutil
import sys
import time
from datetime import datetime
from pathlib import Path

import yaml
from playwright.async_api import Error as PlaywrightError
from playwright.async_api import TimeoutError as PlaywrightTimeoutError
from playwright.async_api import async_playwright

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="backslashreplace")


DEFAULT_YAML = Path(r"E:\SVN\项目17-DouYin_Spider\datas\douyin_comments_7672652235175692729_by_ip.yml")
PROFILE_SELECTORS = (
    "[data-e2e='user-detail'] .rTzhSEM4",
    "#user_detail_element .rTzhSEM4",
    "[data-e2e='user-info'] .rTzhSEM4",
    ".rTzhSEM4",
)
GENDER_ICON_SELECTORS = (
    "[data-e2e='user-detail'] .rTzhSEM4",
    "#user_detail_element .rTzhSEM4",
    "[data-e2e='user-info'] .rTzhSEM4",
)
GENDER_ICON_SELECTORS = (
    "[data-e2e='user-detail'] .rTzhSEM4",
    "#user_detail_element .rTzhSEM4",
    "[data-e2e='user-info'] .rTzhSEM4",
)
PROFILE_HEADER_SELECTORS = (
    "[data-e2e='user-info']",
    "[data-e2e='user-detail']",
    "#user_detail_element",
)
AUTH_COOKIE_NAMES = {
    "sessionid",
    "sessionid_ss",
    "sid_guard",
    "sid_tt",
    "uid_tt",
    "uid_tt_ss",
}
MALE_SVG_FILL = "#168EF9"
FEMALE_SVG_STROKE = "#F5588E"


def spaced_yaml(text: str) -> str:
    output: list[str] = []
    seen_in_section = False
    for line in text.splitlines():
        if line in {"保留评论:", "待人工复核评论:", "删除审计:"}:
            output.extend(["", ""])
            seen_in_section = False
        if line.startswith("- 日期:"):
            if seen_in_section:
                while output and output[-1] == "":
                    output.pop()
                output.extend(["", ""])
            seen_in_section = True
        output.append(line)
    return "\n".join(output) + "\n"


def save_payload(path: Path, payload: dict) -> None:
    rendered = yaml.safe_dump(payload, allow_unicode=True, sort_keys=False, width=120)
    path.write_text(spaced_yaml(rendered), encoding="utf-8")


def save_checkpoint(path: Path, checkpoint: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(checkpoint, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


async def exact_gender_from_profile(page, wait_ms: int) -> tuple[str, str, str]:
    await page.wait_for_timeout(wait_ms)

    # First priority: Douyin's public gender icon color. Keep the search scoped
    # to the small profile metadata chips; do not scan arbitrary page SVGs.
    for selector in GENDER_ICON_SELECTORS:
        nodes = page.locator(selector)
        for index in range(min(await nodes.count(), 8)):
            node = nodes.nth(index)
            if not await node.is_visible():
                continue
            svg_colors = await node.locator("svg").evaluate_all(
                "svgs => svgs.flatMap(svg => [svg, ...svg.querySelectorAll('*')])"
                ".flatMap(el => ['fill', 'stroke'].map(attribute => ({"
                " attribute, value: (el.getAttribute(attribute) || '').trim().toUpperCase()"
                "}))).filter(item => item.value)"
            )
            male_match = any(
                item.get("attribute") == "fill" and item.get("value") == MALE_SVG_FILL
                for item in svg_colors
            )
            female_match = any(
                item.get("attribute") == "stroke" and item.get("value") == FEMALE_SVG_STROKE
                for item in svg_colors
            )
            # A single icon should never contain both signatures. If it does,
            # skip color inference and let the independent text fallback decide.
            if male_match != female_match:
                gender = "男" if male_match else "女"
                evidence = f"fill={MALE_SVG_FILL}" if male_match else f"stroke={FEMALE_SVG_STROKE}"
                return gender, f"{selector} svg-color", evidence

    # Second priority: the previous exact visible text method.
    for selector in GENDER_ICON_SELECTORS:
        nodes = page.locator(selector)
        for index in range(min(await nodes.count(), 8)):
            node = nodes.nth(index)
            if not await node.is_visible():
                continue
            labels = await node.locator("span").evaluate_all(
                "els => els.filter(el => {"
                " const r=el.getBoundingClientRect(); const s=getComputedStyle(el);"
                " return r.width>0 && r.height>0 && s.display!=='none' && s.visibility!=='hidden';"
                "}).map(el => (el.innerText || el.textContent || '').trim())"
            )
            exact = [text for text in labels if text in {"男", "女"}]
            if len(set(exact)) == 1:
                return exact[0], selector, " | ".join(text for text in labels if text)[:300]

    # Obfuscated class names can change. This fallback remains scoped to the
    # public profile header and still requires an independent visible span.
    for selector in PROFILE_HEADER_SELECTORS:
        header = page.locator(selector).first
        if not await header.count() or not await header.is_visible():
            continue
        labels = await header.locator("span").evaluate_all(
            "els => els.filter(el => {"
            " const r=el.getBoundingClientRect(); const s=getComputedStyle(el);"
            " return r.width>0 && r.height>0 && s.display!=='none' && s.visibility!=='hidden';"
            "}).map(el => (el.innerText || el.textContent || '').trim())"
        )
        exact = [text for text in labels if text in {"男", "女"}]
        if len(set(exact)) == 1:
            return exact[0], f"{selector} exact-span", " | ".join(text for text in labels if text)[:300]

    header = page.locator("[data-e2e='user-detail'], #user_detail_element").first
    if await header.count() and await header.is_visible():
        lines = {line.strip() for line in (await header.inner_text(timeout=3000)).splitlines()}
        exact = lines & {"男", "女"}
        if len(exact) == 1:
            return exact.pop(), "profile-header-exact-line", " | ".join(sorted(lines))[:300]
        return "未知", "not-public", " | ".join(line for line in lines if line)[:300]
    return "未知", "not-public", "未找到公开资料栏"


async def launch_context(playwright, profile_dir: Path, headless: bool):
    errors = []
    for channel in ("msedge", "chrome", None):
        try:
            kwargs = {"user_data_dir": str(profile_dir), "headless": headless, "viewport": None}
            if channel:
                kwargs["channel"] = channel
            return await playwright.chromium.launch_persistent_context(**kwargs)
        except Exception as exc:
            errors.append(f"{channel or 'chromium'}: {exc}")
    raise RuntimeError("无法启动浏览器：" + " | ".join(errors))


async def login_cookie_names(context) -> list[str]:
    names = {cookie["name"] for cookie in await context.cookies(["https://www.douyin.com/"])}
    return sorted(names & AUTH_COOKIE_NAMES)


async def wait_for_scan_login(context, page, timeout_seconds: int, status_path: Path) -> None:
    await page.goto("https://www.douyin.com/", wait_until="domcontentloaded", timeout=60000)
    print("请在打开的抖音浏览器中扫码登录。本窗口会自动检测登录结果，请勿关闭浏览器。", flush=True)
    deadline = time.monotonic() + timeout_seconds
    last_report = -1
    while time.monotonic() < deadline:
        names = await login_cookie_names(context)
        if names:
            await page.wait_for_timeout(2000)
            status = {
                "登录状态": "已保存",
                "保存时间": datetime.now().astimezone().isoformat(timespec="seconds"),
                "浏览器档案": str(status_path.parent.resolve()),
                "检测到的登录凭证": names,
            }
            status_path.write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")
            print(json.dumps(status, ensure_ascii=False, indent=2), flush=True)
            return
        remaining = max(0, int(deadline - time.monotonic()))
        bucket = remaining // 30
        if bucket != last_report:
            print(f"等待扫码登录，剩余约 {remaining} 秒……", flush=True)
            last_report = bucket
        await page.wait_for_timeout(1000)
    raise RuntimeError("等待扫码登录超时，请重新运行“第1步_扫码登录.bat”")


def build_jobs(payload: dict, sections: list[str], checkpoint: dict, limit: int) -> list[dict]:
    jobs: list[dict] = []
    queued_urls: set[str] = set()
    for section in sections:
        for row in payload.get(section, []):
            url = str(row.get("主页链接") or "").strip()
            if not url or url in queued_urls:
                continue
            cached = checkpoint.get(url)
            # Unknown may have resulted from an incomplete page and is retried.
            if cached and cached.get("性别") in {"男", "女"}:
                continue
            if limit and len(jobs) >= limit:
                return jobs
            queued_urls.add(url)
            jobs.append({
                "序号": len(jobs) + 1,
                "昵称": row.get("昵称") or row.get("ID（昵称）") or row.get("名称"),
                "主页链接": url,
            })
    return jobs


async def scan_profiles(
    context,
    jobs: list[dict],
    checkpoint: dict,
    checkpoint_path: Path,
    tabs: int,
    wait_ms: int,
    timeout_ms: int,
    stagger_ms: int,
    retries: int,
    request_interval_ms: int,
) -> list[dict]:
    queue: asyncio.Queue = asyncio.Queue()
    for job in jobs:
        queue.put_nowait(job)

    results: list[dict] = []
    checkpoint_lock = asyncio.Lock()
    print_lock = asyncio.Lock()
    started_at = time.monotonic()

    async def worker(tab_number: int, page) -> None:
        page.set_default_timeout(timeout_ms)
        if stagger_ms:
            await page.wait_for_timeout((tab_number - 1) * stagger_ms)
        last_request_at = 0.0
        while True:
            try:
                job = queue.get_nowait()
            except asyncio.QueueEmpty:
                return
            url = job["主页链接"]
            result = None
            for attempt in range(1, retries + 2):
                url = job["主页链接"]
                try:
                    elapsed_ms = (time.monotonic() - last_request_at) * 1000
                    if last_request_at and elapsed_ms < request_interval_ms:
                        await page.wait_for_timeout(int(request_interval_ms - elapsed_ms))
                    last_request_at = time.monotonic()
                    await page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
                    gender, selector, profile_text = await exact_gender_from_profile(page, wait_ms)
                    result = {
                        "性别": gender,
                        "选择器": selector,
                        "资料栏摘要": profile_text,
                        "时间": datetime.now().astimezone().isoformat(timespec="seconds"),
                        "标签页": tab_number,
                        "访问次数": attempt,
                    }
                    break
                except (PlaywrightTimeoutError, PlaywrightError) as exc:
                    result = {
                        "性别": "未知",
                        "选择器": "error",
                        "错误": str(exc)[:500],
                        "时间": datetime.now().astimezone().isoformat(timespec="seconds"),
                        "标签页": tab_number,
                        "访问次数": attempt,
                    }
                    if attempt <= retries:
                        # Concurrent requests can occasionally receive a
                        # transient HTTP failure. Back off before retrying.
                        await page.wait_for_timeout(1200 * attempt + tab_number * 150)

            display = {
                "序号": job["序号"],
                "标签页": tab_number,
                "昵称": job["昵称"],
                "主页链接": url,
                "识别性别": result["性别"],
                "选择器": result.get("选择器"),
                "访问次数": result.get("访问次数", 1),
                "资料栏摘要": result.get("资料栏摘要", ""),
            }
            async with checkpoint_lock:
                checkpoint[url] = result
                save_checkpoint(checkpoint_path, checkpoint)
                results.append(display)
            async with print_lock:
                print(json.dumps(display, ensure_ascii=False), flush=True)
            queue.task_done()

    worker_count = min(tabs, len(jobs))
    pages = list(context.pages[:worker_count])
    while len(pages) < worker_count:
        pages.append(await context.new_page())
    await asyncio.gather(*(worker(tab_number, pages[tab_number - 1]) for tab_number in range(1, worker_count + 1)))
    results.sort(key=lambda item: item["序号"])
    elapsed = round(time.monotonic() - started_at, 1)
    print(json.dumps({"并发标签页": worker_count, "并发扫描耗时秒": elapsed}, ensure_ascii=False), flush=True)
    return results


async def repair_failed_profiles(
    context,
    results: list[dict],
    checkpoint: dict,
    checkpoint_path: Path,
    wait_ms: int,
    timeout_ms: int,
    retries: int,
    cooldown_ms: int,
) -> None:
    failed = [result for result in results if result.get("选择器") == "error"]
    if not failed:
        return
    print(f"第一轮有 {len(failed)} 个网页加载失败，等待后开始单标签低速补扫。", flush=True)
    await asyncio.sleep(cooldown_ms / 1000)
    for repair_index, display in enumerate(failed, start=1):
        page = await context.new_page()
        page.set_default_timeout(timeout_ms)
        repaired = None
        try:
            for attempt in range(1, retries + 2):
                try:
                    await page.goto(display["主页链接"], wait_until="domcontentloaded", timeout=timeout_ms)
                    gender, selector, profile_text = await exact_gender_from_profile(page, wait_ms)
                    repaired = {
                        "性别": gender,
                        "选择器": selector,
                        "资料栏摘要": profile_text,
                        "时间": datetime.now().astimezone().isoformat(timespec="seconds"),
                        "标签页": "补扫",
                        "访问次数": attempt,
                    }
                    break
                except (PlaywrightTimeoutError, PlaywrightError) as exc:
                    repaired = {
                        "性别": "未知",
                        "选择器": "error",
                        "错误": str(exc)[:500],
                        "时间": datetime.now().astimezone().isoformat(timespec="seconds"),
                        "标签页": "补扫",
                        "访问次数": attempt,
                    }
                    if attempt <= retries:
                        await page.wait_for_timeout(2500 * attempt)
        finally:
            await page.close()

        checkpoint[display["主页链接"]] = repaired
        save_checkpoint(checkpoint_path, checkpoint)
        display.update({
            "标签页": "补扫",
            "识别性别": repaired["性别"],
            "选择器": repaired.get("选择器"),
            "访问次数": repaired.get("访问次数", 1),
            "资料栏摘要": repaired.get("资料栏摘要", ""),
        })
        print(json.dumps({"补扫进度": f"{repair_index}/{len(failed)}", **display}, ensure_ascii=False), flush=True)
        if repair_index < len(failed):
            await asyncio.sleep(cooldown_ms / 1000)


async def async_main(args) -> int:
    profile_dir = args.profile_dir.resolve()
    profile_dir.mkdir(parents=True, exist_ok=True)

    if args.login_only:
        if args.headless:
            raise ValueError("扫码登录必须使用有头浏览器，不能添加 --headless")
        async with async_playwright() as playwright:
            context = await launch_context(playwright, profile_dir, False)
            await context.clear_cookies()
            page = context.pages[0] if context.pages else await context.new_page()
            try:
                await wait_for_scan_login(context, page, args.login_timeout_sec, profile_dir / "login_status.json")
            finally:
                await context.close()
        print("登录信息已保存在本地。现在可以运行第2步试跑。", flush=True)
        return 0

    yaml_path = args.yaml.resolve()
    payload = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
    sections = [name for name in ("第一轮清洗结果", "保留评论", "待人工复核评论") if name in payload]
    if not sections:
        raise ValueError("YML 中没有第一轮清洗结果、保留评论或待人工复核评论")
    checkpoint = {}
    if args.checkpoint.exists():
        checkpoint = json.loads(args.checkpoint.read_text(encoding="utf-8"))

    jobs = build_jobs(payload, sections, checkpoint, args.limit)
    backup = None
    if not args.dry_run:
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        backup = yaml_path.with_name(f"{yaml_path.stem}.before-playwright-gender-{stamp}{yaml_path.suffix}")
        shutil.copy2(yaml_path, backup)

    async with async_playwright() as playwright:
        context = await launch_context(playwright, profile_dir, args.headless)
        if not await login_cookie_names(context):
            await context.close()
            raise RuntimeError("尚未检测到已保存的抖音登录状态，请先运行“第1步_扫码登录.bat”")
        try:
            trial_results = await scan_profiles(
                context=context,
                jobs=jobs,
                checkpoint=checkpoint,
                checkpoint_path=args.checkpoint.resolve(),
                tabs=args.tabs,
                wait_ms=args.wait_ms,
                timeout_ms=args.timeout_ms,
                stagger_ms=args.stagger_ms,
                retries=args.retries,
                request_interval_ms=args.request_interval_ms,
            ) if jobs else []
            await repair_failed_profiles(
                context=context,
                results=trial_results,
                checkpoint=checkpoint,
                checkpoint_path=args.checkpoint.resolve(),
                wait_ms=args.wait_ms,
                timeout_ms=args.timeout_ms,
                retries=args.repair_retries,
                cooldown_ms=args.repair_cooldown_ms,
            )
        finally:
            try:
                await context.close()
            except PlaywrightError:
                # The user may close the headed browser while the script is
                # winding down. Checkpoints written per profile remain valid.
                pass

    deleted_now = 0
    if not args.dry_run:
        audit = payload.setdefault("删除审计", [])
        for section in sections:
            kept = []
            for row in payload.get(section, []):
                url = str(row.get("主页链接") or "").strip()
                result = checkpoint.get(url)
                if result and result.get("性别") == "男":
                    audit.append({
                        **row,
                        "删除原因": "Playwright 读取主页公开资料栏明确显示男",
                        "性别证据选择器": result.get("选择器", ""),
                    })
                    deleted_now += 1
                else:
                    kept.append(row)
            payload[section] = kept
        summary = payload.setdefault("清洗总览", {})
        summary["自动删除数量"] = len(payload.get("删除审计", []))
        summary["待人工复核数量"] = len(payload.get("待人工复核评论", []))
        summary["保留数量"] = len(payload.get("保留评论", []))
        summary["清洗前数量"] = summary["自动删除数量"] + summary["待人工复核数量"] + summary["保留数量"]
        save_payload(yaml_path, payload)

    print(json.dumps({
        "完成": True,
        "试运行": args.dry_run,
        "并发标签页": min(args.tabs, len(jobs)) if jobs else 0,
        "本次检查": len(trial_results),
        "识别统计": {
            gender: sum(result["识别性别"] == gender for result in trial_results)
            for gender in ("男", "女", "未知")
        },
        "本次删除男性": deleted_now,
        "YML已修改": not args.dry_run,
        "备份": str(backup) if backup else "未创建（试运行不改文件）",
        "断点": str(args.checkpoint.resolve()),
    }, ensure_ascii=False, indent=2), flush=True)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="并发读取抖音主页公开性别，删除明确显示为男的 YAML 评论")
    parser.add_argument("--yaml", type=Path, default=DEFAULT_YAML)
    parser.add_argument("--limit", type=int, default=0, help="本次最多检查多少个主页；0 表示全部")
    parser.add_argument("--tabs", type=int, default=5, help="并发标签页数量，范围 1-5，默认 5")
    parser.add_argument("--wait-ms", type=int, default=2500)
    parser.add_argument("--stagger-ms", type=int, default=300, help="各标签首次访问的错峰毫秒数")
    parser.add_argument("--retries", type=int, default=2, help="网页加载失败后的自动重试次数，默认 2")
    parser.add_argument("--request-interval-ms", type=int, default=5000, help="每个标签两次主页访问的最小间隔毫秒数")
    parser.add_argument("--repair-retries", type=int, default=2, help="低速补扫阶段的重试次数，默认 2")
    parser.add_argument("--repair-cooldown-ms", type=int, default=3000, help="低速补扫的请求间隔毫秒数")
    parser.add_argument("--timeout-ms", type=int, default=30000)
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--dry-run", action="store_true", help="只识别并展示，不修改 YML")
    parser.add_argument("--login-only", action="store_true", help="只打开抖音等待扫码，并保存持久登录状态")
    parser.add_argument("--login-timeout-sec", type=int, default=600, help="扫码登录最长等待秒数")
    parser.add_argument("--profile-dir", type=Path, default=Path(__file__).resolve().parent / "browser_profile")
    parser.add_argument("--checkpoint", type=Path, default=Path(__file__).resolve().parent / "gender_checkpoint.json")
    args = parser.parse_args()
    if not 1 <= args.tabs <= 5:
        raise ValueError("--tabs 必须在 1 到 5 之间")
    if args.stagger_ms < 0:
        raise ValueError("--stagger-ms 不能小于 0")
    if not 0 <= args.retries <= 5:
        raise ValueError("--retries 必须在 0 到 5 之间")
    if args.request_interval_ms < 1000:
        raise ValueError("--request-interval-ms 不能小于 1000")
    if not 0 <= args.repair_retries <= 5:
        raise ValueError("--repair-retries 必须在 0 到 5 之间")
    if args.repair_cooldown_ms < 1000:
        raise ValueError("--repair-cooldown-ms 不能小于 1000")
    return asyncio.run(async_main(args))


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, RuntimeError, yaml.YAMLError, json.JSONDecodeError) as exc:
        print(f"错误：{exc}", file=sys.stderr)
        raise SystemExit(1)
