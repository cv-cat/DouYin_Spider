from __future__ import annotations

import argparse
import re
import shutil
from collections import Counter
from datetime import datetime
from pathlib import Path

import yaml

from yaml_comment_format import add_comment_spacing


MALE_NICKNAME = re.compile(
    r"先生|大叔|少爷|公子|老公|猛男|帅哥|男孩|男生|爷们|"
    r"(?:^|[^表堂姨姑舅])(哥哥|哥)(?:$|[\s._·丨丶\-])"
)

SEEKING_WOMEN = re.compile(
    r"(?:蹲|找|想找|想认识|认识|求|来个|缺个|要个|有没有|处个|谈个)"
    r".{0,10}(?:小姐姐|姐姐|御姐|甜妹|女生|女孩|妹妹|妹子|女朋友|老婆|对象)|"
    r"(?:小姐姐|姐姐|御姐|甜妹|女生|女孩|妹妹|妹子).{0,10}"
    r"(?:找我|来找我|联系我|私我|滴滴|有没有|处对象|谈恋爱)"
)

MALE_SELF_DESCRIPTION = re.compile(
    r"(?:本人|我是|咱是|纯情|单身|未婚).{0,6}(?:男|男生|男孩|爷们|哥哥|大叔)|"
    r"(?:男|男生|男孩|爷们).{0,6}(?:一枚|一个|求对象|找对象)|"
    r"(?:身高|净身高|裸高)?\s*(?:17[5-9]|18\d|19\d|2\d\d)\s*(?:cm|厘米|公分)?"
)

# Birth year is accepted only with birth-context or a standalone two-digit
# personal-info comment. This avoids treating game scores and other numbers as age.
OLD_BIRTH_CONTEXT = re.compile(
    r"(?<!\d)(?:19)?(9[0-9])\s*(?:年|年生|年的|后|出生|年出生)(?!\d)|"
    r"(?:本人|我是|出生|年纪|年龄)\D{0,5}(?:19)?(9[0-9])(?!\d)"
)
OLD_BIRTH_STANDALONE = re.compile(r"^\s*(?:19)?9[0-9]\s*(?:年|后)?\s*$")

AGE_CONTEXT = re.compile(
    r"(?<!\d)(\d{1,2})\s*(?:岁|周岁)(?!\d)|"
    r"(?:年龄|年纪|本人|我|今年)\D{0,5}(\d{1,2})(?!\d)"
)


def removal_reason(comment: dict) -> str:
    nickname = str(comment.get("nickname") or "").strip()
    content = str(comment.get("content") or "").strip()
    if MALE_NICKNAME.search(nickname):
        return "男性昵称特征"
    if SEEKING_WOMEN.search(content):
        return "寻找女性/女性对象话术"
    if MALE_SELF_DESCRIPTION.search(content):
        return "男性自述或明显男性身高"
    if OLD_BIRTH_CONTEXT.search(content) or OLD_BIRTH_STANDALONE.fullmatch(content):
        return "自述2000年以前出生"
    for match in AGE_CONTEXT.finditer(content):
        values = [value for value in match.groups() if value]
        if values and 27 <= int(values[0]) <= 99:
            return "自述年龄27岁及以上"
    return ""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("path")
    args = parser.parse_args()
    path = Path(args.path).resolve()
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    before = sum(len(rows) for rows in payload["comments_by_ip"].values())
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = path.with_name(f"{path.stem}.before-clean-{timestamp}{path.suffix}")
    shutil.copy2(path, backup)

    hubei = list(payload["comments_by_ip"].get("湖北", []))
    removed = []
    kept = []
    for comment in hubei:
        reason = removal_reason(comment)
        if reason:
            removed.append({"reason": reason, **comment})
        else:
            kept.append(comment)

    removed_non_hubei = before - len(hubei)
    reasons = Counter(row["reason"] for row in removed)
    payload["comments_by_ip"] = {"湖北": kept}
    payload["ip_summary"] = [{"ip_location": "湖北", "comment_count": len(kept)}]
    payload["metadata"]["total_comments"] = len(kept)
    payload["metadata"]["cleaning"] = {
        "cleaned_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "kept_ip_location": "湖北",
        "removed_non_hubei": removed_non_hubei,
        "removed_by_content_rules": len(removed),
        "removal_reasons": dict(reasons),
        "backup_file": backup.name,
    }
    rendered = yaml.safe_dump(payload, allow_unicode=True, sort_keys=False, width=120)
    path.write_text(add_comment_spacing(rendered), encoding="utf-8")
    audit = path.with_name(f"{path.stem}.removed-{timestamp}.yml")
    audit.write_text(
        yaml.safe_dump({"removed": removed}, allow_unicode=True, sort_keys=False, width=120),
        encoding="utf-8",
    )
    print(yaml.safe_dump({
        "before": before,
        "hubei_before_rules": len(hubei),
        "removed_non_hubei": removed_non_hubei,
        "removed_by_rules": len(removed),
        "remaining": len(kept),
        "reasons": dict(reasons),
        "backup": str(backup),
        "audit": str(audit),
    }, allow_unicode=True, sort_keys=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
