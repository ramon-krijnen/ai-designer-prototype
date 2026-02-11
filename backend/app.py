from __future__ import annotations

import os
from http import HTTPStatus
from typing import Any
from uuid import uuid4

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
    steps_raw = payload.get("steps")
    steps = None
    if steps_raw is not None and str(steps_raw).strip() != "":
        try:
            steps = int(steps_raw)
        except (TypeError, ValueError):
            raise ValueError("Field 'steps' must be an integer")
        if steps <= 0:
            raise ValueError("Field 'steps' must be greater than 0")

    return provider, ImageGenerationRequest(
        prompt=prompt,
        model=model,
        size=size,
        quality=quality,
        steps=steps,
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


@app.get("/api/runs")
def list_runs() -> tuple[Any, int]:
    limit = request.args.get("limit", default=25, type=int) or 25
    offset = request.args.get("offset", default=0, type=int) or 0
    limit = max(1, min(limit, 100))
    offset = max(0, offset)

    runs = image_store.list_runs(limit=limit, offset=offset)
    serialized_runs = []
    for run in runs:
        serialized_runs.append(
            {
                "run_id": run["run_id"],
                "created_at": run["created_at"],
                "image_count": run["image_count"],
                "images": [_serialize_record(image) for image in run["images"]],
            }
        )
    return jsonify(serialized_runs), HTTPStatus.OK




@app.get("/api/providers")
def list_providers() -> tuple[Any, int]:
    return jsonify(provider_registry.metadata()), HTTPStatus.OK


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
        models_raw = payload.get("models")
        models: list[str] = []
        if isinstance(models_raw, list):
            for model_entry in models_raw:
                model_name = str(model_entry).strip()
                if model_name:
                    models.append(model_name)
        if generation_request.model:
            models = [generation_request.model]
        if not models:
            models = [generation_request.model] if generation_request.model else [""]

        provider = provider_registry.get(provider_name)
        run_id = str(uuid4())
        revised_prompt = None
        generation_results = []

        for model_name in models:
            request_for_model = ImageGenerationRequest(
                prompt=generation_request.prompt,
                model=model_name or None,
                size=generation_request.size,
                quality=generation_request.quality,
                steps=generation_request.steps,
            )
            result = provider.generate(request_for_model)
            if revised_prompt is None and result.revised_prompt:
                revised_prompt = result.revised_prompt
            generation_results.append(result)

        saved_records = []
        try:
            for result in generation_results:
                saved_records.append(image_store.save_generation(payload, result, run_id=run_id))
        except Exception as exc:
            app.logger.exception("Failed to persist image generation run; rolling back")
            image_store.delete_run(run_id)
            raise RuntimeError("Failed to persist generated images") from exc

        responses = []
        for index, result in enumerate(generation_results):
            saved_record = saved_records[index]
            responses.append(
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
                    "run_id": run_id,
                }
            )

        first = responses[0]
        return (
            jsonify(
                {
                    "provider": first["provider"],
                    "model": first["model"],
                    "prompt": first["prompt"],
                    "image_base64": first["image_base64"],
                    "size": first["size"],
                    "quality": first["quality"],
                    "revised_prompt": revised_prompt,
                    "image_id": first["image_id"],
                    "image_url": first["image_url"],
                    "run_id": run_id,
                    "images": responses,
                }
            ),
            HTTPStatus.OK,
        )
    except ValueError as exc:
        return jsonify({"error": str(exc)}), HTTPStatus.BAD_REQUEST
    except Exception:
        app.logger.exception("Image generation failed")
        return jsonify({"error": "Image generation failed"}), HTTPStatus.BAD_GATEWAY


@app.post("/api/images/openai")
def generate_openai_image() -> tuple[Any, int]:
    payload = request.get_json(silent=True) or {}
    payload["provider"] = "openai"
    return _generate_from_payload(payload)


@app.post("/api/images/krea")
def generate_krea_image() -> tuple[Any, int]:
    payload = request.get_json(silent=True) or {}
    payload["provider"] = "krea"
    return _generate_from_payload(payload)


def _serialize_record(record: dict[str, Any]) -> dict[str, Any]:
    serialized = dict(record)
    image_id = serialized["id"]
    serialized["image_url"] = url_for("get_image_file", image_id=image_id)
    return serialized


if __name__ == "__main__":
    app.run(debug=True)
