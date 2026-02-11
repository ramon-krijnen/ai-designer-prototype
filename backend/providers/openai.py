from __future__ import annotations

import os

from openai import OpenAI

from providers.base import ImageGenerationRequest, ImageGenerationResult


class OpenAIImageProvider:
    name = "openai"

    def __init__(self) -> None:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY is not set")
        self._client = OpenAI(api_key=api_key)

    def generate(self, request: ImageGenerationRequest) -> ImageGenerationResult:
        model = request.model or os.getenv("OPENAI_IMAGE_MODEL", "gpt-image-1")
        size = request.size or os.getenv("OPENAI_IMAGE_SIZE", "1024x1024")
        quality = request.quality or os.getenv("OPENAI_IMAGE_QUALITY", "standard")

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
