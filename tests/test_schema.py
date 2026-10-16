from datetime import datetime

import pytest
from pydantic import ValidationError

from metro_agent.domain.schemas import Analysis, Aspect, EvidenceSpan
from metro_agent.models.demo import DemoAnnotator


def test_invalid_enum_is_rejected(make_content):
    valid = DemoAnnotator().analyze(make_content()).model_dump()
    valid["sentiment"] = "invented-label"
    with pytest.raises(ValidationError):
        Analysis.model_validate(valid)


def test_unsupported_fields_cannot_be_silently_accepted(make_content):
    valid = DemoAnnotator().analyze(make_content()).model_dump()
    valid["accuracy"] = 0.99
    with pytest.raises(ValidationError):
        Analysis.model_validate(valid)


def test_naive_timestamp_is_rejected(make_content):
    with pytest.raises(ValidationError):
        make_content(published_at=datetime(2026, 1, 1))


def test_multiple_aspects_do_not_replace_sentiment(make_content):
    content = make_content(text="换乘方便，但地铁拥挤。")
    result = DemoAnnotator().analyze(content)
    assert result.sentiment == "mixed"
    assert set(result.aspects) == {Aspect.TRANSFER, Aspect.CROWDING}


def test_neutral_service_description_is_not_negative(make_content):
    result = DemoAnnotator().analyze(make_content(text="今天地铁人多，记录一下。"))
    assert result.sentiment == "neutral"
    assert result.aspects == [Aspect.CROWDING]


def test_fabricated_or_misaligned_evidence_is_rejected(make_content):
    content = make_content()
    analysis = DemoAnnotator().analyze(content)
    analysis.evidence = [EvidenceSpan(start=0, end=3, quote="不存在")]
    with pytest.raises(ValueError, match="evidence"):
        analysis.verify_against(content)


def test_demo_cannot_analyze_private_real_data(make_content):
    with pytest.raises(ValueError, match="synthetic"):
        DemoAnnotator().analyze(make_content(synthetic=False))
