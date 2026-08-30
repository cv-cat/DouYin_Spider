from __future__ import annotations

import argparse
import re
import shutil
from collections import Counter
from datetime import datetime
from pathlib import Path

import yaml

from yaml_comment_format import add_comment_spacing


# Dating comments commonly abbreviate birth years as "98[emoji]", "93射手",
# "97 找..." or "96武汉". Treat standalone 91-99 tokens as 1991-1999.
OLD_YEAR_SHORT = re.compile(r"(?<![\d.])(?:19)?9[1-9](?![\d.])")

# Explicit self-identification. Exclude words such as 男朋友/男神 because
# those may describe the desired partner rather than the commenter.
EXPLICIT_MALE = re.compile(
    r"(?<!\d)(?:0\d|9\d)\s*(?:年|后)?\s*(?:男生|男孩|男大|男)(?!朋友|神|装)|"
    r"(?:我是|本人|咱是|自己是)\s*(?:一个|个)?\s*(?:男生|男孩|男大|男)(?!朋友|神|装)|"
    r"(?:男生|男孩|男大)\s*(?:一枚|一个|本人)?"
)


def reason(comment: dict) -> str:
    content = str(comment.get("content") or "")
    reasons = []
    if OLD_YEAR_SHORT.search(content):
        reasons.append("评论含91至99出生年份简写")
    if EXPLICIT_MALE.search(content):
        reasons.append("评论者明确自述男性")
    return "；".join(reasons)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("path")
    args = parser.parse_args()
    path = Path(args.path).resolve()
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    rows = [row for values in payload["comments_by_ip"].values() for row in values]
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = path.with_name(f"{path.stem}.before-clean-round2-{timestamp}{path.suffix}")
    shutil.copy2(path, backup)

    kept, removed = [], []
    for row in rows:
        why = reason(row)
        if why:
            removed.append({"reason": why, **row})
        else:
            kept.append(row)
    counts = Counter(
        part for row in removed for part in row["reason"].split("；") if part
    )
    payload["comments_by_ip"] = {"湖北": kept}
    payload["ip_summary"] = [{"ip_location": "湖北", "comment_count": len(kept)}]
    payload["metadata"]["total_comments"] = len(kept)
    history = payload["metadata"].setdefault("cleaning_history", [])
    history.append({
        "round": 2,
        "cleaned_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "before": len(rows),
        "removed": len(removed),
        "remaining": len(kept),
        "rules": dict(counts),
        "backup_file": backup.name,
    })
    rendered = yaml.safe_dump(payload, allow_unicode=True, sort_keys=False, width=120)
    path.write_text(add_comment_spacing(rendered), encoding="utf-8")
    audit = path.with_name(f"{path.stem}.removed-round2-{timestamp}.yml")
    audit.write_text(
        yaml.safe_dump({"removed": removed}, allow_unicode=True, sort_keys=False, width=120),
        encoding="utf-8",
    )
    print(yaml.safe_dump({
        "before": len(rows), "removed": len(removed), "remaining": len(kept),
        "rule_hits": dict(counts), "backup": str(backup), "audit": str(audit),
    }, allow_unicode=True, sort_keys=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
