import json

import httpx
from pydantic import SecretStr

from metro_agent.agent.contracts import Limits
from metro_agent.annotation.live import annotate_live
from metro_agent.config import ModelConfig
from metro_agent.demo import seed_demo
from metro_agent.models.chat import LiveChat
from metro_agent.storage.db import Store


def client(handler):
    config = ModelConfig(
        base_url="https://fixture.example/v1",
        model="test-model",
        api_key=SecretStr("placeholder"),
        input_usd_per_million=1,
        output_usd_per_million=1,
    )
    return LiveChat(config, httpx.MockTransport(handler))


def test_structured_model_annotation_cached_and_provenance_validated(tmp_path):
    calls = 0

    def handler(request):
        nonlocal calls
        calls += 1
        body = json.loads(request.content)
        text = json.loads(body["messages"][1]["content"])["text"]
        system = body["messages"][0]["content"]
        annotator = system.split("annotator=")[1].split(";")[0]
        prompt = system.split("prompt_version=")[1].split(";")[0]
        analysis = {
            "relevance": "relevant",
            "sentiment": "neutral",
            "aspects": [],
            "evidence": [{"start": 0, "end": len(text), "quote": text}],
            "annotator": annotator,
            "prompt_version": prompt,
            "label_source": "model",
        }
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "finish_reason": "tool_calls",
                        "message": {
                            "tool_calls": [
                                {
                                    "id": "label-1",
                                    "function": {
                                        "name": "label_feedback",
                                        "arguments": json.dumps(analysis),
                                    },
                                }
                            ]
                        },
                    }
                ],
                "usage": {"prompt_tokens": 30, "completion_tokens": 30},
            },
        )

    with Store(tmp_path / "db.sqlite3") as store:
        dataset = seed_demo(store)
        first = annotate_live(store, dataset, client(handler), Limits(max_steps=1), limit=1)
        assert first["succeeded"] == 1 and first["version"].startswith("chat-")
        again = annotate_live(store, dataset, client(handler), Limits(max_steps=1), limit=1)
        assert again["cached"] == 1 and again["succeeded"] == 1 and calls == 2


def test_uncertain_annotation_not_repeated_and_budget_prevents_call(tmp_path):
    calls = 0

    def handler(request):
        nonlocal calls
        calls += 1
        raise httpx.ReadTimeout("do not expose")

    with Store(tmp_path / "db.sqlite3") as store:
        dataset = seed_demo(store)
        no_budget = annotate_live(store, dataset, client(handler), Limits(max_cost_usd=0))
        assert no_budget["stop_reason"] == "cost_limit" and calls == 0
        first = annotate_live(store, dataset, client(handler), Limits())
        assert first["failed"] == 1 and calls == 1
        repeated = annotate_live(store, dataset, client(handler), Limits())
        assert repeated["stop_reason"] == "prior_attempt_requires_review" and calls == 1
