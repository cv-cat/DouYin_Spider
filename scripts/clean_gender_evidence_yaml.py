from __future__ import annotations

import argparse
import re
import shutil
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import yaml


K_COUNT = "当前符合条件的评论数"
K_ROWS = "符合条件的评论"

EXPLICIT_FEMALE = re.compile(r"(?:我是|本人|咱是|自己是|本小姐|本姑娘|姨).{0,6}(?:女生|女孩|女大学生|女大|女高|女研|女|妹子|\d{1,2}了)")
SEEKING_MALE = re.compile(r"(?:找|蹲|想认识|想要|来个|有没有|处个).{0,12}(?:男生|男孩|小哥哥|哥哥|弟弟|帅哥|男朋友|老公|对象男)|(?:男生|小哥哥|哥哥|弟弟|帅哥|老公).{0,10}(?:找我|来找我|滴滴|私我|你在哪|的来)|(?:老公你在哪|想要帅哥)")
EXPLICIT_MALE = re.compile(r"(?:我是|本人|咱是|自己是|单身|未婚|纯情).{0,6}(?:男生|男孩|男大|男高|男研|男士|男人|男|爷们)(?!朋友|神|装)|(?<![\d])(?:0\d|9\d)\s*(?:年|后)?\s*[,，、/ ]{0,3}(?:男生|男孩|男大|男高|男研|男)(?!朋友|神|装)|男找女|单身老男人|小哥哥一枚|(?:^|[，,。.!！?？\s])(?:大叔|叔)\s*\d{1,2}|汉口滴大叔|我是正人君子")
SEEKING_WOMEN = re.compile(r"(?:蹲|d|找|想找|想要|想认识|认识|求|来个|缺个|要个|有没有|处个|谈个|期待|喜欢).{0,16}(?:小姐姐|姐姐|御姐|甜妹|女生|女孩|女人|妹妹|妹子|女大|小美|女朋友|老婆|BBW)|(?:小姐姐|姐姐|御姐|甜妹|女生|女孩|女人|妹妹|妹子|女大|小美|老婆|BBW).{0,12}(?:找我|来找我|联系我|私我|滴滴|有没有|处对象|谈恋爱|看上我|感兴趣|你在哪|的来|主动)|(?:老婆你在哪|来个女大|d个妹妹|蹲个武汉的小美|姐弟恋|没有女生主动|真有这种女孩子吗)", re.I)
STRONG_MALE_NAME = re.compile(r"先生|大叔|少爷|公子|帅哥|猛男|单身老男人|男孩|男生|(?:^|[^表堂姨姑舅])(?:哥哥|哥)(?:$|[\s._·丨丶\-])")
SUSPECT_MALE_NAME = re.compile(r"(?:^|[\s._·丨丶\-])(阿强|小张|老王|龙少|浩哥)(?:$|[\s._·丨丶\-])", re.I)
HEIGHT = re.compile(r"(?<!\d)(1(?:7[5-9]|8\d|9\d))(?:\s*(?:cm|厘米|公分))?(?!\d)|(?<!\d)(1\.(?:7[5-9]|8\d|9\d))\s*(?:m|米)?(?!\d)", re.I)
WEIGHT = re.compile(r"(?<!\d)(?:[5-9]\d|1[0-5]\d)\s*(?:kg|公斤|斤)(?!\d)", re.I)
ASSETS = re.compile(r"有房|有车|房车|月入|月薪|年薪|收入|体制内|公务员|事业编|研究生|本科|工作稳定|独生子|父母退休")
MASC_STYLE = re.compile(r"不卡颜|主页看建模|看建模|谁敢线下|直接线下|有房有车|月入多少")

INTEREST_PATTERNS = {
    "钓鱼/路亚": re.compile(r"钓鱼|路亚"),
    "台球": re.compile(r"台球"),
    "摩托/改装/越野": re.compile(r"摩托|机车|改装车|越野"),
    "公路车": re.compile(r"公路车"),
    "健身增肌": re.compile(r"健身|增肌"),
    "篮球/足球": re.compile(r"篮球|足球"),
    "穿越火线": re.compile(r"穿越火线|CF(?:手游)?", re.I),
    "军事/机械/数码硬件": re.compile(r"军事|军迷|机械|装机|显卡|数码硬件"),
}


@dataclass
class Decision:
    score: int = 0
    evidence: list[str] = field(default_factory=list)
    strong: list[str] = field(default_factory=list)
    negative: list[str] = field(default_factory=list)

    @property
    def action(self) -> str:
        if self.negative and not self.strong:
            return "保留"
        if self.score >= 60:
            return "删除"
        if self.score >= 25:
            return "待人工复核"
        return "保留"


