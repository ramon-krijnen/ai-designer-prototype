from __future__ import annotations

import base64
import json
import os
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from providers.base import ImageGenerationRequest, ImageGenerationResult


class KreaImageProvider:
    name = "krea"
    OPTIONS = {
        "models": [
            {"id": "qwen_2512", "label": "qwen_2512 (Qwen 2512)"},
            {"id": "z_image", "label": "z_image (Z Image)"},
            {"id": "flux_1_dev", "label": "flux_1_dev (Flux 1 Dev)"},
        ],
        "sizes": ["1024x1024", "1024x576", "576x1024", "1536x1024", "1024x1536"],
        "qualities": [],
        "default_model": "qwen_2512",
        "default_size": "1024x1024",
        "default_quality": None,
        "supports_steps": True,
        "default_steps": 28,
    }

    _MODEL_PATH_ALIASES = {
        "qwen_2512": "qwen/2512",
        "qwen/2512": "qwen/2512",
        "z_image": "z-image/z-image",
        "z-image/z-image": "z-image/z-image",
        "flux_1_dev": "bfl/flux-1-dev",
        "bfl/flux-1-dev": "bfl/flux-1-dev",
    }

    def __init__(self) -> None:
        self._token = os.getenv("KREA_API_KEY")
        if not self._token:
            raise ValueError("KREA_API_KEY is not set")

        self._base_url = os.getenv("KREA_API_BASE_URL", "https://api.krea.ai").rstrip("/")
        self._default_model_alias = self.OPTIONS["default_model"]
        self._user_agent = os.getenv("KREA_USER_AGENT", "ai-designer-prototype/1.0")

    def generate(self, request: ImageGenerationRequest) -> ImageGenerationResult:
        model_alias = (request.model or self._default_model_alias).strip()
        model_path = self._resolve_model_path(model_alias)

        body: dict[str, object] = {"prompt": request.prompt}
        size_label = None

        if model_path == "z-image/z-image":
            width, height = self._resolve_dimensions(request.size)
            body["width"] = width
            body["height"] = height
            size_label = f"{width}x{height}"

        if model_path == "bfl/flux-1-dev":
            width, height = self._resolve_dimensions(request.size)
            body["width"] = width
            body["height"] = height
            size_label = f"{width}x{height}"
            body["steps"] = self._resolve_flux_steps(request.steps)

        endpoint = f"{self._base_url}/generate/image/{model_path}"
        payload = self._resolve_generation_payload(endpoint, body)
        image_base64 = self._extract_image_base64(payload)

        return ImageGenerationResult(
            provider=self.name,
            model=model_path,
            prompt=request.prompt,
            image_base64=image_base64,
            size=size_label,
            quality=request.quality,
            revised_prompt=None,
        )

    def _resolve_model_path(self, model_alias: str) -> str:
        resolved = self._MODEL_PATH_ALIASES.get(model_alias)
        if resolved:
            return resolved

        supported = ", ".join(sorted(self._MODEL_PATH_ALIASES.keys()))
        raise ValueError(f"Unsupported Krea model '{model_alias}'. Supported: {supported}")

    def _resolve_flux_steps(self, requested_steps: int | None) -> int:
        if requested_steps is not None:
            return self._validate_flux_steps(requested_steps)

        return self._validate_flux_steps(int(self.OPTIONS["default_steps"]))

    def _resolve_dimensions(self, requested_size: str | None) -> tuple[int, int]:
        if requested_size:
            parsed = self._parse_size(requested_size)
            if parsed:
                return parsed

        default_size = str(self.OPTIONS["default_size"])
        parsed_default = self._parse_size(default_size)
        if parsed_default:
            return parsed_default

        return self._validate_dimensions(1024, 1024)

    def _parse_size(self, value: str) -> tuple[int, int] | None:
        parts = value.lower().split("x")
        if len(parts) != 2:
            return None

        try:
            width = int(parts[0].strip())
            height = int(parts[1].strip())
        except ValueError:
            return None

        if width <= 0 or height <= 0:
            return None

        return self._validate_dimensions(width, height)

    def _validate_dimensions(self, width: int, height: int) -> tuple[int, int]:
        if not (512 <= width <= 2368):
            raise ValueError("Krea width must be between 512 and 2368")
        if not (512 <= height <= 2368):
            raise ValueError("Krea height must be between 512 and 2368")
        return width, height

    def _validate_flux_steps(self, steps: int) -> int:
        if not (1 <= steps <= 100):
            raise ValueError("Krea Flux steps must be between 1 and 100")
        return steps

    def _post_json(self, url: str, body: dict[str, object]) -> dict[str, object]:
        request = Request(
            url,
            data=json.dumps(body).encode("utf-8"),
            method="POST",
            headers=self._base_headers(content_type_json=True),
        )

        try:
            with urlopen(request, timeout=60) as response:
                response_body = response.read().decode("utf-8")
        except HTTPError as exc:
            details = exc.read().decode("utf-8", errors="replace")
            if exc.code == 403 and "error code: 1010" in details.lower():
                raise RuntimeError(
                    "Krea access blocked by Cloudflare (1010). Check API key scope and allowlist this server IP with Krea support."
                ) from exc
            raise RuntimeError(f"Krea API error ({exc.code}): {details}") from exc
        except URLError as exc:
            raise RuntimeError(f"Krea API connection failed: {exc.reason}") from exc

        try:
            payload = json.loads(response_body)
        except json.JSONDecodeError as exc:
            raise RuntimeError("Krea API returned invalid JSON") from exc

        if not isinstance(payload, dict):
            raise RuntimeError("Krea API returned an unexpected payload")

        return payload

    def _get_json(self, url: str) -> dict[str, object]:
        request = Request(
            url,
            method="GET",
            headers=self._base_headers(content_type_json=False),
        )

        try:
            with urlopen(request, timeout=60) as response:
                response_body = response.read().decode("utf-8")
        except HTTPError as exc:
            details = exc.read().decode("utf-8", errors="replace")
            if exc.code == 403 and "error code: 1010" in details.lower():
                raise RuntimeError(
                    "Krea access blocked by Cloudflare (1010). Check API key scope and allowlist this server IP with Krea support."
                ) from exc
            raise RuntimeError(f"Krea API error ({exc.code}): {details}") from exc
        except URLError as exc:
            raise RuntimeError(f"Krea API connection failed: {exc.reason}") from exc

        try:
            payload = json.loads(response_body)
        except json.JSONDecodeError as exc:
            raise RuntimeError("Krea API returned invalid JSON") from exc

        if not isinstance(payload, dict):
            raise RuntimeError("Krea API returned an unexpected payload")

        return payload

    def _resolve_generation_payload(self, endpoint: str, body: dict[str, object]) -> dict[str, object]:
        payload = self._post_json(endpoint, body)
        job_id = payload.get("job_id")
        if not isinstance(job_id, str) or not job_id.strip():
            return payload

        poll_interval = float((os.getenv("KREA_POLL_INTERVAL_SECONDS") or "2").strip() or "2")
        timeout_seconds = int((os.getenv("KREA_JOB_TIMEOUT_SECONDS") or "120").strip() or "120")
        deadline = time.monotonic() + max(1, timeout_seconds)
        job_url = f"{self._base_url}/jobs/{job_id.strip()}"

        while time.monotonic() < deadline:
            job_payload = self._get_json(job_url)
            status = str(job_payload.get("status") or "").strip().lower()
            if status == "completed":
                return job_payload

            if status in {"failed", "error", "cancelled", "canceled"}:
                raise RuntimeError(f"Krea job failed with status '{status}'")

            time.sleep(max(0.2, poll_interval))

        raise RuntimeError(f"Krea job timed out after {timeout_seconds} seconds")

    def _extract_image_base64(self, payload: dict[str, object]) -> str:
        candidates: list[object] = []

        images = payload.get("images")
        data = payload.get("data")
        image_urls = payload.get("image_urls")
        result = payload.get("result")

        if isinstance(images, list):
            candidates.extend(images)
        if isinstance(data, list):
            candidates.extend(data)
        if isinstance(image_urls, list):
            candidates.extend(image_urls)
        if isinstance(result, dict):
            result_urls = result.get("urls")
            if isinstance(result_urls, list):
                candidates.extend(result_urls)
            for key in ("image_url", "image", "image_base64", "b64_json", "base64"):
                value = result.get(key)
                if value:
                    candidates.append(value)

        for key in ("image_url", "image", "image_base64", "b64_json", "base64"):
            value = payload.get(key)
            if value:
                candidates.append(value)

        for candidate in candidates:
            resolved = self._resolve_candidate_base64(candidate)
            if resolved:
                return resolved

        raise RuntimeError("Krea API response did not contain an image")

    def _resolve_candidate_base64(self, candidate: object) -> str | None:
        if isinstance(candidate, str):
            return self._string_to_base64(candidate)

        if not isinstance(candidate, dict):
            return None

        for key in ("url", "src", "image_url"):
            value = candidate.get(key)
            if isinstance(value, str):
                resolved = self._string_to_base64(value)
                if resolved:
                    return resolved

        for key in ("image_base64", "b64_json", "base64"):
            value = candidate.get(key)
            if isinstance(value, str):
                resolved = self._string_to_base64(value)
                if resolved:
                    return resolved

        return None

    def _string_to_base64(self, value: str) -> str | None:
        trimmed = value.strip()
        if not trimmed:
            return None

        if trimmed.startswith("data:"):
            _, _, base64_part = trimmed.partition(",")
            return base64_part.strip() or None

        parsed = urlparse(trimmed)
        if parsed.scheme in {"http", "https"}:
            image_bytes = self._download_bytes(trimmed)
            return base64.b64encode(image_bytes).decode("ascii")

        return trimmed

    def _download_bytes(self, url: str) -> bytes:
        request = Request(
            url,
            method="GET",
            headers=self._base_headers(content_type_json=False),
        )
        try:
            with urlopen(request, timeout=60) as response:
                return response.read()
        except HTTPError as exc:
            details = exc.read().decode("utf-8", errors="replace")
            if exc.code == 403 and "error code: 1010" in details.lower():
                raise RuntimeError(
                    "Krea image download blocked by Cloudflare (1010). Check API key scope and allowlist this server IP with Krea support."
                ) from exc
            raise RuntimeError(f"Failed to download image ({exc.code}): {details}") from exc
        except URLError as exc:
            raise RuntimeError(f"Failed to download image: {exc.reason}") from exc

    def _base_headers(self, *, content_type_json: bool) -> dict[str, str]:
        headers = {
            "Authorization": f"Bearer {self._token}",
            "Accept": "application/json",
            "User-Agent": self._user_agent,
        }
        if content_type_json:
            headers["Content-Type"] = "application/json"
        return headers
