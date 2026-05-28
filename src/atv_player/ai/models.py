from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class AIProviderConfig:
    base_url: str
    api_key: str
    chat_model: str
    timeout_seconds: int = 30

    @property
    def is_complete(self) -> bool:
        return bool(
            self.base_url.strip()
            and self.api_key.strip()
            and self.chat_model.strip()
        )


@dataclass(slots=True)
class AICompletionResult:
    content: str
    raw: dict[str, Any] = field(default_factory=dict)


class AIError(RuntimeError):
    pass
