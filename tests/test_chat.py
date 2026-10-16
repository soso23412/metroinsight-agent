import json

import httpx
import pytest
from pydantic import SecretStr

from metro_agent.config import ModelConfig
from metro_agent.models.chat import LiveChat, ModelFailure


@pytest.fixture
def config():
    return ModelConfig(
        base_url="https://provider.example/v1",
        model="fixture-model",
        api_key=SecretStr("test-placeholder"),
        input_usd_per_million=1,
        output_usd_per_million=2,
    )


def response(calls=None):
    return {
        "choices": [
            {
                "finish_reason": "tool_calls",
                "message": {
                    "tool_calls": calls
                    or [
                        {
                            "id": "call-1",
                            "function": {"name": "describe_dataset", "arguments": "{}"},
                        }
                    ]
                },
            }
        ],
        "usage": {"prompt_tokens": 40, "completion_tokens": 10},
    }


def test_wire_protocol_and_no_secret_in_identity(config):
    def handler(request):
        body = json.loads(request.content)
        assert request.url == "https://provider.example/v1/chat/completions"
        assert body["tools"][0]["type"] == "function" and body["stream"] is False
        return httpx.Response(200, json=response())

    client = LiveChat(config, httpx.MockTransport(handler))
    result = client.decide([{"role": "user", "content": "test"}], 5)
    assert result.calls[0].name == "describe_dataset" and result.input_tokens == 40
    assert "test-placeholder" not in client.identity
    assert client.reserve([])[0] > config.max_output_tokens


@pytest.mark.parametrize(
    ("status", "code", "uncertain"),
    [
        (429, "provider_rate_limited", False),
        (401, "provider_request_rejected", False),
        (302, "provider_request_rejected", False),
        (503, "provider_server_error", True),
    ],
)
def test_http_failures_redacted_no_hidden_retry(config, status, code, uncertain):
    count = 0

    def handler(request):
        nonlocal count
        count += 1
        return httpx.Response(status, text="private-provider-error")

    with pytest.raises(ModelFailure) as exc:
        LiveChat(config, httpx.MockTransport(handler)).decide([], 1)
    assert exc.value.code == code and exc.value.uncertain == uncertain and count == 1
    assert "private-provider-error" not in str(exc.value)


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"choices": []},
        {"choices": [{"finish_reason": "stop"}]},
        response([{"id": "x", "function": {"name": "x", "arguments": "not JSON"}}]),
        response([{"id": "x", "function": {"name": "x", "arguments": "[]"}}]),
    ],
)
def test_invalid_provider_output_fails_closed(config, payload):
    with pytest.raises(ModelFailure):
        LiveChat(config, httpx.MockTransport(lambda _: httpx.Response(200, json=payload))).decide(
            [], 1
        )


def test_timeout_and_oversize(config):
    def timeout(request):
        raise httpx.ReadTimeout("secret-body")

    with pytest.raises(ModelFailure, match="network_uncertain"):
        LiveChat(config, httpx.MockTransport(timeout)).decide([], 1)
    with pytest.raises(ModelFailure, match="too_large"):
        LiveChat(
            config, httpx.MockTransport(lambda _: httpx.Response(200, content=b"x" * 1_000_001))
        ).decide([], 1)


@pytest.mark.parametrize(
    "url", ["http://example.com", "https://user:pass@example.com", "https://example.com?k=secret"]
)
def test_provider_configuration_rejects_credentials_in_url(config, url):
    with pytest.raises(ValueError):
        ModelConfig(**(config.model_dump() | {"base_url": url}))
