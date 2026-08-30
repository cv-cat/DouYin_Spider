from __future__ import annotations

import argparse
import json
from pathlib import Path

import yaml

from finalize_chinese_comments_yml import spaced_yaml


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("yaml_path")
    parser.add_argument("profile_json")
    args = parser.parse_args()
    yaml_path = Path(args.yaml_path)
    payload = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
    profiles = json.loads(Path(args.profile_json).read_text(encoding="utf-8-sig"))
    gender_by_url = {
        str(row.get("profile_url") or ""): str(row.get("gender") or "未知")
        for row in profiles if row.get("profile_url")
    }
    rows = payload["符合条件的评论"]
    kept = []
    deleted_male = 0
    for row in rows:
        gender = gender_by_url.get(str(row.get("主页链接") or ""), "未知")
        if gender == "男":
            deleted_male += 1
            continue
        enriched = dict(row)
        # The public profile packet commonly omits gender. Do not add a
        # meaningless "性别: 未知" field to the human-facing YAML. If a
        # previously generated record contains it, remove it while retaining
        # the rule that an explicitly public male value deletes the record.
        enriched.pop("性别", None)
        kept.append(enriched)
    payload["当前符合条件的评论数"] = len(kept)
    payload["符合条件的评论"] = kept
    rendered = yaml.safe_dump(payload, allow_unicode=True, sort_keys=False, width=120)
    yaml_path.write_text(spaced_yaml(rendered), encoding="utf-8")
    print(yaml.safe_dump({
        "抓包主页数": len(gender_by_url),
        "公开男性并删除": deleted_male,
        "未公开性别字段": sum(
            gender_by_url.get(str(row.get("主页链接") or ""), "未知") == "未知"
            for row in kept
        ),
        "剩余": len(kept),
    }, allow_unicode=True, sort_keys=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
