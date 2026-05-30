class LeadScoringService:
    DEFAULT_SOURCE_WEIGHTS = {
        "comment": 30,
        "search": 10,
        "live": 10,
    }

    DEFAULT_INTENT_RULES = (
        {
            "label": "strong",
            "weight": 22,
            "cap": 40,
            "terms": ("求带", "陪玩", "求陪玩", "上分", "求上分"),
        },
        {
            "label": "medium",
            "weight": 17,
            "cap": 30,
            "terms": ("找队友", "找搭子", "车队"),
        },
        {
            "label": "weak",
            "weight": 8,
            "cap": 23,
            "terms": ("段位", "卡关", "上不去", "想赢"),
        },
    )

    DEFAULT_CONTEXT_RULE = {
        "label": "delta",
        "bonus": 20,
        "terms": ("三角洲", "三角洲行动"),
    }

    DEFAULT_PAYMENT_RULE = {
        "label": "payment",
        "weight": 10,
        "cap": 15,
        "terms": ("多少钱", "长期", "靠谱", "有人接吗", "固定队"),
    }

    DEFAULT_NEGATIVE_RULES = (
        {
            "label": "free",
            "penalty": 12,
            "flag": "free_rider",
            "terms": ("免费", "白嫖"),
        },
        {
            "label": "ad",
            "penalty": 10,
            "flag": "ad_noise",
            "terms": ("广告",),
        },
    )

    DEFAULT_EXCLUSION_RULES = (
        {
            "label": "agency",
            "flag": "agency",
            "terms": ("招代理", "加盟"),
        },
        {
            "label": "competitor",
            "flag": "competitor",
            "terms": ("同行", "工作室"),
        },
    )

    def __init__(
        self,
        source_weights=None,
        intent_rules=None,
        context_rule=None,
        payment_rule=None,
        negative_rules=None,
        exclusion_rules=None,
    ):
        self.source_weights = source_weights or self.DEFAULT_SOURCE_WEIGHTS
        self.intent_rules = intent_rules or self.DEFAULT_INTENT_RULES
        self.context_rule = context_rule or self.DEFAULT_CONTEXT_RULE
        self.payment_rule = payment_rule or self.DEFAULT_PAYMENT_RULE
        self.negative_rules = negative_rules or self.DEFAULT_NEGATIVE_RULES
        self.exclusion_rules = exclusion_rules or self.DEFAULT_EXCLUSION_RULES

    def score_lead(self, lead=None, **overrides):
        payload = {}
        if lead is not None:
            if not isinstance(lead, dict):
                raise TypeError("lead must be a dict when provided")
            payload.update(lead)
        payload.update(overrides)

        source_type = str(payload.get("source_type") or "").strip().lower()
        text_haystack = self._build_haystack(payload, ("content", "comment_text", "notes"))
        profile_haystack = self._build_haystack(payload, ("nickname", "signature"))
        review_haystack = " ".join(part for part in (text_haystack, profile_haystack) if part)
        reasons = []
        matched_terms = []
        risk_flags = []

        excluded_labels, excluded_terms, excluded_flags = self._match_exclusions(review_haystack)
        if excluded_labels:
            reasons.extend(f"excluded:{label}" for label in excluded_labels)
            matched_terms.extend(excluded_terms)
            risk_flags.extend(["excluded", *excluded_flags])
            return self._build_result(0, reasons, risk_flags, matched_terms, source_type, excluded=True)

        score = int(self.source_weights.get(source_type, 0))
        if score:
            reasons.append(f"source:{source_type}")

        best_intent = None
        for rule in self.intent_rules:
            rule_terms = self._find_terms(text_haystack, rule["terms"])
            if not rule_terms:
                continue
            rule_score = min(len(rule_terms) * int(rule["weight"]), int(rule["cap"]))
            if best_intent is None or rule_score > best_intent["score"]:
                best_intent = {
                    "label": rule["label"],
                    "score": rule_score,
                    "terms": rule_terms,
                }

        if best_intent:
            score += best_intent["score"]
            reasons.append(f"intent:{best_intent['label']}")
            matched_terms.extend(best_intent["terms"])

        context_terms = self._find_terms(text_haystack, self.context_rule["terms"])
        if context_terms:
            score += int(self.context_rule["bonus"])
            reasons.append(f"context:{self.context_rule['label']}")
            matched_terms.extend(context_terms)

        payment_terms = self._find_terms(text_haystack, self.payment_rule["terms"])
        if payment_terms:
            score += min(len(payment_terms) * int(self.payment_rule["weight"]), int(self.payment_rule["cap"]))
            reasons.append(f"support:{self.payment_rule['label']}")
            matched_terms.extend(payment_terms)

        for rule in self.negative_rules:
            rule_terms = self._find_terms(review_haystack, rule["terms"])
            if not rule_terms:
                continue
            score -= int(rule["penalty"])
            reasons.append(f"negative:{rule['label']}")
            matched_terms.extend(rule_terms)
            risk_flags.append(rule["flag"])

        score = max(0, min(100, score))
        return self._build_result(score, reasons, risk_flags, matched_terms, source_type, excluded=False)

    def _match_exclusions(self, haystack):
        labels = []
        terms = []
        flags = []
        for rule in self.exclusion_rules:
            rule_terms = self._find_terms(haystack, rule["terms"])
            if not rule_terms:
                continue
            labels.append(rule["label"])
            terms.extend(rule_terms)
            flags.append(rule["flag"])
        return labels, terms, flags

    def _build_haystack(self, payload, fields):
        parts = [payload.get(field) for field in fields]
        normalized = [str(part).strip().lower() for part in parts if str(part or "").strip()]
        return " ".join(normalized)

    def _find_terms(self, haystack, terms):
        return [term for term in terms if term.lower() in haystack]

    def _build_result(self, score, reasons, risk_flags, matched_terms, source_type, excluded):
        grade = self._grade(score)
        return {
            "score": score,
            "total_score": score,
            "grade": grade,
            "reasons": reasons,
            "risk_flags": risk_flags,
            "matched_terms": sorted(set(matched_terms)),
            "source_type": source_type,
            "excluded": excluded,
        }

    def _grade(self, score):
        if score >= 85:
            return "S"
        if score >= 70:
            return "A"
        if score >= 50:
            return "B"
        return "C"
