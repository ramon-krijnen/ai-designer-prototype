from __future__ import annotations

import base64
import binascii
import os
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime
from http import HTTPStatus
from typing import Any
from uuid import uuid4

from flask import Flask, jsonify, request, send_file, url_for
from providers.base import ImageGenerationRequest, InputImage
from providers.registry import ProviderRegistry
from storage import ImageStore

app = Flask(__name__)
provider_registry = ProviderRegistry()
image_store = ImageStore(
    db_path=os.getenv("IMAGE_STORE_DB_PATH", "data/images.db"),
    image_dir=os.getenv("IMAGE_STORE_DIR", "data/images"),
)
generation_executor = ThreadPoolExecutor(max_workers=max(1, int(os.getenv("GENERATION_WORKERS", "4"))))
generation_jobs: dict[str, dict[str, Any]] = {}
generation_jobs_lock = threading.Lock()
MAX_EDIT_IMAGES = 16
MAX_EDIT_IMAGE_BYTES = 50 * 1024 * 1024


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
    reference_images = _parse_reference_images(payload.get("edit_images"))

    return provider, ImageGenerationRequest(
        prompt=prompt,
        model=model,
        size=size,
        quality=quality,
        steps=steps,
        reference_images=reference_images,
    )


@app.get("/")
def health() -> tuple[dict[str, str], int]:
    return {"status": "ok", "service": "ai-designer-backend"}, HTTPStatus.OK


@app.post("/api/images/generate")
def generate_image() -> tuple[Any, int]:
    payload = request.get_json(silent=True) or {}
    return _start_async_generation(payload)


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


@app.get("/api/runs/<run_id>/status")
def get_run_status(run_id: str) -> tuple[Any, int]:
    with generation_jobs_lock:
        job = generation_jobs.get(run_id)

    images = image_store.list_run_images(run_id)
    if job is None and not images:
        return jsonify({"error": "Run not found"}), HTTPStatus.NOT_FOUND

    serialized_images = [_serialize_record(image) for image in images]
    if job is None:
        completed = len(serialized_images)
        return (
            jsonify(
                {
                    "run_id": run_id,
                    "created_at": serialized_images[0]["created_at"] if serialized_images else "",
                    "updated_at": serialized_images[-1]["created_at"] if serialized_images else "",
                    "total": completed,
                    "completed": completed,
                    "failed": 0,
                    "done": True,
                    "revised_prompt": "",
                    "errors": [],
                    "images": serialized_images,
                }
            ),
            HTTPStatus.OK,
        )

    revised_prompt = job.get("revised_prompt") or ""
    if not revised_prompt:
        for image in serialized_images:
            value = image.get("revised_prompt")
            if isinstance(value, str) and value.strip():
                revised_prompt = value.strip()
                break

    return (
        jsonify(
            {
                "run_id": run_id,
                "created_at": job["created_at"],
                "updated_at": job["updated_at"],
                "total": job["total"],
                "completed": job["completed"],
                "failed": job["failed"],
                "done": job["done"],
                "revised_prompt": revised_prompt,
                "errors": list(job["errors"]),
                "images": serialized_images,
            }
        ),
        HTTPStatus.OK,
    )




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


