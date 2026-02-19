from __future__ import annotations

import base64
import hashlib
import json
import mimetypes
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from providers.base import ImageGenerationResult, InputImage


class ImageStore:
    def __init__(self, db_path: str = "data/images.db", image_dir: str = "data/images") -> None:
        self._db_path = Path(db_path)
        self._image_dir = Path(image_dir)
        self._reference_dir = self._image_dir / "references"
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._image_dir.mkdir(parents=True, exist_ok=True)
        self._reference_dir.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS image_generations (
                    id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    model TEXT NOT NULL,
                    prompt TEXT NOT NULL,
                    revised_prompt TEXT,
                    size TEXT,
                    quality TEXT,
                    image_path TEXT NOT NULL,
                    mime_type TEXT NOT NULL,
                    sha256 TEXT NOT NULL,
                    image_base64 TEXT NOT NULL,
                    request_json TEXT NOT NULL,
                    response_json TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS run_records (
                    run_id TEXT PRIMARY KEY,
                    created_at TEXT NOT NULL,
                    request_json TEXT NOT NULL,
                    preset_id TEXT,
                    preset_version INTEGER
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS presets (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    description TEXT NOT NULL,
                    tags_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    created_by TEXT NOT NULL,
                    latest_version INTEGER NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS preset_versions (
                    id TEXT PRIMARY KEY,
                    preset_id TEXT NOT NULL,
                    version INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    model_config_json TEXT NOT NULL,
                    prompting_config_json TEXT NOT NULL,
                    input_schema_json TEXT NOT NULL,
                    generation_params_json TEXT NOT NULL,
                    reference_rules_json TEXT NOT NULL,
                    output_rules_json TEXT NOT NULL,
                    UNIQUE(preset_id, version)
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS run_reference_images (
                    id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    name TEXT NOT NULL,
                    mime_type TEXT NOT NULL,
                    image_path TEXT NOT NULL,
                    sha256 TEXT NOT NULL,
                    byte_size INTEGER NOT NULL
                )
                """
            )
            columns = {row["name"] for row in conn.execute("PRAGMA table_info(image_generations)").fetchall()}
            if "run_id" not in columns:
                conn.execute("ALTER TABLE image_generations ADD COLUMN run_id TEXT")
                conn.execute("UPDATE image_generations SET run_id = id WHERE run_id IS NULL OR run_id = ''")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_image_generations_run_id ON image_generations(run_id)")
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_image_generations_created_at ON image_generations(created_at DESC)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_image_generations_provider ON image_generations(provider)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_image_generations_run_id ON image_generations(run_id)"
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_run_records_created_at ON run_records(created_at DESC)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_run_reference_images_run_id ON run_reference_images(run_id)")
            run_columns = {row["name"] for row in conn.execute("PRAGMA table_info(run_records)").fetchall()}
            if "preset_id" not in run_columns:
                conn.execute("ALTER TABLE run_records ADD COLUMN preset_id TEXT")
            if "preset_version" not in run_columns:
                conn.execute("ALTER TABLE run_records ADD COLUMN preset_version INTEGER")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_run_records_preset_id ON run_records(preset_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_presets_updated_at ON presets(updated_at DESC)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_preset_versions_preset_id ON preset_versions(preset_id)")
            if "image_base64" not in columns:
                conn.execute("ALTER TABLE image_generations ADD COLUMN image_base64 TEXT")
                rows = conn.execute(
                    """
                    SELECT id, image_path, response_json
                    FROM image_generations
                    WHERE image_base64 IS NULL OR image_base64 = ''
                    """
                ).fetchall()
                backfill_rows = []
                for row in rows:
                    image_base64 = self._extract_image_base64_from_response_json(row["response_json"])
                    if image_base64 is None:
                        image_base64 = self._read_image_file_base64(row["image_path"])
                    if image_base64 is not None:
                        backfill_rows.append((image_base64, row["id"]))
                if backfill_rows:
                    conn.executemany(
                        "UPDATE image_generations SET image_base64 = ? WHERE id = ?",
                        backfill_rows,
                    )
            conn.execute(
                """
                INSERT OR IGNORE INTO run_records (run_id, created_at, request_json, preset_id, preset_version)
                SELECT run_id, MIN(created_at), COALESCE(MAX(request_json), '{}'), NULL, NULL
                FROM image_generations
                WHERE run_id IS NOT NULL AND run_id != ''
                GROUP BY run_id
                """
            )

    def create_run(
        self,
        run_id: str,
        request_payload: dict[str, Any],
        reference_images: tuple[InputImage, ...] = (),
        preset_id: str | None = None,
        preset_version: int | None = None,
    ) -> dict[str, Any]:
        created_at = datetime.now(UTC).isoformat()
        run_row = {
            "run_id": run_id,
            "created_at": created_at,
            "request_json": json.dumps(request_payload, ensure_ascii=True),
            "preset_id": preset_id,
            "preset_version": preset_version,
        }

        reference_rows = []
        for reference_image in reference_images:
            reference_id = str(uuid4())
            extension = self._guess_extension(reference_image.mime_type)
            image_path = self._reference_dir / f"{reference_id}{extension}"
            image_path.write_bytes(reference_image.data)
            reference_rows.append(
                {
                    "id": reference_id,
                    "run_id": run_id,
                    "created_at": created_at,
                    "name": reference_image.filename,
                    "mime_type": reference_image.mime_type,
                    "image_path": str(image_path),
                    "sha256": hashlib.sha256(reference_image.data).hexdigest(),
                    "byte_size": len(reference_image.data),
                }
            )

        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO run_records (run_id, created_at, request_json, preset_id, preset_version)
                VALUES (:run_id, :created_at, :request_json, :preset_id, :preset_version)
                """,
                run_row,
            )
            if reference_rows:
                conn.executemany(
                    """
                    INSERT INTO run_reference_images (
                        id, run_id, created_at, name, mime_type, image_path, sha256, byte_size
                    ) VALUES (
                        :id, :run_id, :created_at, :name, :mime_type, :image_path, :sha256, :byte_size
                    )
                    """,
                    reference_rows,
                )

        run_record = self.get_run(run_id)
        if run_record is None:
            raise RuntimeError(f"Failed to create run '{run_id}'")
        return run_record

    def save_generation(
        self,
        request_payload: dict[str, Any],
        result: ImageGenerationResult,
        run_id: str | None = None,
    ) -> dict[str, Any]:
        image_id = str(uuid4())
        effective_run_id = run_id or image_id
        image_bytes = base64.b64decode(result.image_base64)
        image_hash = hashlib.sha256(image_bytes).hexdigest()
        image_filename = f"{image_id}.png"
        image_path = self._image_dir / image_filename
        image_path.write_bytes(image_bytes)

        created_at = datetime.now(UTC).isoformat()
        row = {
            "id": image_id,
            "run_id": effective_run_id,
            "created_at": created_at,
            "provider": result.provider,
            "model": result.model,
            "prompt": result.prompt,
            "revised_prompt": result.revised_prompt,
            "size": result.size,
            "quality": result.quality,
            "image_path": str(image_path),
            "mime_type": "image/png",
            "sha256": image_hash,
            "image_base64": result.image_base64,
            "request_json": json.dumps(request_payload, ensure_ascii=True),
            "response_json": json.dumps(self._extract_response_fields(result), ensure_ascii=True),
        }

        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO image_generations (
                    id, run_id, created_at, provider, model, prompt, revised_prompt,
                    size, quality, image_path, mime_type, sha256, image_base64, request_json, response_json
                ) VALUES (
                    :id, :run_id, :created_at, :provider, :model, :prompt, :revised_prompt,
                    :size, :quality, :image_path, :mime_type, :sha256, :image_base64, :request_json, :response_json
                )
                """,
                row,
            )

        return self.get_generation(image_id)

    def list_generations(self, limit: int = 50, offset: int = 0) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT id, run_id, created_at, provider, model, prompt, revised_prompt, size, quality,
                       image_path, mime_type, sha256
                FROM image_generations
                ORDER BY created_at DESC
                LIMIT ? OFFSET ?
                """,
                (limit, offset),
            ).fetchall()
        return [dict(row) for row in rows]

    def get_generation(self, image_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT id, run_id, created_at, provider, model, prompt, revised_prompt, size, quality,
                       image_path, mime_type, sha256, image_base64, request_json, response_json
                FROM image_generations
                WHERE id = ?
                """,
                (image_id,),
            ).fetchone()

        if row is None:
            return None

        record = dict(row)
        record["request_json"] = self._load_json(record.get("request_json"), default={})
        record["response_json"] = self._load_json(record.get("response_json"), default={})
        if not record["response_json"]:
            record["response_json"] = self._extract_response_fields_from_record(record)
        return record

    def image_file_path(self, image_id: str) -> Path | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT image_path FROM image_generations WHERE id = ?",
                (image_id,),
            ).fetchone()
        if row is None:
            return None
        path = Path(row["image_path"])
        if not path.exists():
            return None
        return path

    def reference_image_file_path(self, reference_id: str) -> Path | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT image_path FROM run_reference_images WHERE id = ?",
                (reference_id,),
            ).fetchone()
        if row is None:
            return None
        path = Path(row["image_path"])
        if not path.exists():
            return None
        return path

    def delete_run(self, run_id: str) -> None:
        with self._connect() as conn:
            image_rows = conn.execute(
                "SELECT image_path FROM image_generations WHERE run_id = ?",
                (run_id,),
            ).fetchall()
            reference_rows = conn.execute(
                "SELECT image_path FROM run_reference_images WHERE run_id = ?",
                (run_id,),
            ).fetchall()
            conn.execute("DELETE FROM image_generations WHERE run_id = ?", (run_id,))
            conn.execute("DELETE FROM run_reference_images WHERE run_id = ?", (run_id,))
            conn.execute("DELETE FROM run_records WHERE run_id = ?", (run_id,))

        for row in [*image_rows, *reference_rows]:
            image_path = Path(row["image_path"])
            try:
                if image_path.exists():
                    image_path.unlink()
            except OSError:
                # Best effort cleanup; DB rows were already removed.
                continue

    def list_runs(self, limit: int = 25, offset: int = 0) -> list[dict[str, Any]]:
        with self._connect() as conn:
            run_rows = conn.execute(
                """
                SELECT run_id, created_at, request_json, preset_id, preset_version
                FROM run_records
                ORDER BY created_at DESC
                LIMIT ? OFFSET ?
                """,
                (limit, offset),
            ).fetchall()

            if not run_rows:
                return []

            run_ids = [row["run_id"] for row in run_rows]
            placeholders = ",".join("?" for _ in run_ids)
            image_rows = conn.execute(
                f"""
                SELECT id, run_id, created_at, provider, model, prompt, revised_prompt, size, quality,
                       image_path, mime_type, sha256
                FROM image_generations
                WHERE run_id IN ({placeholders})
                ORDER BY created_at ASC
                """,
                run_ids,
            ).fetchall()
            reference_rows = conn.execute(
                f"""
                SELECT id, run_id, created_at, name, mime_type, image_path, sha256, byte_size
                FROM run_reference_images
                WHERE run_id IN ({placeholders})
                ORDER BY created_at ASC
                """,
                run_ids,
            ).fetchall()

        images_by_run: dict[str, list[dict[str, Any]]] = {run_id: [] for run_id in run_ids}
        for image_row in image_rows:
            image = dict(image_row)
            images_by_run[image["run_id"]].append(image)
        references_by_run: dict[str, list[dict[str, Any]]] = {run_id: [] for run_id in run_ids}
        for reference_row in reference_rows:
            reference = dict(reference_row)
            references_by_run[reference["run_id"]].append(reference)

        runs: list[dict[str, Any]] = []
        for row in run_rows:
            run_id = row["run_id"]
            run_images = images_by_run.get(run_id, [])
            runs.append(
                {
                    "run_id": run_id,
                    "created_at": row["created_at"],
                    "image_count": len(run_images),
                    "images": run_images,
                    "reference_images": references_by_run.get(run_id, []),
                    "request_json": self._load_json(row["request_json"], default={}),
                    "preset_id": row["preset_id"],
                    "preset_version": row["preset_version"],
                }
            )
        return runs

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT run_id, created_at, request_json, preset_id, preset_version
                FROM run_records
                WHERE run_id = ?
                """,
                (run_id,),
            ).fetchone()
        if row is None:
            return None
        run = dict(row)
        run["request_json"] = self._load_json(run.get("request_json"), default={})
        return run

    def list_run_images(self, run_id: str) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT id, run_id, created_at, provider, model, prompt, revised_prompt, size, quality,
                       image_path, mime_type, sha256
                FROM image_generations
                WHERE run_id = ?
                ORDER BY created_at ASC
                """,
                (run_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def list_run_reference_images(self, run_id: str) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT id, run_id, created_at, name, mime_type, image_path, sha256, byte_size
                FROM run_reference_images
                WHERE run_id = ?
                ORDER BY created_at ASC
                """,
                (run_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def create_preset(
        self,
        *,
        name: str,
        description: str,
        tags: list[str],
        created_by: str,
        model_config: dict[str, Any],
        prompting_config: dict[str, Any],
        input_schema: dict[str, Any],
        generation_params: dict[str, Any],
        reference_rules: dict[str, Any],
        output_rules: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        now = datetime.now(UTC).isoformat()
        preset_id = str(uuid4())
        version_id = str(uuid4())
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO presets (id, name, description, tags_json, created_at, updated_at, created_by, latest_version)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    preset_id,
                    name,
                    description,
                    json.dumps(tags, ensure_ascii=True),
                    now,
                    now,
                    created_by,
                    1,
                ),
            )
            conn.execute(
                """
                INSERT INTO preset_versions (
                    id, preset_id, version, created_at,
                    model_config_json, prompting_config_json, input_schema_json,
                    generation_params_json, reference_rules_json, output_rules_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    version_id,
                    preset_id,
                    1,
                    now,
                    json.dumps(model_config, ensure_ascii=True),
                    json.dumps(prompting_config, ensure_ascii=True),
                    json.dumps(input_schema, ensure_ascii=True),
                    json.dumps(generation_params, ensure_ascii=True),
                    json.dumps(reference_rules, ensure_ascii=True),
                    json.dumps(output_rules or {}, ensure_ascii=True),
                ),
            )
        preset = self.get_preset(preset_id)
        if preset is None:
            raise RuntimeError(f"Failed to create preset '{preset_id}'")
        return preset

    def list_presets(self) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT id, name, description, tags_json, created_at, updated_at, created_by, latest_version
                FROM presets
                ORDER BY updated_at DESC
                """
            ).fetchall()
        return [self._normalize_preset_row(dict(row)) for row in rows]

    def get_preset(self, preset_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT id, name, description, tags_json, created_at, updated_at, created_by, latest_version
                FROM presets
                WHERE id = ?
                """,
                (preset_id,),
            ).fetchone()
        if row is None:
            return None
        return self._normalize_preset_row(dict(row))

    def list_preset_versions(self, preset_id: str) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT id, preset_id, version, created_at,
                       model_config_json, prompting_config_json, input_schema_json,
                       generation_params_json, reference_rules_json, output_rules_json
                FROM preset_versions
                WHERE preset_id = ?
                ORDER BY version DESC
                """,
                (preset_id,),
            ).fetchall()
        return [self._normalize_preset_version_row(dict(row)) for row in rows]

    def get_preset_version(self, preset_id: str, version: int | None = None) -> dict[str, Any] | None:
        with self._connect() as conn:
            if version is None:
                row = conn.execute(
                    """
                    SELECT v.id, v.preset_id, v.version, v.created_at,
                           v.model_config_json, v.prompting_config_json, v.input_schema_json,
                           v.generation_params_json, v.reference_rules_json, v.output_rules_json
                    FROM preset_versions v
                    JOIN presets p ON p.id = v.preset_id
                    WHERE v.preset_id = ? AND v.version = p.latest_version
                    """,
                    (preset_id,),
                ).fetchone()
            else:
                row = conn.execute(
                    """
                    SELECT id, preset_id, version, created_at,
                           model_config_json, prompting_config_json, input_schema_json,
                           generation_params_json, reference_rules_json, output_rules_json
                    FROM preset_versions
                    WHERE preset_id = ? AND version = ?
                    """,
                    (preset_id, version),
                ).fetchone()
        if row is None:
            return None
        return self._normalize_preset_version_row(dict(row))

    def create_preset_version(
        self,
        preset_id: str,
        *,
        model_config: dict[str, Any],
        prompting_config: dict[str, Any],
        input_schema: dict[str, Any],
        generation_params: dict[str, Any],
        reference_rules: dict[str, Any],
        output_rules: dict[str, Any] | None = None,
        name: str | None = None,
        description: str | None = None,
        tags: list[str] | None = None,
    ) -> dict[str, Any]:
        now = datetime.now(UTC).isoformat()
        version_id = str(uuid4())
        with self._connect() as conn:
            current = conn.execute(
                "SELECT latest_version, name, description, tags_json FROM presets WHERE id = ?",
                (preset_id,),
            ).fetchone()
            if current is None:
                raise ValueError(f"Preset '{preset_id}' not found")
            next_version = int(current["latest_version"]) + 1
            conn.execute(
                """
                INSERT INTO preset_versions (
                    id, preset_id, version, created_at,
                    model_config_json, prompting_config_json, input_schema_json,
                    generation_params_json, reference_rules_json, output_rules_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    version_id,
                    preset_id,
                    next_version,
                    now,
                    json.dumps(model_config, ensure_ascii=True),
                    json.dumps(prompting_config, ensure_ascii=True),
                    json.dumps(input_schema, ensure_ascii=True),
                    json.dumps(generation_params, ensure_ascii=True),
                    json.dumps(reference_rules, ensure_ascii=True),
                    json.dumps(output_rules or {}, ensure_ascii=True),
                ),
            )
            conn.execute(
                """
                UPDATE presets
                SET latest_version = ?, updated_at = ?, name = ?, description = ?, tags_json = ?
                WHERE id = ?
                """,
                (
                    next_version,
                    now,
                    name if name is not None else current["name"],
                    description if description is not None else current["description"],
                    json.dumps(tags, ensure_ascii=True) if isinstance(tags, list) else current["tags_json"],
                    preset_id,
                ),
            )
        version = self.get_preset_version(preset_id, version=next_version)
        if version is None:
            raise RuntimeError(f"Failed to create preset version for '{preset_id}'")
        return version

    def duplicate_preset(
        self,
        source_preset_id: str,
        *,
        name: str,
        created_by: str,
        description: str | None = None,
        tags: list[str] | None = None,
    ) -> dict[str, Any]:
        source_preset = self.get_preset(source_preset_id)
        source_version = self.get_preset_version(source_preset_id)
        if source_preset is None or source_version is None:
            raise ValueError("Source preset not found")
        return self.create_preset(
            name=name,
            description=description if description is not None else source_preset["description"],
            tags=tags if tags is not None else source_preset["tags"],
            created_by=created_by,
            model_config=source_version["model_config"],
            prompting_config=source_version["prompting_config"],
            input_schema=source_version["input_schema"],
            generation_params=source_version["generation_params"],
            reference_rules=source_version["reference_rules"],
            output_rules=source_version["output_rules"],
        )

    @staticmethod
    def _load_json(value: str | None, default: dict[str, Any]) -> dict[str, Any]:
        if not value:
            return default
        try:
            loaded = json.loads(value)
            if isinstance(loaded, dict):
                return loaded
        except json.JSONDecodeError:
            pass
        return default

    @staticmethod
    def _extract_response_fields(result: ImageGenerationResult) -> dict[str, Any]:
        return {
            "provider": result.provider,
            "model": result.model,
            "prompt": result.prompt,
            "revised_prompt": result.revised_prompt,
            "size": result.size,
            "quality": result.quality,
        }

    @staticmethod
    def _extract_response_fields_from_record(record: dict[str, Any]) -> dict[str, Any]:
        return {
            "provider": record.get("provider"),
            "model": record.get("model"),
            "prompt": record.get("prompt"),
            "revised_prompt": record.get("revised_prompt"),
            "size": record.get("size"),
            "quality": record.get("quality"),
        }

    @staticmethod
    def _extract_image_base64_from_response_json(response_json: str | None) -> str | None:
        if not response_json:
            return None
        try:
            payload = json.loads(response_json)
        except json.JSONDecodeError:
            return None
        if isinstance(payload, dict):
            image_base64 = payload.get("image_base64")
            if isinstance(image_base64, str):
                trimmed = image_base64.strip()
                return trimmed or None
        return None

    @staticmethod
    def _read_image_file_base64(image_path: str | None) -> str | None:
        if not image_path:
            return None
        path = Path(image_path)
        if not path.exists():
            return None
        try:
            image_bytes = path.read_bytes()
        except OSError:
            return None
        return base64.b64encode(image_bytes).decode("ascii")

    @staticmethod
    def _guess_extension(mime_type: str) -> str:
        guessed = mimetypes.guess_extension(mime_type.strip().lower() if mime_type else "")
        if not guessed:
            return ".bin"
        if guessed == ".jpe":
            return ".jpg"
        return guessed

    @staticmethod
    def _normalize_preset_row(row: dict[str, Any]) -> dict[str, Any]:
        normalized = dict(row)
        normalized["tags"] = ImageStore._load_json_array(normalized.get("tags_json"))
        normalized.pop("tags_json", None)
        return normalized

    @staticmethod
    def _normalize_preset_version_row(row: dict[str, Any]) -> dict[str, Any]:
        normalized = dict(row)
        normalized["model_config"] = ImageStore._load_json(normalized.get("model_config_json"), default={})
        normalized["prompting_config"] = ImageStore._load_json(normalized.get("prompting_config_json"), default={})
        normalized["input_schema"] = ImageStore._load_json(normalized.get("input_schema_json"), default={})
        normalized["generation_params"] = ImageStore._load_json(normalized.get("generation_params_json"), default={})
        normalized["reference_rules"] = ImageStore._load_json(normalized.get("reference_rules_json"), default={})
        normalized["output_rules"] = ImageStore._load_json(normalized.get("output_rules_json"), default={})
        normalized.pop("model_config_json", None)
        normalized.pop("prompting_config_json", None)
        normalized.pop("input_schema_json", None)
        normalized.pop("generation_params_json", None)
        normalized.pop("reference_rules_json", None)
        normalized.pop("output_rules_json", None)
        return normalized

    @staticmethod
    def _load_json_array(value: str | None) -> list[str]:
        if not value:
            return []
        try:
            loaded = json.loads(value)
        except json.JSONDecodeError:
            return []
        if not isinstance(loaded, list):
            return []
        return [str(item).strip() for item in loaded if str(item).strip()]
