from __future__ import annotations

from typing import Mapping

from providers.base import ImageProvider
from providers.krea import KreaImageProvider
from providers.openai import OpenAIImageProvider


class ProviderRegistry:
    def __init__(self) -> None:
        self._providers: dict[str, type[ImageProvider]] = {
            "openai": OpenAIImageProvider,
            "krea": KreaImageProvider,
        }

    def get(self, name: str) -> ImageProvider:
        provider_cls = self._providers.get(name)
        if provider_cls is None:
            supported = ", ".join(sorted(self._providers.keys()))
            raise ValueError(f"Unsupported provider '{name}'. Supported: {supported}")
        return provider_cls()

    def names(self) -> Mapping[str, type[ImageProvider]]:
        return self._providers

    def metadata(self) -> dict[str, dict[str, object]]:
        result: dict[str, dict[str, object]] = {}
        for name, provider_cls in self._providers.items():
            options = getattr(provider_cls, "OPTIONS", None)
            if isinstance(options, dict):
                result[name] = options
        return result
