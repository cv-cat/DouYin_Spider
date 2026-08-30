"""Search Douyin for videos introducing freestylefly/awesome-gpt-image-2."""

import argparse
import json
import os
import time
from pathlib import Path

from search_github_hot_videos import build_auth, normalize_work
from dy_apis.douyin_api import DouyinAPI


QUERIES = (
    "awesome-gpt-image-2",
    "awesome gpt image 2",
    "freestylefly awesome gpt image 2",
    "GPT Image 2 GitHub",
    "GPT Image 2 提示词 GitHub",
    "GPT Image 2 提示词合集",
)

EXACT_MARKERS = (
    "awesome-gpt-image-2",
    "awesome gpt image 2",
    "freestylefly",
)

PROJECT_MARKERS = (
    "github",
    "开源",
    "项目",
    "仓库",
    "提示词合集",
    "案例合集",
)


def matches_project(record: dict) -> tuple[bool, list[str]]:
    text = record["desc"].casefold().replace("_", " ")
    exact = [marker for marker in EXACT_MARKERS if marker in text]
    if exact:
        return True, exact

    query = record["query"].casefold()
    has_model = "gpt image 2" in text or "gpt-image-2" in text
    project_hits = [marker for marker in PROJECT_MARKERS if marker in text]
    query_is_project_specific = "github" in query or "awesome" in query
    return has_model and bool(project_hits) and query_is_project_specific, project_hits


def collect() -> tuple[list[dict], list[dict]]:
    auth = build_auth()
    by_id = {}
    errors = []
    for query in QUERIES:
        for sort_type in ("1", "0"):
            try:
                response = DouyinAPI.search_general_work(
                    auth, query, sort_type=sort_type, publish_time="0"
                )
                if response.get("status_code") != 0:
                    errors.append(
                        {
                            "query": query,
                            "sort_type": sort_type,
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
                    matched, evidence = matches_project(record)
                    if not matched or not record["id"]:
                        continue
                    record["match_evidence"] = evidence
                    record["sort_type"] = sort_type
                    previous = by_id.get(record["id"])
                    if not previous or record["heat"] > previous["heat"]:
                        by_id[record["id"]] = record
            except Exception as exc:
                errors.append(
                    {"query": query, "sort_type": sort_type, "error": type(exc).__name__}
                )
            time.sleep(1)

    items = sorted(
        by_id.values(),
        key=lambda item: (item["digg"], item["comments"], item["shares"]),
        reverse=True,
    )
    return items, errors


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("datas/awesome_gpt_image_2_videos_20260827.json"),
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

    items, errors = collect()
    payload = {"queries": list(QUERIES), "match_count": len(items), "errors": errors, "items": items}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"output": str(args.output.resolve()), "match_count": len(items), "errors": errors}))


if __name__ == "__main__":
    main()
