from __future__ import annotations

import argparse
import json
from pathlib import Path

import yaml


def normalize(row: dict, include_metrics: bool) -> dict:
    result = {
        "主页链接": row.get("主页链接", ""),
        "评论内容": row.get("评论内容", row.get("内容", "")),
        "名称": row.get("昵称", row.get("名称", "")),
        "评论时间": row.get("日期", row.get("评论时间", "")),
    }
    if include_metrics:
        result.update({
            "主页获赞数": row.get("主页获赞数", ""),
            "粉丝量": row.get("粉丝量", ""),
            "IP": row.get("IP", "湖北"),
        })
    return result


def spaced_dump(data: dict) -> str:
    text = yaml.safe_dump(data, allow_unicode=True, sort_keys=False, width=120)
    lines: list[str] = []
    seen = False
    for line in text.splitlines():
        if line in {"已公开性别为女:", "未公开性别:"}:
            lines.extend(["", ""])
            seen = False
        if line.startswith("- 主页链接:"):
            if seen:
                lines.extend(["", ""])
            seen = True
        lines.append(line)
    marker = "未公开性别:"
    rendered = "\n".join(lines) + "\n"
    separator = (
        "# ============================================================================\n"
        "# ========================= 以下为未公开性别 ================================\n"
        "# ============================================================================\n\n\n"
    )
    return rendered.replace(marker, separator + marker, 1)


def main() -> int:
    parser = argparse.ArgumentParser(description="生成女生优先、未公开性别在后的最终YML")
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--checkpoint", type=Path, required=True, help="Playwright主页性别结果JSON")
    parser.add_argument("--top-level-total", type=int, required=True)
    parser.add_argument("--hubei-total", type=int, required=True)
    args = parser.parse_args()

    source = yaml.safe_load(args.input.read_text(encoding="utf-8")) or {}
    checkpoint = json.loads(args.checkpoint.read_text(encoding="utf-8"))
    rows = list(source.get("保留评论", source.get("评论", [])))
    women, unknown = [], []
    for row in rows:
        url = str(row.get("主页链接", "")).strip()
        gender = str(checkpoint.get(url, {}).get("性别", row.get("公开性别", row.get("性别", "")))).strip()
        if gender == "男":
            continue
        if gender == "女":
            women.append(normalize(row, False))
        else:
            unknown.append(normalize(row, True))

    deleted = max(0, args.hubei_total - len(women) - len(unknown))
    payload = {
        "总览": {
            "一级评论总数": args.top_level_total,
            "湖北IP评论数": args.hubei_total,
            "累计清洗删除数": deleted,
        },
        "已公开性别为女": women,
        "未公开性别": unknown,
    }
    args.output.write_text(spaced_dump(payload), encoding="utf-8")
    print(f"最终YML：{args.output.resolve()}")
    print(f"明确女性：{len(women)}，未公开性别：{len(unknown)}，累计删除：{deleted}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
