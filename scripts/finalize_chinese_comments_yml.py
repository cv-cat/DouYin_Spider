from __future__ import annotations

import argparse
import re
import shutil
from datetime import datetime
from pathlib import Path

import yaml

from yaml_comment_format import add_comment_spacing


# The desired age window keeps 00-05 births. Remove clearly stated 06-09
# births, including full years and compact strings such as 070806.
YOUNG_YEAR = re.compile(
    r"(?<![\d.])(?:200[6-9]|0[6-9])(?:\s*(?:年|年生|后|出生|年出生))?(?![\d.])|"
    r"(?<!\d)(?:0[6-9]){2,}(?!\d)"
)


def is_too_young(comment: dict) -> bool:
    return bool(YOUNG_YEAR.search(str(comment.get("content") or "")))


def spaced_yaml(text: str) -> str:
    """Add two blank lines before the list and between comment records."""
    output: list[str] = []
    seen = False
    for line in text.splitlines():
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
    parser = argparse.ArgumentParser()
    parser.add_argument("path")
    args = parser.parse_args()
    path = Path(args.path).resolve()
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    rows = [row for values in payload["comments_by_ip"].values() for row in values]
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = path.with_name(f"{path.stem}.before-chinese-overview-{timestamp}{path.suffix}")
    shutil.copy2(path, backup)

    removed = [row for row in rows if is_too_young(row)]
    kept = [row for row in rows if not is_too_young(row)]
    output = {
        "当前符合条件的评论数": len(kept),
        "符合条件的评论": [
            {
                "日期": row.get("published_at", ""),
                "昵称": row.get("nickname", ""),
                "评论内容": row.get("content", ""),
                "IP": row.get("ip_location", ""),
                "主页链接": row.get("profile_url", ""),
                "主页获赞数": row.get("profile_total_likes", "未知"),
                "粉丝量": row.get("profile_follower_count", "未知"),
            }
            for row in kept
        ],
    }
    rendered = yaml.safe_dump(output, allow_unicode=True, sort_keys=False, width=120)
    path.write_text(spaced_yaml(rendered), encoding="utf-8")
    audit = path.with_name(f"{path.stem}.removed-young-years-{timestamp}.yml")
    audit.write_text(
        yaml.safe_dump({"删除数量": len(removed), "删除记录": removed}, allow_unicode=True, sort_keys=False, width=120),
        encoding="utf-8",
    )
    print(yaml.safe_dump({
        "清洗前": len(rows), "删除年轻年份": len(removed), "最终保留": len(kept),
        "备份": str(backup), "删除审计": str(audit),
    }, allow_unicode=True, sort_keys=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