def analyze(row: dict) -> Decision:
    nickname = str(row.get("昵称") or "")
    content = str(row.get("评论内容") or "")
    d = Decision()
    if EXPLICIT_FEMALE.search(content):
        d.score -= 100; d.negative.append("明确自述女性 -100")
    if SEEKING_MALE.search(content):
        d.score -= 60; d.negative.append("明确寻找男性 -60")
    if EXPLICIT_MALE.search(content):
        d.score += 100; d.evidence.append("明确自述男性 +100"); d.strong.append("明确自述男性")
    if SEEKING_WOMEN.search(content):
        d.score += 80; d.evidence.append("明确寻找女性 +80"); d.strong.append("明确寻找女性")
    if STRONG_MALE_NAME.search(nickname):
        d.score += 60; d.evidence.append("昵称含明确男性称谓 +60"); d.strong.append("明确男性昵称")
    if SUSPECT_MALE_NAME.search(nickname):
        d.score += 10; d.evidence.append("疑似男性昵称 +10")
    height = HEIGHT.search(content)
    if height:
        d.score += 25; d.evidence.append(f"自报身高≥175cm（{height.group(0)}）+25")
        if WEIGHT.search(content) or ASSETS.search(content):
            d.score += 30; d.evidence.append("同时自报体重/房车/收入/职业等 +30")
    interests = [label for label, pattern in INTEREST_PATTERNS.items() if pattern.search(content)]
    if interests:
        points = min(15, len(interests) * 5)
        d.score += points; d.evidence.append(f"偏男性兴趣：{'、'.join(interests)} +{points}")
    if MASC_STYLE.search(content):
        d.score += 10; d.evidence.append("男性化征友表达 +10")
    # A clear female statement is an overriding safeguard unless equally clear
    # male evidence is also present, in which case it remains reviewable.
    if d.negative and not d.strong:
        d.score = min(d.score, 24)
    return d


def spaced_yaml(text: str) -> str:
    out: list[str] = []
    seen_in_section = False
    for line in text.splitlines():
        if line in {"保留评论:", "待人工复核评论:", "删除审计:"}:
            out.extend(["", ""])
            seen_in_section = False
        if line.startswith("- 日期:"):
            if seen_in_section:
                while out and out[-1] == "": out.pop()
                out.extend(["", ""])
            seen_in_section = True
        out.append(line)
    return "\n".join(out) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("path")
    parser.add_argument("--preview", action="store_true")
    args = parser.parse_args()
    path = Path(args.path).resolve()
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    rows = payload.get(K_ROWS) or payload.get("保留评论") or []
    classified = [(row, analyze(row)) for row in rows]
    counts = {action: sum(d.action == action for _, d in classified) for action in ("删除", "待人工复核", "保留")}
    if args.preview:
        sample = [
            {"处理": d.action, "得分": d.score, "昵称": row.get("昵称"), "评论内容": row.get("评论内容"), "证据": d.evidence + d.negative}
            for row, d in classified if d.action != "保留"
        ]
        print(yaml.safe_dump({"总数": len(rows), **counts, "命中记录": sample}, allow_unicode=True, sort_keys=False, width=120))
        return 0

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = path.with_name(f"{path.stem}.before-gender-ai-clean-{timestamp}{path.suffix}")
    shutil.copy2(path, backup)
    kept = [dict(row) for row, d in classified if d.action == "保留"]
    review = [
        {**row, "疑似原因": "；".join(d.evidence) or "综合弱证据", "男性证据分": d.score,
         "命中的证据": d.evidence + d.negative, "建议": "人工复核"}
        for row, d in classified if d.action == "待人工复核"
    ]
    deleted = [
        {**row, "删除原因": "；".join(d.strong or d.evidence), "男性证据分": d.score,
         "命中的强证据": d.strong, "全部命中证据": d.evidence + d.negative}
        for row, d in classified if d.action == "删除"
    ]
    result = {
        "清洗总览": {"清洗前数量": len(rows), "自动删除数量": len(deleted), "待人工复核数量": len(review), "保留数量": len(kept)},
        "保留评论": kept,
        "待人工复核评论": review,
        "删除审计": deleted,
    }
    path.write_text(spaced_yaml(yaml.safe_dump(result, allow_unicode=True, sort_keys=False, width=120)), encoding="utf-8")
    print(yaml.safe_dump({**result["清洗总览"], "备份": str(backup)}, allow_unicode=True, sort_keys=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
