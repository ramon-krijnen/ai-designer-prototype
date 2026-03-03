from __future__ import annotations

import base64
import os
from pathlib import Path

from google import genai
from google.genai import types

from providers.base import ImageGenerationRequest, ImageGenerationResult


class GeminiImageProvider:
    name = "gemini"
    OPTIONS = {
        "models": [
            {"id": "gemini-2.5-flash-image", "label": "gemini-2.5-flash-image (Nano Banana)"},
            {"id": "gemini-3-pro-image-preview", "label": "gemini-3-pro-image-preview (Nano Banana Pro)"},
        ],
        "sizes": ["1:1", "3:2", "2:3", "3:4", "4:3", "4:5", "5:4", "9:16", "16:9", "21:9"],
        "qualities": [],
        "default_model": "gemini-2.5-flash-image",
        "default_size": "1:1",
        "default_quality": None,
        "supports_steps": False,
        "supports_image_edit": True,
    }

    _MODEL_ALIASES = {
        "nano-banana": "gemini-2.5-flash-image",
        "nano banana": "gemini-2.5-flash-image",
        "nanobanana": "gemini-2.5-flash-image",
        "gemini-2.5-flash-image": "gemini-2.5-flash-image",
        "gemini-2.5-flash-image-preview": "gemini-2.5-flash-image",
        "nano-banana-pro": "gemini-3-pro-image-preview",
        "nano banana pro": "gemini-3-pro-image-preview",
        "nanobanana-pro": "gemini-3-pro-image-preview",
        "nanobanana pro": "gemini-3-pro-image-preview",
        "gemini-3-pro-image-preview": "gemini-3-pro-image-preview",
    }
    _ASPECT_RATIO_ALIASES = {
        "1:1": "1:1",
        "1024x1024": "1:1",
        "3:2": "3:2",
        "1536x1024": "3:2",
        "2:3": "2:3",
        "1024x1536": "2:3",
        "3:4": "3:4",
        "4:3": "4:3",
        "4:5": "4:5",
        "5:4": "5:4",
        "9:16": "9:16",
        "576x1024": "9:16",
        "16:9": "16:9",
        "1024x576": "16:9",
        "21:9": "21:9",
    }

    def __init__(self) -> None:
        api_key = (
            os.getenv("GEMINI_API_KEY")
            or os.getenv("AI_STUDIO_API_KEY")
            or os.getenv("GOOGLE_API_KEY")
            or os.getenv("GOOGLE_CLOUD_KEY")
            or os.getenv("GOOGLE_CLOUD_API_KEY")
            or ""
        ).strip()
        if api_key:
            self._client = genai.Client(api_key=api_key)
            return

        project = (os.getenv("GOOGLE_CLOUD_PROJECT") or os.getenv("GCP_PROJECT") or "").strip()
        if not project:
            raise ValueError(
                "Gemini requires GEMINI_API_KEY/GOOGLE_API_KEY/AI_STUDIO_API_KEY for AI Studio API key mode, or GOOGLE_CLOUD_PROJECT for ADC mode"
            )

        credentials_path = (os.getenv("GOOGLE_APPLICATION_CREDENTIALS") or "").strip()
        if credentials_path:
            path_obj = Path(credentials_path)
            if path_obj.is_dir():
                raise ValueError(
                    "GOOGLE_APPLICATION_CREDENTIALS points to a directory. Set it to a service-account JSON file path."
                )
            if not path_obj.exists():
                raise ValueError(
                    f"GOOGLE_APPLICATION_CREDENTIALS file not found: {credentials_path}"
                )

        location = (os.getenv("GOOGLE_CLOUD_LOCATION") or "global").strip() or "global"
        self._client = genai.Client(vertexai=True, project=project, location=location)

    def generate(self, request: ImageGenerationRequest) -> ImageGenerationResult:
        model_alias = (request.model or self.OPTIONS["default_model"]).strip()
        model = self._resolve_model(model_alias)
        parts: list[types.Part] = [types.Part.from_text(text=request.prompt)]
        for image in request.reference_images:
            parts.append(types.Part.from_bytes(data=image.data, mime_type=image.mime_type))

        aspect_ratio = self._resolve_aspect_ratio(request.size)
        config_args: dict[str, object] = {
            "response_modalities": [types.Modality.TEXT, types.Modality.IMAGE],
            "candidate_count": 1,
        }
        if aspect_ratio:
            config_args["image_config"] = types.ImageConfig(aspect_ratio=aspect_ratio)

        response = self._client.models.generate_content(
            model=model,
            contents=parts,
            config=types.GenerateContentConfig(**config_args),
        )
        image_base64 = self._extract_image_base64(response)
        revised_prompt = self._extract_text(response)

        return ImageGenerationResult(
            provider=self.name,
            model=model,
            prompt=request.prompt,
            image_base64=image_base64,
            size=aspect_ratio or request.size,
            quality=request.quality,
            revised_prompt=revised_prompt,
        )

    def _resolve_model(self, model_alias: str) -> str:
        resolved = self._MODEL_ALIASES.get(model_alias.strip())
        if resolved:
            return resolved
        supported = ", ".join(sorted(self._MODEL_ALIASES.keys()))
        raise ValueError(f"Unsupported Gemini model '{model_alias}'. Supported: {supported}")

    def _resolve_aspect_ratio(self, requested_size: str | None) -> str | None:
        if not requested_size:
            return None
        return self._ASPECT_RATIO_ALIASES.get(requested_size.strip().lower())

    def _extract_image_base64(self, response: object) -> str:
        candidates = getattr(response, "candidates", None)
        if not isinstance(candidates, list):
            raise RuntimeError("Gemini response did not contain candidates")

        for candidate in candidates:
            content = getattr(candidate, "content", None)
            parts = getattr(content, "parts", None)
            if not isinstance(parts, list):
                continue
            for part in parts:
                inline_data = getattr(part, "inline_data", None)
                if inline_data is None:
                    continue
                data = getattr(inline_data, "data", None)
                if isinstance(data, bytes) and data:
                    return base64.b64encode(data).decode("ascii")
                if isinstance(data, str) and data.strip():
                    return data.strip()

        raise RuntimeError("Gemini response did not contain an image")

    def _extract_text(self, response: object) -> str | None:
        candidates = getattr(response, "candidates", None)
        if not isinstance(candidates, list):
            return None
        for candidate in candidates:
            content = getattr(candidate, "content", None)
            parts = getattr(content, "parts", None)
            if not isinstance(parts, list):
                continue
            text_parts: list[str] = []
            for part in parts:
                value = getattr(part, "text", None)
                if isinstance(value, str) and value.strip():
                    text_parts.append(value.strip())
            if text_parts:
                return " ".join(text_parts)
        return None