def _start_async_generation(payload: dict[str, Any]) -> tuple[Any, int]:
    try:
        provider_name, generation_request = _parse_payload(payload)
        if generation_request.reference_images and not _provider_supports_image_edit(provider_name):
            raise ValueError(f"Provider '{provider_name}' does not support image edit inputs")
        models = _resolve_models(payload, generation_request)
        request_payload = _sanitize_request_payload(payload, generation_request)
        run_id = str(uuid4())
        now = _now_iso()
        with generation_jobs_lock:
            generation_jobs[run_id] = {
                "run_id": run_id,
                "created_at": now,
                "updated_at": now,
                "total": len(models),
                "completed": 0,
                "failed": 0,
                "done": False,
                "revised_prompt": "",
                "errors": [],
            }
        threading.Thread(
            target=_run_generation_job,
            args=(run_id, request_payload, provider_name, generation_request, models),
            daemon=True,
        ).start()
        return (
            jsonify(
                {
                    "run_id": run_id,
                    "total": len(models),
                    "completed": 0,
                    "failed": 0,
                    "done": False,
                    "status_url": url_for("get_run_status", run_id=run_id),
                }
            ),
            HTTPStatus.ACCEPTED,
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
    return _start_async_generation(payload)


@app.post("/api/images/krea")
def generate_krea_image() -> tuple[Any, int]:
    payload = request.get_json(silent=True) or {}
    payload["provider"] = "krea"
    return _start_async_generation(payload)


@app.post("/api/images/gemini")
def generate_gemini_image() -> tuple[Any, int]:
    payload = request.get_json(silent=True) or {}
    payload["provider"] = "gemini"
    return _start_async_generation(payload)


def _run_generation_job(
    run_id: str,
    payload: dict[str, Any],
    provider_name: str,
    generation_request: ImageGenerationRequest,
    models: list[str],
) -> None:
    futures = []
    try:
        for model_name in models:
            futures.append(
                generation_executor.submit(
                    _generate_single_image,
                    run_id,
                    payload,
                    provider_name,
                    generation_request,
                    model_name,
                )
            )

        for future in as_completed(futures):
            try:
                result_payload = future.result()
                revised_prompt = result_payload.get("revised_prompt")
                with generation_jobs_lock:
                    job = generation_jobs.get(run_id)
                    if job is None:
                        continue
                    job["completed"] += 1
                    if isinstance(revised_prompt, str) and revised_prompt.strip() and not job["revised_prompt"]:
                        job["revised_prompt"] = revised_prompt.strip()
                    job["updated_at"] = _now_iso()
            except Exception as exc:
                app.logger.exception("Model generation failed for run %s", run_id)
                with generation_jobs_lock:
                    job = generation_jobs.get(run_id)
                    if job is None:
                        continue
                    job["failed"] += 1
                    job["errors"].append(str(exc))
                    job["updated_at"] = _now_iso()
    except Exception as exc:
        app.logger.exception("Run generation failed for run %s", run_id)
        with generation_jobs_lock:
            job = generation_jobs.get(run_id)
            if job is not None:
                job["failed"] = max(job["failed"], job["total"] - job["completed"])
                job["errors"].append(str(exc))
                job["updated_at"] = _now_iso()
    finally:
        with generation_jobs_lock:
            job = generation_jobs.get(run_id)
            if job is not None:
                job["done"] = True
                job["updated_at"] = _now_iso()


def _generate_single_image(
    run_id: str,
    payload: dict[str, Any],
    provider_name: str,
    generation_request: ImageGenerationRequest,
    model_name: str,
) -> dict[str, Any]:
    provider = provider_registry.get(provider_name)
    request_for_model = ImageGenerationRequest(
        prompt=generation_request.prompt,
        model=model_name or None,
        size=generation_request.size,
        quality=generation_request.quality,
        steps=generation_request.steps,
        reference_images=generation_request.reference_images,
    )
    result = provider.generate(request_for_model)
    image_store.save_generation(payload, result, run_id=run_id)
    return {"revised_prompt": result.revised_prompt}


def _resolve_models(payload: dict[str, Any], generation_request: ImageGenerationRequest) -> list[str]:
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
    return models


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _provider_supports_image_edit(provider_name: str) -> bool:
    provider_cls = provider_registry.names().get(provider_name)
    if provider_cls is None:
        return False
    options = getattr(provider_cls, "OPTIONS", None)
    if not isinstance(options, dict):
        return False
    return bool(options.get("supports_image_edit"))


def _parse_reference_images(raw_value: Any) -> tuple[InputImage, ...]:
    if raw_value is None:
        return ()
    if not isinstance(raw_value, list):
        raise ValueError("Field 'edit_images' must be an array")
    if len(raw_value) > MAX_EDIT_IMAGES:
        raise ValueError(f"Field 'edit_images' supports up to {MAX_EDIT_IMAGES} images")

    parsed_images: list[InputImage] = []
    for index, value in enumerate(raw_value, start=1):
        parsed_images.append(_parse_reference_image(value, index))
    return tuple(parsed_images)


def _parse_reference_image(raw_value: Any, index: int) -> InputImage:
    fallback_filename = f"reference-{index}.png"
    if isinstance(raw_value, dict):
        filename = _normalize_filename(raw_value.get("name"), fallback_filename)
        mime_type = _normalize_mime_type(raw_value.get("mime_type")) or "image/png"
        data_url = raw_value.get("data_url")
        base64_value = raw_value.get("base64")
        if isinstance(data_url, str) and data_url.strip():
            mime_from_data_url, encoded_data = _split_data_url(data_url.strip(), index)
            if mime_from_data_url:
                mime_type = mime_from_data_url
            return InputImage(
                data=_decode_base64_image(encoded_data, index),
                filename=filename,
                mime_type=mime_type,
            )
        if isinstance(base64_value, str) and base64_value.strip():
            return InputImage(
                data=_decode_base64_image(base64_value, index),
                filename=filename,
                mime_type=mime_type,
            )
        raise ValueError(f"Field 'edit_images[{index - 1}]' must include 'data_url' or 'base64'")

    if isinstance(raw_value, str):
        trimmed = raw_value.strip()
        if not trimmed:
            raise ValueError(f"Field 'edit_images[{index - 1}]' cannot be empty")
        if trimmed.lower().startswith("data:"):
            mime_type, encoded_data = _split_data_url(trimmed, index)
            return InputImage(
                data=_decode_base64_image(encoded_data, index),
                filename=fallback_filename,
                mime_type=mime_type or "image/png",
            )
        return InputImage(
            data=_decode_base64_image(trimmed, index),
            filename=fallback_filename,
            mime_type="image/png",
        )

    raise ValueError(f"Field 'edit_images[{index - 1}]' must be a string or object")


def _split_data_url(data_url: str, index: int) -> tuple[str | None, str]:
    header, separator, encoded_data = data_url.partition(",")
    if separator != ",":
        raise ValueError(f"Field 'edit_images[{index - 1}]' contains an invalid data URL")
    if ";base64" not in header.lower():
        raise ValueError(f"Field 'edit_images[{index - 1}]' must use base64 data URLs")
    mime_type = _normalize_mime_type(header[5:].split(";", 1)[0])
    return mime_type, encoded_data


def _decode_base64_image(value: str, index: int) -> bytes:
    normalized = "".join(value.strip().split())
    if not normalized:
        raise ValueError(f"Field 'edit_images[{index - 1}]' cannot be empty")
    try:
        decoded = base64.b64decode(normalized, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError(f"Field 'edit_images[{index - 1}]' contains invalid base64 image data") from exc
    if not decoded:
        raise ValueError(f"Field 'edit_images[{index - 1}]' cannot be empty")
    if len(decoded) > MAX_EDIT_IMAGE_BYTES:
        max_size_mb = MAX_EDIT_IMAGE_BYTES // (1024 * 1024)
        raise ValueError(f"Field 'edit_images[{index - 1}]' exceeds the {max_size_mb}MB size limit")
    return decoded


def _normalize_filename(value: Any, fallback: str) -> str:
    if not isinstance(value, str):
        return fallback
    trimmed = value.strip()
    if not trimmed:
        return fallback
    sanitized = trimmed.replace("\\", "_").replace("/", "_")
    return sanitized or fallback


def _normalize_mime_type(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    trimmed = value.strip().lower()
    if not trimmed:
        return None
    if "/" not in trimmed:
        return None
    return trimmed


def _sanitize_request_payload(
    payload: dict[str, Any],
    generation_request: ImageGenerationRequest,
) -> dict[str, Any]:
    sanitized = {key: value for key, value in payload.items() if key != "edit_images"}
    if generation_request.reference_images:
        sanitized["edit_images"] = [
            {
                "name": image.filename,
                "mime_type": image.mime_type,
                "bytes": len(image.data),
            }
            for image in generation_request.reference_images
        ]
    return sanitized


def _serialize_record(record: dict[str, Any]) -> dict[str, Any]:
    serialized = dict(record)
    image_id = serialized["id"]
    serialized["image_url"] = url_for("get_image_file", image_id=image_id)
    return serialized


if __name__ == "__main__":
    app.run(debug=True)
