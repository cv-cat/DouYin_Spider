import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dy_apis.douyin_api import DouyinAPI
from builder.auth import DouyinAuth
from dotenv import load_dotenv
from utils.data_util import handle_work_info


DEFAULT_QUERIES = [
    "Homepage Docker 导航页",
    "Homarr NAS 导航页",
    "Dashy 个人导航面板",
    "Heimdall Docker 导航页",
    "Flame Docker 导航页",
    "CasaOS 个人云",
    "NAS 个人导航页",
    "个人工作台 开源",
    "自建个人工作台",
]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--cutoff", default="2026-05-23")
    parser.add_argument("--per-query", type=int, default=40)
    parser.add_argument("--output", default="datas/personal_dashboard_recent.json")
    args = parser.parse_args()

    cutoff = datetime.strptime(args.cutoff, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp()
    load_dotenv()
    cookie_string = os.getenv("DY_COOKIES")
    if not cookie_string:
        raise RuntimeError("DY_COOKIES is missing")
    auth = DouyinAuth()
    auth.perepare_auth(cookie_string, "", "")
    found = {}

    for query in DEFAULT_QUERIES:
        works, guide_words = DouyinAPI.search_some_video_work(
            auth,
            query,
            num=args.per_query,
            sort_type="2",
            publish_time="180",
        )
        for wrapper in works:
            raw = wrapper.get("aweme_info") or wrapper.get("aweme_mix_info", {}).get("mix_items", [{}])[0]
            if not raw or int(raw.get("create_time", 0)) < cutoff:
                continue
            try:
                item = handle_work_info(raw)
            except (KeyError, TypeError):
                continue
            item["matched_query"] = query
            item["published_at"] = datetime.fromtimestamp(
                int(raw["create_time"]), tz=timezone.utc
            ).astimezone().isoformat(timespec="seconds")
            found[item["work_id"]] = item

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(list(found.values()), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps({"count": len(found), "output": str(output)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
