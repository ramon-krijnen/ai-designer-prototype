from __future__ import annotations

from typing import Mapping

from providers.base import ImageProvider
from providers.openai import OpenAIImageProvider


class ProviderRegistry:
    def __init__(self) -> None:
        self._providers: dict[str, type[ImageProvider]] = {
            "openai": OpenAIImageProvider,
        }

    def get(self, name: str) -> ImageProvider:
        provider_cls = self._providers.get(name)
        if provider_cls is None:
            supported = ", ".join(sorted(self._providers.keys()))
            raise ValueError(f"Unsupported provider '{name}'. Supported: {supported}")
        return provider_cls()

    def names(self) -> Mapping[str, type[ImageProvider]]:
        return self._providers
