from __future__ import annotations

import os
from http import HTTPStatus
from typing import Any

from flask import Flask, jsonify, request, send_file, url_for
from providers.base import ImageGenerationRequest
from providers.registry import ProviderRegistry
from storage import ImageStore

app = Flask(__name__)
provider_registry = ProviderRegistry()
image_store = ImageStore(
    db_path=os.getenv("IMAGE_STORE_DB_PATH", "data/images.db"),
    image_dir=os.getenv("IMAGE_STORE_DIR", "data/images"),
)

def _parse_payload(payload: dict[str, Any]) -> tuple[str, ImageGenerationRequest]:
    prompt = (payload.get("prompt") or "").strip()
    if not prompt:
        raise ValueError("Field 'prompt' is required")

    provider = (payload.get("provider") or "openai").strip().lower()
    model = (payload.get("model") or "").strip() or None
    size = (payload.get("size") or "").strip() or None
    quality = (payload.get("quality") or "").strip() or None
    return provider, ImageGenerationRequest(
        prompt=prompt,
        model=model,
        size=size,
        quality=quality,
    )


@app.get("/")
def health() -> tuple[dict[str, str], int]:
    return {"status": "ok", "service": "ai-designer-backend"}, HTTPStatus.OK


@app.post("/api/images/generate")
def generate_image() -> tuple[Any, int]:
    payload = request.get_json(silent=True) or {}
    return _generate_from_payload(payload)


@app.get("/api/images")
def list_images() -> tuple[Any, int]:
    limit = request.args.get("limit", default=50, type=int) or 50
    offset = request.args.get("offset", default=0, type=int) or 0
    limit = max(1, min(limit, 200))
    offset = max(0, offset)

    records = image_store.list_generations(limit=limit, offset=offset)
    return jsonify([_serialize_record(record) for record in records]), HTTPStatus.OK


@app.get("/api/images/<image_id>")
def get_image(image_id: str) -> tuple[Any, int]:
    record = image_store.get_generation(image_id)
    if record is None:
        return jsonify({"error": "Image not found"}), HTTPStatus.NOT_FOUND
    return jsonify(_serialize_record(record)), HTTPStatus.OK


@app.get("/api/images/<image_id>/file")
def get_image_file(image_id: str) -> Any:
    image_path = image_store.image_file_path(image_id)
    if image_path is None:
        return jsonify({"error": "Image file not found"}), HTTPStatus.NOT_FOUND
    return send_file(image_path, mimetype="image/png")


def _generate_from_payload(payload: dict[str, Any]) -> tuple[Any, int]:
    try:
        provider_name, generation_request = _parse_payload(payload)
        provider = provider_registry.get(provider_name)
        result = provider.generate(generation_request)
        saved_record = image_store.save_generation(payload, result)
        return (
            jsonify(
                {
                    "provider": result.provider,
                    "model": result.model,
                    "prompt": result.prompt,
                    "image_base64": result.image_base64,
                    "size": result.size,
                    "quality": result.quality,
                    "revised_prompt": result.revised_prompt,
                    "image_id": saved_record["id"],
                    "image_url": url_for("get_image_file", image_id=saved_record["id"]),
                }
            ),
            HTTPStatus.OK,
        )
    except ValueError as exc:
        return jsonify({"error": str(exc)}), HTTPStatus.BAD_REQUEST
    except Exception as exc:
        app.logger.exception("Image generation failed")
        return jsonify({"error": "Image generation failed", "details": str(exc)}), HTTPStatus.BAD_GATEWAY


@app.post("/api/images/openai")
def generate_openai_image() -> tuple[Any, int]:
    payload = request.get_json(silent=True) or {}
    payload["provider"] = "openai"
    return _generate_from_payload(payload)


def _serialize_record(record: dict[str, Any]) -> dict[str, Any]:
    serialized = dict(record)
    image_id = serialized["id"]
    serialized["image_url"] = url_for("get_image_file", image_id=image_id)
    return serialized


if __name__ == "__main__":
    app.run(debug=True)
