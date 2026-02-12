from __future__ import annotations

import os
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime
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
generation_executor = ThreadPoolExecutor(max_workers=max(1, int(os.getenv("GENERATION_WORKERS", "4"))))
generation_jobs: dict[str, dict[str, Any]] = {}
generation_jobs_lock = threading.Lock()

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
        models = _resolve_models(payload, generation_request)
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
            args=(run_id, payload, provider_name, generation_request, models),
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


def _serialize_record(record: dict[str, Any]) -> dict[str, Any]:
    serialized = dict(record)
    image_id = serialized["id"]
    serialized["image_url"] = url_for("get_image_file", image_id=image_id)
    return serialized


if __name__ == "__main__":
    app.run(debug=True)
