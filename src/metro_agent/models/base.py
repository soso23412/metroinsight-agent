from typing import Protocol

from metro_agent.domain.schemas import Analysis, Content


class Annotator(Protocol):
    version: str

    def analyze(self, content: Content) -> Analysis | dict: ...
