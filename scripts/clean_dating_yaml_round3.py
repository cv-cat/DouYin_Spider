from __future__ import annotations

import argparse
import re
import shutil
from datetime import datetime
from pathlib import Path

import yaml

from yaml_comment_format import add_comment_spacing


# In this dating-comment dataset, users often start with an unlabelled age:
# "28，...", "29 武汉...", "42找...". Years 91-99 were handled in round 2.
AGE_AT_START = re.compile(r"^\s*(2[7-9]|[3-8]\d|90)(?!\d)")
AGE_WITH_LABEL = re.compile(r"(?<!\d)(2[7-9]|[3-8]\d|90)\s*(?:岁|周岁)(?!\d)")


def reason(comment: dict) -> str:
    content = str(comment.get("content") or "")
    if AGE_AT_START.search(content) or AGE_WITH_LABEL.search(content):
        return "自述年龄27岁及以上"
    return ""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("path")
    args = parser.parse_args()
    path = Path(args.path).resolve()
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    rows = [row for values in payload["comments_by_ip"].values() for row in values]
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = path.with_name(f"{path.stem}.before-clean-round3-{timestamp}{path.suffix}")
    shutil.copy2(path, backup)
    kept, removed = [], []
    for row in rows:
        why = reason(row)
        if why:
            removed.append({"reason": why, **row})
        else:
            kept.append(row)
    payload["comments_by_ip"] = {"湖北": kept}
    payload["ip_summary"] = [{"ip_location": "湖北", "comment_count": len(kept)}]
    payload["metadata"]["total_comments"] = len(kept)
    payload["metadata"].setdefault("cleaning_history", []).append({
        "round": 3,
        "cleaned_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "before": len(rows), "removed": len(removed), "remaining": len(kept),
        "rule": "交友评论开头直接报27岁及以上，或明确写27岁及以上",
        "backup_file": backup.name,
    })
    rendered = yaml.safe_dump(payload, allow_unicode=True, sort_keys=False, width=120)
    path.write_text(add_comment_spacing(rendered), encoding="utf-8")
    audit = path.with_name(f"{path.stem}.removed-round3-{timestamp}.yml")
    audit.write_text(yaml.safe_dump({"removed": removed}, allow_unicode=True, sort_keys=False, width=120), encoding="utf-8")
    print(yaml.safe_dump({"before": len(rows), "removed": len(removed), "remaining": len(kept), "backup": str(backup), "audit": str(audit)}, allow_unicode=True, sort_keys=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
