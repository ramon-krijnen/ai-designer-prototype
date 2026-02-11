from __future__ import annotations

import os

from openai import OpenAI

from providers.base import ImageGenerationRequest, ImageGenerationResult


class OpenAIImageProvider:
    name = "openai"
    OPTIONS = {
        "models": [
            {"id": "gpt-image-1", "label": "gpt-image-1"},
            {"id": "gpt-image-1.5", "label": "gpt-image-1.5"},
        ],
        "sizes": ["1024x1024", "1536x1024", "1024x1536"],
        "qualities": ["low", "medium", "high"],
        "default_model": "gpt-image-1",
        "default_size": "1024x1024",
        "default_quality": "medium",
        "supports_steps": False,
    }

    def __init__(self) -> None:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY is not set")
        self._client = OpenAI(api_key=api_key)

    def generate(self, request: ImageGenerationRequest) -> ImageGenerationResult:
        model = request.model or self.OPTIONS["default_model"]
        size = request.size or self.OPTIONS["default_size"]
        quality = request.quality or self.OPTIONS["default_quality"]

        allowed_models = {item["id"] for item in self.OPTIONS["models"]}
        allowed_sizes = set(self.OPTIONS["sizes"])
        allowed_qualities = set(self.OPTIONS["qualities"])

        if model not in allowed_models:
            raise ValueError(f"Unsupported OpenAI model '{model}'")
        if size not in allowed_sizes:
            raise ValueError(f"Unsupported OpenAI size '{size}'")
        if quality not in allowed_qualities:
            raise ValueError(f"Unsupported OpenAI quality '{quality}'")

        result = self._client.images.generate(
            model=model,
            prompt=request.prompt,
            size=size,
            quality=quality,
        )
        image = result.data[0]

        return ImageGenerationResult(
            provider=self.name,
            model=model,
            prompt=request.prompt,
            image_base64=image.b64_json,
            size=size,
            quality=quality,
            revised_prompt=getattr(image, "revised_prompt", None),
        )
