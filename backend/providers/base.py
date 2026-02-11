from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class ImageGenerationRequest:
    prompt: str
    model: str | None = None
    size: str | None = None
    quality: str | None = None


@dataclass(frozen=True)
class ImageGenerationResult:
    provider: str
    model: str
    prompt: str
    image_base64: str
    size: str | None = None
    quality: str | None = None
    revised_prompt: str | None = None


class ImageProvider(Protocol):
    name: str

    def generate(self, request: ImageGenerationRequest) -> ImageGenerationResult:
        ...
