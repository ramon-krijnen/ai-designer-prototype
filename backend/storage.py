from __future__ import annotations

import base64
import hashlib
import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from providers.base import ImageGenerationResult


class ImageStore:
    def __init__(self, db_path: str = "data/images.db", image_dir: str = "data/images") -> None:
        self._db_path = Path(db_path)
        self._image_dir = Path(image_dir)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._image_dir.mkdir(parents=True, exist_ok=True)
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

    def delete_run(self, run_id: str) -> None:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT image_path FROM image_generations WHERE run_id = ?",
                (run_id,),
            ).fetchall()
            conn.execute("DELETE FROM image_generations WHERE run_id = ?", (run_id,))

        for row in rows:
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
                SELECT run_id, MAX(created_at) AS created_at, COUNT(*) AS image_count
                FROM image_generations
                GROUP BY run_id
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

        images_by_run: dict[str, list[dict[str, Any]]] = {run_id: [] for run_id in run_ids}
        for image_row in image_rows:
            image = dict(image_row)
            images_by_run[image["run_id"]].append(image)

        runs: list[dict[str, Any]] = []
        for row in run_rows:
            run_id = row["run_id"]
            runs.append(
                {
                    "run_id": run_id,
                    "created_at": row["created_at"],
                    "image_count": row["image_count"],
                    "images": images_by_run.get(run_id, []),
                }
            )
        return runs

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
