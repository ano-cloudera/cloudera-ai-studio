from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class EffectivePrompt:
    prompt_key: str
    content: str
    source: str  # project | workspace | global | file
    chain: list[str] = field(default_factory=list)
