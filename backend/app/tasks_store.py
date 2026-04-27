from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Any

from .models import DesignRecord, GenerateRequest, NanoBananaTaskStatus, TaskRecord


class TasksStore:
    def __init__(self, db_path: str):
        self._db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS tasks (
                  task_id TEXT PRIMARY KEY,
                  status INTEGER NOT NULL,
                  created_at INTEGER NOT NULL,
                  updated_at INTEGER NOT NULL,
                  result_image_url TEXT NULL,
                  error_message TEXT NULL,
                  raw_json TEXT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS design_records (
                  task_id TEXT PRIMARY KEY,
                  status INTEGER NOT NULL,
                  prompt TEXT NOT NULL,
                  negative_prompt TEXT NULL,
                  room_type TEXT NULL,
                  design_style TEXT NULL,
                  color_preference TEXT NULL,
                  material_preference TEXT NULL,
                  budget_level TEXT NULL,
                  cultural_element TEXT NULL,
                  keep_structure INTEGER NOT NULL,
                  draft_image_url TEXT NULL,
                  reference_image_url TEXT NULL,
                  mask_url TEXT NULL,
                  result_image_url TEXT NULL,
                  error_message TEXT NULL,
                  created_at INTEGER NOT NULL,
                  updated_at INTEGER NOT NULL
                )
                """
            )
            conn.commit()
        self._backfill_design_records()

    def _backfill_design_records(self) -> None:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM tasks
                WHERE task_id NOT IN (SELECT task_id FROM design_records)
                  AND raw_json IS NOT NULL
                """
            ).fetchall()
            for row in rows:
                try:
                    raw = json.loads(row["raw_json"])
                except json.JSONDecodeError:
                    continue
                request = raw.get("request") if isinstance(raw, dict) else None
                if not isinstance(request, dict) or not request.get("prompt"):
                    continue
                image_urls = request.get("image_urls") if isinstance(request.get("image_urls"), list) else []
                conn.execute(
                    """
                    INSERT OR IGNORE INTO design_records (
                      task_id, status, prompt, negative_prompt, room_type, design_style,
                      color_preference, material_preference, budget_level, cultural_element,
                      keep_structure, draft_image_url, reference_image_url, mask_url,
                      result_image_url, error_message, created_at, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        row["task_id"],
                        row["status"],
                        request.get("prompt"),
                        request.get("negative_prompt"),
                        request.get("room_type"),
                        request.get("design_style"),
                        request.get("color_preference"),
                        request.get("material_preference"),
                        request.get("budget_level"),
                        request.get("cultural_element"),
                        1 if request.get("keep_structure", True) else 0,
                        image_urls[0] if len(image_urls) >= 1 else None,
                        image_urls[1] if len(image_urls) >= 2 else None,
                        request.get("mask_url"),
                        row["result_image_url"],
                        row["error_message"],
                        row["created_at"],
                        row["updated_at"],
                    ),
                )
            conn.commit()

    def upsert(self, task_id: str, status: NanoBananaTaskStatus, *, raw: dict[str, Any] | None = None) -> None:
        now = int(time.time())
        raw_json = json.dumps(raw, ensure_ascii=False) if raw is not None else None
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO tasks (task_id, status, created_at, updated_at, raw_json)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(task_id) DO UPDATE SET
                  status=excluded.status,
                  updated_at=excluded.updated_at,
                  raw_json=COALESCE(excluded.raw_json, tasks.raw_json)
                """,
                (task_id, int(status), now, now, raw_json),
            )
            conn.commit()

    def update_result(
        self,
        task_id: str,
        *,
        status: NanoBananaTaskStatus,
        result_image_url: str | None,
        error_message: str | None,
        raw: dict[str, Any] | None = None,
    ) -> None:
        now = int(time.time())
        raw_json = json.dumps(raw, ensure_ascii=False) if raw is not None else None
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE tasks
                SET status=?, updated_at=?, result_image_url=?, error_message=?,
                    raw_json=COALESCE(?, raw_json)
                WHERE task_id=?
                """,
                (int(status), now, result_image_url, error_message, raw_json, task_id),
            )
            conn.commit()

    def get(self, task_id: str) -> TaskRecord | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM tasks WHERE task_id=?", (task_id,)).fetchone()
        if not row:
            return None
        raw = json.loads(row["raw_json"]) if row["raw_json"] else None
        return TaskRecord(
            task_id=row["task_id"],
            status=NanoBananaTaskStatus(int(row["status"])),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            result_image_url=row["result_image_url"],
            error_message=row["error_message"],
            raw=raw,
        )

    def list_recent(self, limit: int = 50) -> list[TaskRecord]:
        limit = max(1, min(limit, 200))
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM tasks ORDER BY updated_at DESC LIMIT ?",
                (limit,),
            ).fetchall()

        records: list[TaskRecord] = []
        for row in rows:
            raw = json.loads(row["raw_json"]) if row["raw_json"] else None
            records.append(
                TaskRecord(
                    task_id=row["task_id"],
                    status=NanoBananaTaskStatus(int(row["status"])),
                    created_at=row["created_at"],
                    updated_at=row["updated_at"],
                    result_image_url=row["result_image_url"],
                    error_message=row["error_message"],
                    raw=raw,
                )
            )
        return records

    def save_design_request(
        self,
        task_id: str,
        req: GenerateRequest,
        *,
        status: NanoBananaTaskStatus,
        result_image_url: str | None = None,
        error_message: str | None = None,
    ) -> None:
        now = int(time.time())
        draft_image_url = req.image_urls[0] if len(req.image_urls) >= 1 else None
        reference_image_url = req.image_urls[1] if len(req.image_urls) >= 2 else None
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO design_records (
                  task_id, status, prompt, negative_prompt, room_type, design_style,
                  color_preference, material_preference, budget_level, cultural_element,
                  keep_structure, draft_image_url, reference_image_url, mask_url,
                  result_image_url, error_message, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(task_id) DO UPDATE SET
                  status=excluded.status,
                  prompt=excluded.prompt,
                  negative_prompt=excluded.negative_prompt,
                  room_type=excluded.room_type,
                  design_style=excluded.design_style,
                  color_preference=excluded.color_preference,
                  material_preference=excluded.material_preference,
                  budget_level=excluded.budget_level,
                  cultural_element=excluded.cultural_element,
                  keep_structure=excluded.keep_structure,
                  draft_image_url=excluded.draft_image_url,
                  reference_image_url=excluded.reference_image_url,
                  mask_url=excluded.mask_url,
                  result_image_url=COALESCE(excluded.result_image_url, design_records.result_image_url),
                  error_message=excluded.error_message,
                  updated_at=excluded.updated_at
                """,
                (
                    task_id,
                    int(status),
                    req.prompt,
                    req.negative_prompt,
                    req.room_type,
                    req.design_style,
                    req.color_preference,
                    req.material_preference,
                    req.budget_level,
                    req.cultural_element,
                    1 if req.keep_structure else 0,
                    draft_image_url,
                    reference_image_url,
                    req.mask_url,
                    result_image_url,
                    error_message,
                    now,
                    now,
                ),
            )
            conn.commit()

    def update_design_result(
        self,
        task_id: str,
        *,
        status: NanoBananaTaskStatus,
        result_image_url: str | None,
        error_message: str | None,
    ) -> None:
        now = int(time.time())
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE design_records
                SET status=?, updated_at=?, result_image_url=COALESCE(?, result_image_url), error_message=?
                WHERE task_id=?
                """,
                (int(status), now, result_image_url, error_message, task_id),
            )
            conn.commit()

    def get_design_record(self, task_id: str) -> DesignRecord | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM design_records WHERE task_id=?", (task_id,)).fetchone()
        return self._row_to_design_record(row) if row else None

    def list_design_records(self, limit: int = 50, design_style: str | None = None) -> list[DesignRecord]:
        limit = max(1, min(limit, 200))
        sql = "SELECT * FROM design_records"
        params: list[object] = []
        if design_style:
            sql += " WHERE design_style=?"
            params.append(design_style)
        sql += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [self._row_to_design_record(row) for row in rows]

    def delete_design_record(self, task_id: str) -> bool:
        with self._connect() as conn:
            cur = conn.execute("DELETE FROM design_records WHERE task_id=?", (task_id,))
            conn.commit()
            return cur.rowcount > 0

    def _row_to_design_record(self, row: sqlite3.Row) -> DesignRecord:
        return DesignRecord(
            task_id=row["task_id"],
            status=NanoBananaTaskStatus(int(row["status"])),
            prompt=row["prompt"],
            negative_prompt=row["negative_prompt"],
            room_type=row["room_type"],
            design_style=row["design_style"],
            color_preference=row["color_preference"],
            material_preference=row["material_preference"],
            budget_level=row["budget_level"],
            cultural_element=row["cultural_element"],
            keep_structure=bool(row["keep_structure"]),
            draft_image_url=row["draft_image_url"],
            reference_image_url=row["reference_image_url"],
            mask_url=row["mask_url"],
            result_image_url=row["result_image_url"],
            error_message=row["error_message"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
