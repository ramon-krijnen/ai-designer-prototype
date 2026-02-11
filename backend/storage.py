from __future__ import annotations

import base64
import hashlib
import json
import sqlite3
from dataclasses import asdict
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
            "request_json": json.dumps(request_payload, ensure_ascii=True),
            "response_json": json.dumps(asdict(result), ensure_ascii=True),
        }

        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO image_generations (
                    id, run_id, created_at, provider, model, prompt, revised_prompt,
                    size, quality, image_path, mime_type, sha256, request_json, response_json
                ) VALUES (
                    :id, :run_id, :created_at, :provider, :model, :prompt, :revised_prompt,
                    :size, :quality, :image_path, :mime_type, :sha256, :request_json, :response_json
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
                       image_path, mime_type, sha256, request_json, response_json
                FROM image_generations
                WHERE id = ?
                """,
                (image_id,),
            ).fetchone()

        if row is None:
            return None

        record = dict(row)
        record["request_json"] = json.loads(record["request_json"])
        record["response_json"] = json.loads(record["response_json"])
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

            runs: list[dict[str, Any]] = []
            for row in run_rows:
                run_id = row["run_id"]
                image_rows = conn.execute(
                    """
                    SELECT id, run_id, created_at, provider, model, prompt, revised_prompt, size, quality,
                           image_path, mime_type, sha256
                    FROM image_generations
                    WHERE run_id = ?
                    ORDER BY created_at ASC
                    """,
                    (run_id,),
                ).fetchall()

                runs.append(
                    {
                        "run_id": run_id,
                        "created_at": row["created_at"],
                        "image_count": row["image_count"],
                        "images": [dict(image_row) for image_row in image_rows],
                    }
                )

        return runs
