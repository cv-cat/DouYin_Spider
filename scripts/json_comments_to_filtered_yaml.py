from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

import yaml


def spaced_dump(payload: dict) -> str:
    rendered = yaml.safe_dump(payload, allow_unicode=True, sort_keys=False, width=120)
    output: list[str] = []
    seen = False
    for line in rendered.splitlines():
        if line == "符合条件的评论:":
            output.extend(["", ""])
        if line.startswith("- 日期:"):
            if seen:
                while output and output[-1] == "":
                    output.pop()
                output.extend(["", ""])
            seen = True
        output.append(line)
    return "\n".join(output) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="将项目17评论JSON整理为中文YAML")
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--video-total", type=int, required=True)
    parser.add_argument("--scanned-level1", type=int, required=True)
    args = parser.parse_args()

    rows = json.loads(args.input.read_text(encoding="utf-8"))
    comments = []
    for row in rows:
        timestamp = int(row.get("create_time") or 0)
        comments.append({
            "日期": datetime.fromtimestamp(timestamp).astimezone().isoformat(timespec="seconds") if timestamp else "",
            "昵称": row.get("nickname", ""),
            "评论内容": row.get("text", ""),
            "IP": row.get("ip_location", ""),
            "主页链接": row.get("profile_url", ""),
        })

    payload = {
        "总览": {
            "视频评论总数": args.video_total,
            "已扫描一级评论数": args.scanned_level1,
            "湖北且近14天一级评论数": len(comments),
        },
        "符合条件的评论": comments,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(spaced_dump(payload), encoding="utf-8")
    print(f"YAML：{args.output.resolve()}")
    print(f"写入评论：{len(comments)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
