from __future__ import annotations

import argparse
import re
from pathlib import Path

import yaml

from clean_gender_evidence_yaml import INTEREST_PATTERNS, analyze


DISPLAY_INTEREST_PATTERNS = {
    **INTEREST_PATTERNS,
    "电子游戏": re.compile(r"打瓦|无畏契约|瓦罗兰特|王者|吃鸡|和平精英|铲铲|金铲铲|米哈游|原神|崩铁|游戏"),
    "音乐/乐器": re.compile(r"吉他|钢琴|唱歌|音乐|民谣|乐器"),
    "动漫": re.compile(r"国漫|动漫|二次元|番剧"),
    "做饭/美食": re.compile(r"做饭|烘焙|下厨|美食"),
}


def spaced_yaml(payload: dict) -> str:
    text = yaml.safe_dump(payload, allow_unicode=True, sort_keys=False, width=120)
    output: list[str] = []
    seen = False
    for line in text.splitlines():
        if line.startswith("- ID（昵称）:"):
            if seen:
                output.extend(["", ""])
            seen = True
        output.append(line)
    return "\n".join(output) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source")
    parser.add_argument("output")
    args = parser.parse_args()

    source = Path(args.source)
    output = Path(args.output)
    payload = yaml.safe_load(source.read_text(encoding="utf-8"))
    rows = payload.get("符合条件的评论") or payload.get("保留评论") or []

    kept: list[dict] = []
    deleted: list[tuple[dict, object]] = []
    review_count = 0
    for row in rows:
        decision = analyze(row)
        if decision.action == "删除":
            deleted.append((row, decision))
            continue
        if decision.action == "待人工复核":
            review_count += 1
        content = str(row.get("评论内容") or "")
        interests = [name for name, pattern in DISPLAY_INTEREST_PATTERNS.items() if pattern.search(content)]
        item = {
            "ID（昵称）": row.get("昵称") or "",
            "评论内容": content,
            "兴趣爱好": interests or "未明确提及",
            "日期": row.get("日期") or "",
            "IP": row.get("IP") or "",
            "主页链接": row.get("主页链接") or "",
        }
        if decision.action == "待人工复核":
            item["第一轮判断"] = "证据不足，保留并待人工复核"
        kept.append(item)

    result = {
        "总览": {
            "清洗前评论数": len(rows),
            "第一轮删除疑似男性数": len(deleted),
            "第一轮保留评论数": len(kept),
            "其中待人工复核数": review_count,
        },
        "第一轮清洗结果": kept,
    }
    output.write_text(spaced_yaml(result), encoding="utf-8")
    print(yaml.safe_dump({
        **result["总览"],
        "删除记录": [
            {"ID（昵称）": row.get("昵称"), "评论内容": row.get("评论内容"), "依据": d.evidence}
            for row, d in deleted
        ],
        "输出文件": str(output.resolve()),
    }, allow_unicode=True, sort_keys=False, width=120))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
