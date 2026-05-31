from web.services.lead_scoring_service import LeadScoringService


def test_comment_with_strong_intent_scores_s_grade():
    service = LeadScoringService()

    result = service.score_lead(
        {
            "source_type": "comment",
            "content": "三角洲求带，最好今晚能上分",
        }
    )

    assert result["total_score"] == 90
    assert result["grade"] == "S"
    assert "source:comment" in result["reasons"]
    assert "intent:strong" in result["reasons"]
    assert "context:delta" in result["reasons"]
    assert result["risk_flags"] == []


def test_delta_playmate_comment_variants_score_as_high_intent():
    service = LeadScoringService()

    for text in ("三角洲找陪，今晚有人吗", "三角洲来陪一个，想上分", "三角洲找人带，带我上把"):
        result = service.score_lead(
            {
                "source_type": "comment",
                "content": text,
            }
        )

        assert result["grade"] in {"S", "A"}
        assert "intent:strong" in result["reasons"]
        assert "context:delta" in result["reasons"]


def test_delta_escort_terms_score_as_high_intent():
    service = LeadScoringService()

    for text in ("三角洲护航有人接吗", "三角洲纯绿护报价来", "三角洲来个绿护"):
        result = service.score_lead(
            {
                "source_type": "comment",
                "content": text,
            }
        )

        assert result["grade"] in {"S", "A"}
        assert "intent:strong" in result["reasons"]
        assert "context:delta" in result["reasons"]


def test_search_source_and_mid_intent_lands_in_b_grade():
    service = LeadScoringService()

    result = service.score_lead(
        {
            "source_type": "search",
            "content": "三角洲找队友，来个固定车队",
        }
    )

    assert result["total_score"] == 60
    assert result["grade"] == "B"
    assert "source:search" in result["reasons"]
    assert "intent:medium" in result["reasons"]


def test_live_source_with_weak_pain_signal_scores_b_grade():
    service = LeadScoringService()

    result = service.score_lead(
        {
            "source_type": "live",
            "content": "三角洲段位卡关了，最近一直上不去，想赢几把",
        }
    )

    assert result["total_score"] == 53
    assert result["grade"] == "B"
    assert "source:live" in result["reasons"]
    assert "intent:weak" in result["reasons"]


def test_negative_terms_add_risk_and_reduce_grade():
    service = LeadScoringService()

    result = service.score_lead(
        {
            "source_type": "comment",
            "content": "三角洲求带上分，但是最好免费，别来广告",
        }
    )

    assert result["total_score"] == 68
    assert result["grade"] == "B"
    assert "negative:free" in result["reasons"]
    assert "negative:ad" in result["reasons"]
    assert result["risk_flags"] == ["free_rider", "ad_noise"]


def test_exclusion_terms_force_c_grade_and_block_flag():
    service = LeadScoringService()

    result = service.score_lead(
        {
            "source_type": "comment",
            "content": "三角洲工作室招代理，同行互推",
        }
    )

    assert result["total_score"] == 0
    assert result["grade"] == "C"
    assert "excluded:agency" in result["reasons"]
    assert "excluded:competitor" in result["reasons"]
    assert result["risk_flags"] == ["excluded", "agency", "competitor"]


def test_keyword_terms_do_not_inflate_weak_comment_to_high_intent():
    service = LeadScoringService()

    result = service.score_lead(
        {
            "source_type": "comment",
            "keyword": "三角洲求陪玩",
            "comment_text": "哈哈哈，也给我来两个",
        }
    )

    assert result["total_score"] == 30
    assert result["grade"] == "C"
    assert result["reasons"] == ["source:comment"]
    assert result["matched_terms"] == []
