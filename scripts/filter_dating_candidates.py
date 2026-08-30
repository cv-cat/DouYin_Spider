from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


MALE_CONTENT = re.compile(
    r"蹲.{0,8}(小姐姐|姐姐|御姐|女生|女孩|妹妹|妹子|女朋友|对象)|"
    r"找.{0,8}(小姐姐|姐姐|御姐|女生|女孩|妹妹|妹子|女朋友)|"
    r"(小姐姐|姐姐|御姐|女生|女孩|妹妹|妹子).{0,8}(找我|来找我|可以来)|"
    r"(本人|我是|男)[，,：:\s]*男|男生|爷们|兄弟|哥们|哥哥|太帅"
)
MALE_NAME = re.compile(r"先生|(?<!表)哥(?:$|[._·\-丨])|大叔|少爷|公子|男孩|男生|爷们")
OLD_BIRTH = re.compile(r"(?<!\d)(?:19)?(9[0-9])\s*(?:年|后|的)?(?!\d)")
CM_HEIGHT = re.compile(r"(?<!\d)(1[7-9]\d|2\d\d)\s*(?:cm|厘米|公分)?(?!\d)", re.I)
M_HEIGHT = re.compile(r"(?<!\d)(1\.[7-9]\d?)\s*(?:m|米)(?!\d)", re.I)


def rejection(row: dict) -> str:
    ip = str(row.get("ip_location") or "")
    text = str(row.get("text") or row.get("normalized_content") or "")
    nickname = str(row.get("nickname") or row.get("author_nickname") or "")
    signature = str(row.get("signature") or "")
    combined = f"{nickname} {text} {signature}"
    if "湖北" in ip:
        return "湖北IP"
    if MALE_CONTENT.search(text):
        return "明显男性/寻找女性话术"
    if MALE_NAME.search(nickname):
        return "男性昵称"
    if str(row.get("gender") or "") == "男":
        return "主页公开性别为男"
    if MALE_CONTENT.search(signature):
        return "主页个签含男性线索"
    for match in OLD_BIRTH.finditer(combined):
        if int(match.group(1)) <= 99:
            return "自述1999年或以前出生"
    if CM_HEIGHT.search(combined) or M_HEIGHT.search(combined):
        return "自述身高170cm及以上"
    return ""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source")
    parser.add_argument("output")
    parser.add_argument("--limit", type=int, default=80)
    args = parser.parse_args()
    rows = json.loads(Path(args.source).read_text(encoding="utf-8-sig"))
    kept, rejected = [], {}
    for row in rows:
        reason = rejection(row)
        if reason:
            rejected[reason] = rejected.get(reason, 0) + 1
        elif row.get("sec_uid"):
            kept.append(row)
    if args.limit:
        kept = kept[: args.limit]
    Path(args.output).write_text(
        json.dumps(kept, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps({"kept": len(kept), "rejected": rejected}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
