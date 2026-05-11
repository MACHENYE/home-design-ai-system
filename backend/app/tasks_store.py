from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Any

from .models import FavoriteScheme, FavoriteSchemeCreate, UserProfile, DesignRecord, GenerateRequest, NanoBananaTaskStatus, TaskRecord


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
                  user_id INTEGER NULL,
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
                  user_id INTEGER NULL,
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
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS users (
                  id INTEGER PRIMARY KEY AUTOINCREMENT,
                  username TEXT NOT NULL UNIQUE,
                  password_hash TEXT NOT NULL,
                  created_at INTEGER NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS sessions (
                  token TEXT PRIMARY KEY,
                  user_id INTEGER NOT NULL,
                  created_at INTEGER NOT NULL,
                  expires_at INTEGER NULL,
                  FOREIGN KEY(user_id) REFERENCES users(id)
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS favorite_schemes (
                  id INTEGER PRIMARY KEY AUTOINCREMENT,
                  user_id INTEGER NOT NULL,
                  task_id TEXT NULL,
                  title TEXT NOT NULL,
                  style TEXT NULL,
                  image TEXT NOT NULL,
                  created_at INTEGER NOT NULL,
                  UNIQUE(user_id, task_id),
                  FOREIGN KEY(user_id) REFERENCES users(id)
                )
                """
            )
            self._ensure_column(conn, "tasks", "user_id", "INTEGER NULL")
            self._ensure_column(conn, "design_records", "user_id", "INTEGER NULL")
            conn.commit()
        self._backfill_design_records()

    def _ensure_column(self, conn: sqlite3.Connection, table: str, column: str, definition: str) -> None:
        columns = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
        if column not in columns:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")

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
                      result_image_url, error_message, created_at, updated_at, user_id
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                        row["user_id"] if "user_id" in row.keys() else None,
                    ),
                )
            conn.commit()

    def upsert(self, task_id: str, status: NanoBananaTaskStatus, *, raw: dict[str, Any] | None = None, user_id: int | None = None) -> None:
        now = int(time.time())
        raw_json = json.dumps(raw, ensure_ascii=False) if raw is not None else None
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO tasks (task_id, user_id, status, created_at, updated_at, raw_json)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(task_id) DO UPDATE SET
                  user_id=COALESCE(excluded.user_id, tasks.user_id),
                  status=excluded.status,
                  updated_at=excluded.updated_at,
                  raw_json=COALESCE(excluded.raw_json, tasks.raw_json)
                """,
                (task_id, user_id, int(status), now, now, raw_json),
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

    def list_recent(self, limit: int = 50, user_id: int | None = None) -> list[TaskRecord]:
        limit = max(1, min(limit, 200))
        params: list[object] = []
        where = ""
        if user_id is not None:
            where = "WHERE user_id=?"
            params.append(user_id)
        params.append(limit)
        with self._connect() as conn:
            rows = conn.execute(
                f"SELECT * FROM tasks {where} ORDER BY updated_at DESC LIMIT ?",
                params,
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
        user_id: int | None = None,
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
                  result_image_url, error_message, created_at, updated_at, user_id
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(task_id) DO UPDATE SET
                  user_id=COALESCE(excluded.user_id, design_records.user_id),
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
                    user_id,
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

    def get_design_record(self, task_id: str, user_id: int | None = None) -> DesignRecord | None:
        with self._connect() as conn:
            if user_id is None:
                row = conn.execute("SELECT * FROM design_records WHERE task_id=?", (task_id,)).fetchone()
            else:
                row = conn.execute("SELECT * FROM design_records WHERE task_id=? AND user_id=?", (task_id, user_id)).fetchone()
        return self._row_to_design_record(row) if row else None

    def list_design_records(self, limit: int = 50, design_style: str | None = None, user_id: int | None = None) -> list[DesignRecord]:
        limit = max(1, min(limit, 200))
        sql = "SELECT * FROM design_records"
        params: list[object] = []
        where: list[str] = []
        if user_id is not None:
            where.append("user_id=?")
            params.append(user_id)
        if design_style:
            where.append("design_style=?")
            params.append(design_style)
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [self._row_to_design_record(row) for row in rows]

    def delete_design_record(self, task_id: str, user_id: int | None = None) -> bool:
        with self._connect() as conn:
            if user_id is None:
                cur = conn.execute("DELETE FROM design_records WHERE task_id=?", (task_id,))
            else:
                cur = conn.execute("DELETE FROM design_records WHERE task_id=? AND user_id=?", (task_id, user_id))
            conn.commit()
            return cur.rowcount > 0

    def create_user(self, username: str, password_hash: str) -> UserProfile:
        now = int(time.time())
        with self._connect() as conn:
            cur = conn.execute(
                "INSERT INTO users (username, password_hash, created_at) VALUES (?, ?, ?)",
                (username, password_hash, now),
            )
            conn.commit()
            user_id = int(cur.lastrowid)
        return UserProfile(id=user_id, username=username, created_at=now)

    def get_user_by_username(self, username: str) -> tuple[UserProfile, str] | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
        if not row:
            return None
        return UserProfile(id=row["id"], username=row["username"], created_at=row["created_at"]), row["password_hash"]

    def create_session(self, token: str, user_id: int, expires_at: int | None = None) -> None:
        now = int(time.time())
        with self._connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO sessions (token, user_id, created_at, expires_at) VALUES (?, ?, ?, ?)",
                (token, user_id, now, expires_at),
            )
            conn.commit()

    def get_user_by_token(self, token: str) -> UserProfile | None:
        now = int(time.time())
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT users.*
                FROM sessions
                JOIN users ON users.id=sessions.user_id
                WHERE sessions.token=? AND (sessions.expires_at IS NULL OR sessions.expires_at>?)
                """,
                (token, now),
            ).fetchone()
        if not row:
            return None
        return UserProfile(id=row["id"], username=row["username"], created_at=row["created_at"])

    def delete_session(self, token: str) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM sessions WHERE token=?", (token,))
            conn.commit()

    def save_favorite_scheme(self, user_id: int, scheme: FavoriteSchemeCreate) -> FavoriteScheme:
        now = int(time.time())
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO favorite_schemes (user_id, task_id, title, style, image, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(user_id, task_id) DO UPDATE SET
                  title=excluded.title,
                  style=excluded.style,
                  image=excluded.image
                """,
                (user_id, scheme.task_id, scheme.title, scheme.style, scheme.image, now),
            )
            row = conn.execute(
                """
                SELECT * FROM favorite_schemes
                WHERE user_id=? AND ((task_id IS NULL AND id=last_insert_rowid()) OR task_id=?)
                ORDER BY id DESC LIMIT 1
                """,
                (user_id, scheme.task_id),
            ).fetchone()
            conn.commit()
        return self._row_to_favorite_scheme(row)

    def list_favorite_schemes(self, user_id: int, limit: int = 50) -> list[FavoriteScheme]:
        limit = max(1, min(limit, 200))
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM favorite_schemes WHERE user_id=? ORDER BY created_at DESC LIMIT ?",
                (user_id, limit),
            ).fetchall()
        return [self._row_to_favorite_scheme(row) for row in rows]

    def delete_favorite_scheme(self, user_id: int, favorite_id: int) -> bool:
        with self._connect() as conn:
            cur = conn.execute("DELETE FROM favorite_schemes WHERE id=? AND user_id=?", (favorite_id, user_id))
            conn.commit()
            return cur.rowcount > 0

    def admin_dashboard(self, limit: int = 120) -> dict[str, Any]:
        limit = max(20, min(limit, 300))
        with self._connect() as conn:
            totals = conn.execute(
                """
                SELECT
                  (SELECT COUNT(*) FROM users) AS users,
                  (SELECT COUNT(*) FROM design_records) AS records,
                  (SELECT COUNT(*) FROM favorite_schemes) AS favorites,
                  (SELECT COUNT(*) FROM design_records WHERE status=3) AS successes,
                  (SELECT COUNT(*) FROM design_records WHERE status=4) AS failures
                """
            ).fetchone()
            users = conn.execute(
                """
                SELECT
                  users.id,
                  users.username,
                  users.created_at,
                  COUNT(design_records.task_id) AS total_records,
                  SUM(CASE WHEN design_records.status=3 THEN 1 ELSE 0 END) AS success_records,
                  SUM(CASE WHEN design_records.status=4 THEN 1 ELSE 0 END) AS failed_records,
                  MAX(design_records.updated_at) AS last_used_at
                FROM users
                LEFT JOIN design_records ON design_records.user_id=users.id
                GROUP BY users.id
                ORDER BY COALESCE(last_used_at, users.created_at) DESC
                """
            ).fetchall()
            style_rows = conn.execute(
                """
                SELECT COALESCE(design_style, '未设置') AS name, COUNT(*) AS value
                FROM design_records
                GROUP BY COALESCE(design_style, '未设置')
                ORDER BY value DESC
                LIMIT 8
                """
            ).fetchall()
            daily_rows = conn.execute(
                """
                SELECT date(created_at, 'unixepoch', 'localtime') AS day, COUNT(*) AS value
                FROM design_records
                GROUP BY day
                ORDER BY day DESC
                LIMIT 7
                """
            ).fetchall()
            records = conn.execute(
                """
                SELECT design_records.*, users.username
                FROM design_records
                LEFT JOIN users ON users.id=design_records.user_id
                ORDER BY design_records.created_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()

        return {
            "summary": dict(totals) if totals else {},
            "users": [dict(row) for row in users],
            "styleStats": [dict(row) for row in style_rows],
            "dailyStats": list(reversed([dict(row) for row in daily_rows])),
            "records": [dict(row) for row in records],
        }

    def _row_to_favorite_scheme(self, row: sqlite3.Row) -> FavoriteScheme:
        return FavoriteScheme(
            id=row["id"],
            user_id=row["user_id"],
            task_id=row["task_id"],
            title=row["title"],
            style=row["style"],
            image=row["image"],
            created_at=row["created_at"],
        )

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
