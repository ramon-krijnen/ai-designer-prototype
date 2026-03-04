from __future__ import annotations

import base64
import json
import logging
import os
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

logger = logging.getLogger(__name__)

from providers.base import ImageGenerationRequest, ImageGenerationResult


class QwenImageProvider:
    name = "qwen"
    OPTIONS = {
        "models": [
            {"id": "qwen-image-edit-plus-2025-12-15", "label": "qwen-image-edit-plus-2025-12-15", "supports_image_edit": True},
            {"id": "qwen-image-edit-plus", "label": "qwen-image-edit-plus", "supports_image_edit": True},
            {"id": "qwen-image-edit-max", "label": "qwen-image-edit-max", "supports_image_edit": True},
        ],
        "sizes": ["1024*1024", "1024*1536", "1536*1024", "1280*720", "720*1280", "768*1152", "1152*768"],
        "qualities": [],
        "default_model": "qwen-image-edit-plus-2025-12-15",
        "default_size": "1024*1024",
        "default_quality": None,
        "supports_steps": False,
        "supports_image_edit": True,
    }

    _VALID_MODELS = {
        "qwen-image-edit-plus-2025-12-15",
        "qwen-image-edit-plus",
        "qwen-image-edit-max",
    }

    def __init__(self) -> None:
        self._api_key = os.getenv("DASHSCOPE_API_KEY")
        if not self._api_key:
            raise ValueError("DASHSCOPE_API_KEY is not set")
        self._base_url = os.getenv(
            "DASHSCOPE_API_BASE_URL",
            "https://dashscope-intl.aliyuncs.com/api/v1",
        ).rstrip("/")

    def generate(self, request: ImageGenerationRequest) -> ImageGenerationResult:
        model = (request.model or self.OPTIONS["default_model"]).strip()
        if model not in self._VALID_MODELS:
            supported = ", ".join(sorted(self._VALID_MODELS))
            raise ValueError(f"Unsupported Qwen model '{model}'. Supported: {supported}")

        size = self._resolve_size(request.size)

        content: list[dict[str, str]] = []
        for image in request.reference_images:
            data_uri = f"data:{image.mime_type};base64,{base64.b64encode(image.data).decode('ascii')}"
            content.append({"image": data_uri})
        content.append({"text": request.prompt})

        parameters: dict[str, object] = {"n": 1, "watermark": False}
        if size:
            parameters["size"] = size

        body = {
            "model": model,
            "input": {"messages": [{"role": "user", "content": content}]},
            "parameters": parameters,
        }

        endpoint = f"{self._base_url}/services/aigc/multimodal-generation/generation"
        logger.info("qwen generate: POST %s model=%s size=%s", endpoint, model, size)
        response_payload = self._post_json(endpoint, body)
        image_base64 = self._extract_image_base64(response_payload)

        return ImageGenerationResult(
            provider=self.name,
            model=model,
            prompt=request.prompt,
            image_base64=image_base64,
            size=size or request.size,
            quality=None,
            revised_prompt=None,
        )

    def _resolve_size(self, requested_size: str | None) -> str | None:
        if not requested_size:
            return None
        normalized = requested_size.strip().replace("x", "*").replace("X", "*")
        parts = normalized.split("*")
        if len(parts) != 2:
            return None
        try:
            width = int(parts[0].strip())
            height = int(parts[1].strip())
        except ValueError:
            return None
        if not (512 <= width <= 2048 and 512 <= height <= 2048):
            raise ValueError(
                f"Qwen image dimensions must be between 512 and 2048 pixels, got {width}x{height}"
            )
        return f"{width}*{height}"

    def _post_json(self, url: str, body: dict[str, object]) -> dict[str, object]:
        req = Request(
            url,
            data=json.dumps(body).encode("utf-8"),
            method="POST",
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
        )
        try:
            with urlopen(req, timeout=120) as response:
                response_body = response.read().decode("utf-8")
        except HTTPError as exc:
            details = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Qwen API error ({exc.code}): {details}") from exc
        except URLError as exc:
            raise RuntimeError(f"Qwen API connection failed: {exc.reason}") from exc

        try:
            payload = json.loads(response_body)
        except json.JSONDecodeError as exc:
            raise RuntimeError("Qwen API returned invalid JSON") from exc

        if not isinstance(payload, dict):
            raise RuntimeError("Qwen API returned an unexpected payload")

        code = payload.get("code")
        if code is not None and code != "Success":
            raise RuntimeError(f"Qwen API error: {payload.get('message') or code}")

        return payload

    def _extract_image_base64(self, payload: dict[str, object]) -> str:
        output = payload.get("output")
        if not isinstance(output, dict):
            raise RuntimeError("Qwen API response missing 'output'")
        choices = output.get("choices")
        if not isinstance(choices, list) or not choices:
            raise RuntimeError("Qwen API response missing 'output.choices'")
        message = choices[0].get("message") if isinstance(choices[0], dict) else None
        if not isinstance(message, dict):
            raise RuntimeError("Qwen API response missing 'output.choices[0].message'")
        content = message.get("content")
        if not isinstance(content, list):
            raise RuntimeError("Qwen API response missing 'output.choices[0].message.content'")
        for item in content:
            if not isinstance(item, dict):
                continue
            image_url = item.get("image")
            if isinstance(image_url, str) and image_url.strip():
                return self._download_to_base64(image_url.strip())
        raise RuntimeError("Qwen API response did not contain an image URL")

    def _download_to_base64(self, url: str) -> str:
        req = Request(url, method="GET", headers={"Accept": "*/*"})
        try:
            with urlopen(req, timeout=60) as response:
                return base64.b64encode(response.read()).decode("ascii")
        except HTTPError as exc:
            details = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Failed to download Qwen image ({exc.code}): {details}") from exc
        except URLError as exc:
            raise RuntimeError(f"Failed to download Qwen image: {exc.reason}") from exc