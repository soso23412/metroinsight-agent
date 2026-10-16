from __future__ import annotations

import os
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, field_validator

from metro_agent.domain.schemas import Contract


class ModelConfig(Contract):
    base_url: str
    model: str = Field(min_length=1, max_length=100)
    api_key: SecretStr
    input_usd_per_million: float = Field(gt=0)
    output_usd_per_million: float = Field(gt=0)
    max_output_tokens: int = Field(default=2048, ge=128, le=8192)

    @field_validator("base_url")
    @classmethod
    def safe_url(cls, value: str) -> str:
        parsed = urlsplit(value)
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("provider_requires_https_without_credentials_or_query")
        return value.rstrip("/")

    @classmethod
    def from_env(cls) -> ModelConfig:
        # Invoked only by explicitly selected live execution. No dotenv auto-reading.
        return cls(
            base_url=os.environ["METRO_MODEL_BASE_URL"],
            model=os.environ["METRO_MODEL"],
            api_key=SecretStr(os.environ["METRO_MODEL_API_KEY"]),
            input_usd_per_million=float(os.environ["METRO_INPUT_USD_PER_MILLION"]),
            output_usd_per_million=float(os.environ["METRO_OUTPUT_USD_PER_MILLION"]),
        )
