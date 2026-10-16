"""Deterministic teaching fixture, deliberately unavailable for real source data."""

from __future__ import annotations

from metro_agent.domain.schemas import Analysis, Aspect, Content, EvidenceSpan, Relevance, Sentiment

ASPECT_TERMS = {
    Aspect.CROWDING: ("拥挤", "人多", "挤不上"),
    Aspect.PUNCTUALITY: ("晚点", "延误", "准点"),
    Aspect.EQUIPMENT: ("扶梯", "闸机", "电梯"),
    Aspect.CLEANLINESS: ("干净", "垃圾", "异味"),
    Aspect.SAFETY: ("安检", "骚扰"),
    Aspect.TICKETING: ("票价", "支付"),
    Aspect.STAFF: ("工作人员", "服务态度"),
    Aspect.TRANSFER: ("换乘",),
    Aspect.COMFORT: ("噪音", "闷热"),
    Aspect.ACCESSIBILITY: ("无障碍", "轮椅"),
}


class DemoAnnotator:
    version = "synthetic-rules:demo-v1:1"

    def analyze(self, content: Content) -> Analysis:
        if not content.synthetic:
            raise ValueError("offline_demo_requires_synthetic_content")
        text = content.text
        irrelevant = any(word in text for word in ("跑酷", "租房", "广告"))
        aspects = (
            []
            if irrelevant
            else [aspect for aspect, words in ASPECT_TERMS.items() if any(w in text for w in words)]
        )
        positive = any(word in text for word in ("干净", "准点", "方便", "友好", "满意"))
        negative = any(word in text for word in ("拥挤", "晚点", "坏了", "垃圾", "异味", "闷热"))
        sentiment = (
            Sentiment.UNKNOWN
            if irrelevant
            else Sentiment.MIXED
            if positive and negative
            else Sentiment.POSITIVE
            if positive
            else Sentiment.NEGATIVE
            if negative
            else Sentiment.NEUTRAL
        )
        event = not irrelevant and any(w in text for w in ("停运", "故障", "开通"))
        result = Analysis(
            relevance=Relevance.IRRELEVANT if irrelevant else Relevance.RELEVANT,
            sentiment=sentiment,
            aspects=aspects,
            event_candidate=event,
            event_type="事件候选" if event else None,
            evidence=[] if irrelevant else [EvidenceSpan(start=0, end=len(text), quote=text)],
            annotator="synthetic-rules",
            prompt_version="demo-v1",
            label_source="synthetic_rule",
        )
        result.verify_against(content)
        return result
