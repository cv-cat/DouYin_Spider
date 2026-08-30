"""Search Douyin for popular GitHub project videos using the project API."""

import argparse
import json
import os
import time
from pathlib import Path

from dotenv import load_dotenv

from builder.auth import DouyinAuth
from dy_apis.douyin_api import DouyinAPI


DEFAULT_QUERIES = (
    "GitHub 开源工具推荐",
    "GitHub 自托管项目",
    "GitHub 编程学习项目",
    "GitHub 网络安全项目",
    "GitHub 开源软件推荐",
    "GitHub 开源游戏项目",
    "GitHub 爬虫开源项目",
    "GitHub 实用项目推荐",
)

EXCLUDED_TOPICS = {
    "AI 提示词": ("提示词", "prompt", "prompts", "咒语"),
    "AI 工作流": ("ai工作流", "ai 工作流", "workflow", "n8n", "dify", "coze", "自动化编排"),
    "AI 编程": (
        "ai编程",
        "ai 编程",
        "ai coding",
        "vibe coding",
        "vibecoding",
        "claude code",
        "claudecode",
        "cursor",
        "copilot",
        "代码助手",
        "编程助手",
        "代码生成",
    ),
}


def build_auth() -> DouyinAuth:
    load_dotenv(override=True)
    cookie_str = os.getenv("DY_COOKIES")
    if not cookie_str:
        raise RuntimeError("DY_COOKIES is not configured in .env")

    auth = DouyinAuth()
    auth.perepare_auth(cookie_str, "", "")
    return auth


def normalize_work(work: dict, query: str) -> dict:
    statistics = work.get("statistics") or {}
    author = work.get("author") or {}
    aweme_id = str(work.get("aweme_id") or "")
    digg = int(statistics.get("digg_count") or 0)
    comments = int(statistics.get("comment_count") or 0)
    shares = int(statistics.get("share_count") or 0)
    collects = int(statistics.get("collect_count") or 0)
    return {
        "id": aweme_id,
        "url": f"https://www.douyin.com/video/{aweme_id}",
        "desc": work.get("desc") or "",
        "author": author.get("nickname") or "",
        "create_time": work.get("create_time"),
        "digg": digg,
        "comments": comments,
        "shares": shares,
        "collects": collects,
        "query": query,
        "heat": digg + comments * 5 + shares * 8,
    }


def excluded_topic(text: str) -> str | None:
    normalized = text.casefold().replace("_", " ").replace("-", " ")
    for topic, keywords in EXCLUDED_TOPICS.items():
        if any(keyword.casefold() in normalized for keyword in keywords):
            return topic
    return None


def collect(
    auth: DouyinAuth, queries: tuple[str, ...]
) -> tuple[list[dict], list[dict], list[dict]]:
    by_id = {}
    errors = []
    excluded = {}
    for query in queries:
        try:
            response = DouyinAPI.search_general_work(
                auth,
                query,
                sort_type="1",
                publish_time="0",
            )
            if response.get("status_code") != 0:
                errors.append(
                    {
                        "query": query,
                        "status_code": response.get("status_code"),
                        "status_msg": response.get("status_msg"),
                    }
                )
                continue

            for wrapper in response.get("data", []):
                work = wrapper.get("aweme_info")
                if not work or work.get("aweme_type") != 0:
                    continue
                record = normalize_work(work, query)
                topic = excluded_topic(record["desc"])
                if topic:
                    excluded[record["id"]] = {
                        "id": record["id"],
                        "topic": topic,
                        "desc": record["desc"],
                    }
                    continue
                previous = by_id.get(record["id"])
                if record["id"] and (not previous or record["heat"] > previous["heat"]):
                    by_id[record["id"]] = record
        except Exception as exc:
            errors.append({"query": query, "error": type(exc).__name__})
        time.sleep(1)

    items = sorted(
        by_id.values(),
        key=lambda item: (item["heat"], item["digg"], item["comments"], item["shares"]),
        reverse=True,
    )
    return items, errors, list(excluded.values())


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=30)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("datas/github_hot_videos_20260826.json"),
    )
    args = parser.parse_args()

    for name in (
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "ALL_PROXY",
        "http_proxy",
        "https_proxy",
        "all_proxy",
    ):
        os.environ.pop(name, None)

    items, errors, excluded = collect(build_auth(), DEFAULT_QUERIES)
    payload = {
        "queries": list(DEFAULT_QUERIES),
        "excluded_topics": list(EXCLUDED_TOPICS),
        "candidate_count": len(items),
        "excluded_count": len(excluded),
        "excluded": excluded,
        "errors": errors,
        "items": items[: args.limit],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {
                "output": str(args.output.resolve()),
                "candidate_count": len(items),
                "excluded_count": len(excluded),
                "saved_count": min(len(items), args.limit),
                "errors": errors,
            },
            ensure_ascii=True,
        )
    )


if __name__ == "__main__":
    main()
