"""Deterministic, explainable targeting rules for Douyin comment leads."""

import re


NON_HUBEI_PLACES = {
    "北京", "上海", "天津", "重庆", "郑州", "南阳", "洛阳", "焦作", "开封",
    "广州", "深圳", "东莞", "佛山", "长沙", "南昌", "杭州", "南京", "苏州",
    "成都", "西安", "济南", "青岛", "合肥", "福州", "厦门", "昆明", "贵阳",
    "太原", "石家庄", "沈阳", "大连", "长春", "哈尔滨", "兰州", "乌鲁木齐",
}
FEMALE_TARGET_TERMS = ("姐姐", "小姐姐", "甜妹", "御姐", "美女", "女朋友", "女生", "女大", "妹妹")
SEEK_TERMS = ("蹲", "找", "求", "想认识", "有没有", "来个", "缺", "处一个", "谈一个")
MALE_SELF_TERMS = ("男大", "男生", "男的", "男人", "爷们", "小哥哥", "帅哥", "单身男", "直男", "弟弟", "叔", "老登")
MALE_NICKNAME_PATTERNS = (
    r"(?:先生|少爷|公子|男孩|男生|男人|小哥|大叔|老叔|猛男|靓仔)$",
    r"^(?:叔叔|哥哥|弟弟|小哥|大叔)",
)
LOW_INFORMATION_RE = re.compile(r"^[\s\W_]*(?:\d{1,4})?[\s\W_]*$", re.UNICODE)
NEGATIVE_INTENT_TERMS = ("别找了", "不想谈", "不谈恋爱", "单着不好吗", "单身挺好", "不处对象")
TARGET_INTENT_TERMS = (
    "找对象", "对象", "谈恋爱", "恋爱", "脱单", "相亲", "单身", "催婚", "催了",
    "介绍", "想认识", "认真处", "愿望", "许愿", "报名", "有人谈吗", "有合适",
    "找不到", "没人追", "不想再一个人", "来一个", "我来主动", "给个暗示",
)
LOW_VALUE_TERMS = ("你好", "您好", "我要", "累了", "真的假的")
LOW_VALUE_RE = re.compile(r"^(?:\[[^\]]+\]|@[^\s]+|哈+|呵+|嘿+|来吧|对呀对呀)+[!！。,.，\s]*$")


def _compact(value):
    return re.sub(r"\s+", "", str(value or "")).lower()


def _mentioned_birth_year(text):
    compact = _compact(text)
    patterns = (
        r"(?<!\d)([1-9]\d|0\d)(?:年|年的|年生|后|的)(?!\d)",
        r"(?:我是|本人|本人是|我)([1-9]\d|0\d)(?!\d)",
        r"(?<!\d)([1-9]\d|0\d)(?:男|女)(?!\d)",
        r"^([1-9]\d|0\d)(?=\D|$)",
    )
    for pattern in patterns:
        match = re.search(pattern, compact)
        if match:
            return match.group(1)
    return ""


def _seeks_non_hubei_location(text):
    compact = _compact(text)
    if not any(term in compact for term in ("有吗", "有没有", "谈吗", "处吗", "行吗", "可以吗", "找对象", "找个")):
        return ""
    return next((place for place in NON_HUBEI_PLACES if place in compact), "")


def _explicit_male_signal(text, nickname):
    compact = _compact(text)
    nick = _compact(nickname)
    if any(term in compact for term in MALE_SELF_TERMS):
        return "评论包含明确男性自述"
    female_question = any(target in compact for target in FEMALE_TARGET_TERMS) and any(
        term in compact for term in ("有吗", "有没有", "吗", "许愿", "来个", "找")
    )
    if female_question or (any(seek in compact for seek in SEEK_TERMS) and any(target in compact for target in FEMALE_TARGET_TERMS)):
        return "评论明确寻找女性对象"
    if any(re.search(pattern, nick) for pattern in MALE_NICKNAME_PATTERNS):
        return "昵称包含明确男性称谓"
    return ""


def evaluate_target_comment(row):
    """Return (accepted, reasons); retain unknown gender absent strong public signals."""
    text = str(row.get("text") or row.get("comment_text") or "").strip()
    nickname = str(row.get("nickname") or row.get("author_nickname") or "").strip()
    reasons = []
    if not text or LOW_INFORMATION_RE.fullmatch(text):
        reasons.append("空内容或纯数字等低信息评论")
    if LOW_VALUE_RE.fullmatch(_compact(text)):
        reasons.append("纯表情、艾特或语气词，缺少客户意向信息")
    if any(term in _compact(text) for term in NEGATIVE_INTENT_TERMS):
        reasons.append("评论明确表达无恋爱意向")
    compact_text = _compact(text)
    if any(term in compact_text for term in ("不需要对象", "反正不找", "不抱希望", "主动我也不要")):
        reasons.append("评论明确表达无恋爱意向")
    if _compact(text) in LOW_VALUE_TERMS:
        reasons.append("只有招呼或态度词，缺少客户意向信息")
    year = _mentioned_birth_year(text)
    if year and 10 <= int(year) <= 99:
        reasons.append(f"出生年份为{year}，早于00年")
    other_place = _seeks_non_hubei_location(text)
    if other_place:
        reasons.append(f"求偶目标指向湖北以外地区：{other_place}")
    male_reason = _explicit_male_signal(text, nickname)
    if male_reason:
        reasons.append(male_reason)
    if str(row.get("gender") or "").strip() == "男":
        reasons.append("主页公开性别为男")
    if not has_target_intent(row):
        reasons.append("未体现恋爱、脱单或认识对象需求")
    return not reasons, reasons


def has_target_intent(row):
    """Return whether public text contains a usable dating or matchmaking need signal."""
    text = _compact(row.get("text") or row.get("comment_text"))
    return any(term in text for term in TARGET_INTENT_TERMS) or bool(_mentioned_birth_year(text))


def filter_target_comments(rows):
    accepted, rejected = [], []
    for row in rows:
        keep, reasons = evaluate_target_comment(row)
        (accepted if keep else rejected).append(row if keep else {"row": row, "reasons": reasons})
    return accepted, rejected
