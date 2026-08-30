from __future__ import annotations

import argparse
import json
from pathlib import Path

import yaml


def render_record(row: dict, include_ip: bool) -> dict:
    item = {
        "主页链接": row.get("主页链接") or "",
        "评论内容": row.get("评论内容") or "",
        "名称": row.get("ID（昵称）") or row.get("昵称") or row.get("名称") or "",
        "评论时间": row.get("日期") or row.get("评论时间") or "",
    }
    interests = row.get("兴趣爱好")
    if interests and interests != "未明确提及":
        item["兴趣爱好"] = interests
    if include_ip:
        item["IP"] = row.get("IP") or ""
    return item


def spaced_dump(payload: dict) -> str:
    text = yaml.safe_dump(payload, allow_unicode=True, sort_keys=False, width=120)
    lines: list[str] = []
    current_section = ""
    seen = False
    for line in text.splitlines():
        if line in {"已公开性别为女:", "未公开性别:"}:
            if line == "未公开性别:":
                lines.extend([
                    "", "",
                    "# ============================================================================",
                    "# ========================= 以下为未公开性别 ================================",
                    "# ============================================================================",
                    "", "",
                ])
            current_section = line
            seen = False
        if line.startswith("- 主页链接:"):
            if seen:
                lines.extend(["", ""])
            seen = True
        lines.append(line)
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--top-level-total", type=int, required=True)
    parser.add_argument("--hubei-total", type=int, required=True)
    parser.add_argument("--first-round-deleted", type=int, required=True)
    args = parser.parse_args()

    source = yaml.safe_load(args.source.read_text(encoding="utf-8"))
    checkpoint = json.loads(args.checkpoint.read_text(encoding="utf-8"))
    rows = source.get("第一轮清洗结果") or source.get("保留评论") or []
    women, unknown = [], []
    male_count = 0
    for row in rows:
        result = checkpoint.get(str(row.get("主页链接") or "").strip(), {})
        gender = result.get("性别", "未知")
        if gender == "男":
            male_count += 1
        elif gender == "女":
            women.append(render_record(row, include_ip=False))
        else:
            unknown.append(render_record(row, include_ip=True))

    payload = {
        "总览": {
            "视频一级评论总数": args.top_level_total,
            "湖北IP评论数": args.hubei_total,
            "累计清洗删除数": args.first_round_deleted + male_count,
        },
        "已公开性别为女": women,
        "未公开性别": unknown,
    }
    args.output.write_text(spaced_dump(payload), encoding="utf-8")
    print(yaml.safe_dump({
        "已公开性别为女": len(women),
        "未公开性别": len(unknown),
        "第二轮删除男性": male_count,
        "最终保留": len(women) + len(unknown),
        "输出文件": str(args.output.resolve()),
    }, allow_unicode=True, sort_keys=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
