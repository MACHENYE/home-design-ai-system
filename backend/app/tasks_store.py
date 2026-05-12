from __future__ import annotations

import json
import time
from datetime import date, datetime
from decimal import Decimal
from typing import Any
from urllib.parse import urlparse, unquote

from .models import (
    DesignFeedbackRequest,
    DesignRecord,
    FavoriteScheme,
    FavoriteSchemeCreate,
    GenerateRequest,
    NanoBananaTaskStatus,
    SystemLog,
    TaskRecord,
    UserProfile,
)


class MySQLConnectionAdapter:
    def __init__(self, conn: Any):
        self._conn = conn

    def __enter__(self) -> "MySQLConnectionAdapter":
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        self._conn.close()

    def execute(self, sql: str, params: list[object] | tuple[object, ...] = ()):
        cursor = self._conn.cursor()
        cursor.execute(sql.replace("?", "%s"), params)
        return cursor

    def cursor(self):
        return self._conn.cursor()

    def commit(self) -> None:
        self._conn.commit()


class TasksStore:
    def __init__(self, database_url: str):
        self._database_url = database_url.strip()
        self._mysql = self._database_url.startswith(("mysql://", "mysql+pymysql://"))
        if not self._mysql:
            raise RuntimeError("DATABASE_URL must be configured with a MySQL connection string.")
        self._init()

    def _connect(self):
        if self._mysql:
            try:
                import pymysql
            except ImportError as exc:
                raise RuntimeError("pymysql is required for MySQL. Run: pip install -r requirements.txt") from exc
            parsed = urlparse(self._database_url.replace("mysql+pymysql://", "mysql://", 1))
            conn = pymysql.connect(
                host=parsed.hostname or "127.0.0.1",
                port=parsed.port or 3306,
                user=unquote(parsed.username or ""),
                password=unquote(parsed.password or ""),
                database=(parsed.path or "/").lstrip("/"),
                charset="utf8mb4",
                autocommit=False,
                cursorclass=pymysql.cursors.DictCursor,
            )
            return MySQLConnectionAdapter(conn)
        raise RuntimeError("SQLite is disabled. Configure DATABASE_URL to use MySQL.")

    def _execute(self, conn: Any, sql: str, params: list[object] | tuple[object, ...] = ()):
        if not self._mysql:
            return conn.execute(sql, params)
        cursor = conn.cursor()
        cursor.execute(sql.replace("?", "%s"), params)
        return cursor

    def _fetchone(self, conn: Any, sql: str, params: list[object] | tuple[object, ...] = ()):
        return self._execute(conn, sql, params).fetchone()

    def _fetchall(self, conn: Any, sql: str, params: list[object] | tuple[object, ...] = ()):
        return self._execute(conn, sql, params).fetchall()

    def _create_table(self, conn: Any, sql: str) -> None:
        if self._mysql:
            sql = sql.replace("INTEGER PRIMARY KEY AUTOINCREMENT", "INTEGER PRIMARY KEY AUTO_INCREMENT")
            sql = sql.replace("task_id TEXT PRIMARY KEY", "task_id VARCHAR(191) PRIMARY KEY")
            sql = sql.replace("token TEXT PRIMARY KEY", "token VARCHAR(191) PRIMARY KEY")
            sql = sql.replace("remote_task_id TEXT NULL", "remote_task_id VARCHAR(191) NULL")
            sql = sql.replace("username TEXT NOT NULL UNIQUE", "username VARCHAR(191) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL UNIQUE")
            sql = sql.replace("task_id TEXT NULL", "task_id VARCHAR(191) NULL")
            sql = sql.replace("role TEXT NOT NULL DEFAULT 'user'", "role VARCHAR(32) NOT NULL DEFAULT 'user'")
            sql = sql.replace("room_type TEXT NULL", "room_type VARCHAR(64) NULL")
            sql = sql.replace("design_style TEXT NULL", "design_style VARCHAR(64) NULL")
            sql = sql.replace("color_preference TEXT NULL", "color_preference VARCHAR(128) NULL")
            sql = sql.replace("material_preference TEXT NULL", "material_preference VARCHAR(64) NULL")
            sql = sql.replace("budget_level TEXT NULL", "budget_level VARCHAR(64) NULL")
            sql = sql.replace("cultural_element TEXT NULL", "cultural_element VARCHAR(64) NULL")
            sql = sql.replace("style TEXT NULL", "style VARCHAR(64) NULL")
        self._execute(conn, sql)

    def _last_insert_id(self, cursor: Any) -> int:
        return int(cursor.lastrowid)

    def _row_dict(self, row: Any) -> dict[str, Any]:
        return dict(row) if row else {}

    def _plain_dict(self, row: Any) -> dict[str, Any]:
        data = dict(row) if row else {}
        return {
            key: (
                float(value)
                if isinstance(value, Decimal)
                else value.isoformat()
                if isinstance(value, (date, datetime))
                else value
            )
            for key, value in data.items()
        }

    def _init(self) -> None:
        with self._connect() as conn:
            self._create_table(
                conn,
                """
                CREATE TABLE IF NOT EXISTS users (
                  id INTEGER PRIMARY KEY AUTOINCREMENT,
                  username TEXT NOT NULL UNIQUE,
                  password_hash TEXT NOT NULL,
                  role TEXT NOT NULL DEFAULT 'user',
                  created_at INTEGER NOT NULL
                )
                """
            )
            self._create_table(
                conn,
                """
                CREATE TABLE IF NOT EXISTS tasks (
                  task_id TEXT PRIMARY KEY,
                  user_id INTEGER NULL,
                  status INTEGER NOT NULL,
                  remote_task_id TEXT NULL,
                  created_at INTEGER NOT NULL,
                  updated_at INTEGER NOT NULL,
                  result_image_url TEXT NULL,
                  error_message TEXT NULL,
                  raw_json TEXT NULL,
                  FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE SET NULL
                )
                """
            )
            self._create_table(
                conn,
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
                  lighting_score INTEGER NULL,
                  style_match_score INTEGER NULL,
                  space_utilization_score INTEGER NULL,
                  satisfaction_score INTEGER NULL,
                  feedback_text TEXT NULL,
                  feedback_updated_at INTEGER NULL,
                  created_at INTEGER NOT NULL,
                  updated_at INTEGER NOT NULL,
                  FOREIGN KEY(task_id) REFERENCES tasks(task_id) ON DELETE CASCADE,
                  FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE SET NULL
                )
                """
            )
            self._create_table(
                conn,
                """
                CREATE TABLE IF NOT EXISTS sessions (
                  token TEXT PRIMARY KEY,
                  user_id INTEGER NOT NULL,
                  created_at INTEGER NOT NULL,
                  expires_at INTEGER NULL,
                  FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
                )
                """
            )
            self._create_table(
                conn,
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
                  FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
                  FOREIGN KEY(task_id) REFERENCES tasks(task_id) ON DELETE SET NULL
                )
                """
            )
            self._create_table(
                conn,
                """
                CREATE TABLE IF NOT EXISTS system_logs (
                  id INTEGER PRIMARY KEY AUTOINCREMENT,
                  user_id INTEGER NULL,
                  username TEXT NULL,
                  level TEXT NOT NULL,
                  action TEXT NOT NULL,
                  target_type TEXT NULL,
                  target_id TEXT NULL,
                  message TEXT NULL,
                  duration_ms INTEGER NULL,
                  request_path TEXT NULL,
                  ip_address TEXT NULL,
                  created_at INTEGER NOT NULL,
                  FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE SET NULL
                )
                """
            )
            self._ensure_column(conn, "tasks", "user_id", "INTEGER NULL")
            self._ensure_column(conn, "tasks", "remote_task_id", "VARCHAR(191) NULL")
            self._ensure_column(conn, "design_records", "user_id", "INTEGER NULL")
            self._ensure_column(conn, "design_records", "lighting_score", "INTEGER NULL")
            self._ensure_column(conn, "design_records", "style_match_score", "INTEGER NULL")
            self._ensure_column(conn, "design_records", "space_utilization_score", "INTEGER NULL")
            self._ensure_column(conn, "design_records", "satisfaction_score", "INTEGER NULL")
            self._ensure_column(conn, "design_records", "feedback_text", "TEXT NULL")
            self._ensure_column(conn, "design_records", "feedback_updated_at", "INTEGER NULL")
            self._ensure_column(conn, "users", "role", "TEXT NOT NULL DEFAULT 'user'")
            self._ensure_column(conn, "system_logs", "duration_ms", "INTEGER NULL")
            self._ensure_column(conn, "system_logs", "request_path", "TEXT NULL")
            self._ensure_column(conn, "system_logs", "ip_address", "TEXT NULL")
            self._normalize_mysql_schema(conn)
            if not self._mysql:
                conn.execute("DROP INDEX IF EXISTS idx_users_username_lower")
            conn.execute("UPDATE users SET role='user' WHERE username!='admin' AND role='admin'")
            conn.execute("UPDATE users SET role='admin' WHERE username='admin'")
            conn.commit()
        self._backfill_design_records()

    def _ensure_column(self, conn: Any, table: str, column: str, definition: str) -> None:
        if self._mysql:
            rows = conn.execute(
                """
                SELECT COLUMN_NAME AS name
                FROM INFORMATION_SCHEMA.COLUMNS
                WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME=? AND COLUMN_NAME=?
                """,
                (table, column),
            ).fetchall()
            columns = {row["name"] for row in rows}
        else:
            columns = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
        if column not in columns:
            if self._mysql:
                definition = definition.replace("TEXT NOT NULL DEFAULT 'user'", "VARCHAR(32) NOT NULL DEFAULT 'user'")
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")

    def _normalize_mysql_schema(self, conn: Any) -> None:
        if not self._mysql:
            return
        column_types = {
            "users": {
                "username": "VARCHAR(191) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL",
                "role": "VARCHAR(32) NOT NULL DEFAULT 'user'",
            },
            "design_records": {
                "room_type": "VARCHAR(191) NULL",
                "design_style": "VARCHAR(191) NULL",
                "color_preference": "VARCHAR(191) NULL",
                "material_preference": "VARCHAR(191) NULL",
                "budget_level": "VARCHAR(191) NULL",
                "cultural_element": "VARCHAR(191) NULL",
            },
            "favorite_schemes": {
                "style": "VARCHAR(191) NULL",
            },
            "system_logs": {
                "username": "VARCHAR(191) NULL",
                "level": "VARCHAR(32) NOT NULL",
                "action": "VARCHAR(80) NOT NULL",
                "target_type": "VARCHAR(80) NULL",
                "target_id": "VARCHAR(191) NULL",
                "request_path": "VARCHAR(191) NULL",
                "ip_address": "VARCHAR(64) NULL",
            },
        }
        for table, columns in column_types.items():
            for column, definition in columns.items():
                self._modify_column_if_exists(conn, table, column, definition)

        # Normalize old rows before foreign keys are enforced.
        conn.execute(
            """
            UPDATE tasks
            LEFT JOIN users ON users.id=tasks.user_id
            SET tasks.user_id=NULL
            WHERE tasks.user_id IS NOT NULL AND users.id IS NULL
            """
        )
        conn.execute(
            """
            INSERT IGNORE INTO tasks (
              task_id, user_id, status, created_at, updated_at,
              result_image_url, error_message, raw_json
            )
            SELECT
              design_records.task_id,
              design_records.user_id,
              design_records.status,
              design_records.created_at,
              design_records.updated_at,
              design_records.result_image_url,
              design_records.error_message,
              NULL
            FROM design_records
            LEFT JOIN tasks ON tasks.task_id=design_records.task_id
            WHERE tasks.task_id IS NULL
            """
        )
        conn.execute(
            """
            UPDATE design_records
            LEFT JOIN users ON users.id=design_records.user_id
            SET design_records.user_id=NULL
            WHERE design_records.user_id IS NOT NULL AND users.id IS NULL
            """
        )
        conn.execute(
            """
            UPDATE favorite_schemes
            LEFT JOIN tasks ON tasks.task_id=favorite_schemes.task_id
            SET favorite_schemes.task_id=NULL
            WHERE favorite_schemes.task_id IS NOT NULL AND tasks.task_id IS NULL
            """
        )
        conn.execute(
            """
            DELETE sessions FROM sessions
            LEFT JOIN users ON users.id=sessions.user_id
            WHERE users.id IS NULL
            """
        )

        self._ensure_foreign_key(conn, "tasks", "fk_tasks_user", "user_id", "users", "id", "ON DELETE SET NULL")
        self._ensure_foreign_key(conn, "design_records", "fk_design_records_task", "task_id", "tasks", "task_id", "ON DELETE CASCADE")
        self._ensure_foreign_key(conn, "design_records", "fk_design_records_user", "user_id", "users", "id", "ON DELETE SET NULL")
        self._ensure_foreign_key(conn, "favorite_schemes", "fk_favorite_schemes_task", "task_id", "tasks", "task_id", "ON DELETE SET NULL")
        self._ensure_foreign_key(conn, "system_logs", "fk_system_logs_user", "user_id", "users", "id", "ON DELETE SET NULL")

        index_specs = {
            "users": [
                ("idx_users_role", "role"),
                ("idx_users_created_at", "created_at"),
            ],
            "tasks": [
                ("idx_tasks_user_id", "user_id"),
                ("idx_tasks_remote_task_id", "remote_task_id"),
                ("idx_tasks_status", "status"),
                ("idx_tasks_created_at", "created_at"),
                ("idx_tasks_updated_at", "updated_at"),
                ("idx_tasks_user_created", "user_id, created_at"),
            ],
            "design_records": [
                ("idx_design_records_user_id", "user_id"),
                ("idx_design_records_status", "status"),
                ("idx_design_records_created_at", "created_at"),
                ("idx_design_records_updated_at", "updated_at"),
                ("idx_design_records_room", "room_type"),
                ("idx_design_records_style", "design_style"),
                ("idx_design_records_color", "color_preference"),
                ("idx_design_records_material", "material_preference"),
                ("idx_design_records_user_created", "user_id, created_at"),
                ("idx_design_records_status_created", "status, created_at"),
                ("idx_design_records_feedback", "satisfaction_score, feedback_updated_at"),
            ],
            "favorite_schemes": [
                ("idx_favorite_schemes_task_id", "task_id"),
                ("idx_favorite_schemes_user_created", "user_id, created_at"),
            ],
            "sessions": [
                ("idx_sessions_user_id", "user_id"),
                ("idx_sessions_expires_at", "expires_at"),
            ],
            "system_logs": [
                ("idx_system_logs_created_at", "created_at"),
                ("idx_system_logs_level", "level"),
                ("idx_system_logs_action", "action"),
                ("idx_system_logs_user_created", "user_id, created_at"),
                ("idx_system_logs_target", "target_type, target_id"),
            ],
        }
        for table, specs in index_specs.items():
            for index_name, columns in specs:
                self._ensure_index(conn, table, index_name, columns)

    def _modify_column_if_exists(self, conn: Any, table: str, column: str, definition: str) -> None:
        row = conn.execute(
            """
            SELECT COLUMN_NAME AS name
            FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME=? AND COLUMN_NAME=?
            """,
            (table, column),
        ).fetchone()
        if row:
            conn.execute(f"ALTER TABLE {table} MODIFY COLUMN {column} {definition}")

    def _ensure_index(self, conn: Any, table: str, index_name: str, columns: str) -> None:
        row = conn.execute(
            """
            SELECT INDEX_NAME AS name
            FROM INFORMATION_SCHEMA.STATISTICS
            WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME=? AND INDEX_NAME=?
            LIMIT 1
            """,
            (table, index_name),
        ).fetchone()
        if not row:
            conn.execute(f"CREATE INDEX {index_name} ON {table} ({columns})")

    def _ensure_foreign_key(
        self,
        conn: Any,
        table: str,
        constraint_name: str,
        column: str,
        ref_table: str,
        ref_column: str,
        on_delete: str,
    ) -> None:
        existing = conn.execute(
            """
            SELECT CONSTRAINT_NAME AS name
            FROM INFORMATION_SCHEMA.KEY_COLUMN_USAGE
            WHERE TABLE_SCHEMA=DATABASE()
              AND TABLE_NAME=?
              AND COLUMN_NAME=?
              AND REFERENCED_TABLE_NAME IS NOT NULL
            LIMIT 1
            """,
            (table, column),
        ).fetchone()
        if existing:
            return
        conn.execute(
            f"""
            ALTER TABLE {table}
            ADD CONSTRAINT {constraint_name}
            FOREIGN KEY ({column}) REFERENCES {ref_table}({ref_column}) {on_delete}
            """
        )

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
                insert_sql = """
                    INSERT {ignore_clause} INTO design_records (
                      task_id, status, prompt, negative_prompt, room_type, design_style,
                      color_preference, material_preference, budget_level, cultural_element,
                      keep_structure, draft_image_url, reference_image_url, mask_url,
                      result_image_url, error_message, created_at, updated_at, user_id
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """.format(ignore_clause="IGNORE" if self._mysql else "OR IGNORE")
                conn.execute(
                    insert_sql,
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
            if self._mysql:
                conn.execute(
                    """
                    INSERT INTO tasks (task_id, user_id, status, created_at, updated_at, raw_json)
                    VALUES (?, ?, ?, ?, ?, ?)
                    ON DUPLICATE KEY UPDATE
                      user_id=COALESCE(VALUES(user_id), user_id),
                      status=VALUES(status),
                      updated_at=VALUES(updated_at),
                      raw_json=COALESCE(VALUES(raw_json), raw_json)
                    """,
                    (task_id, user_id, int(status), now, now, raw_json),
                )
            else:
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

    def attach_remote_task(self, task_id: str, remote_task_id: str, *, raw: dict[str, Any] | None = None) -> None:
        now = int(time.time())
        raw_json = json.dumps(raw, ensure_ascii=False) if raw is not None else None
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE tasks
                SET remote_task_id=?, status=?, updated_at=?, raw_json=COALESCE(?, raw_json)
                WHERE task_id=?
                """,
                (remote_task_id, int(NanoBananaTaskStatus.processing), now, raw_json, task_id),
            )
            conn.execute(
                """
                UPDATE design_records
                SET status=?, updated_at=?
                WHERE task_id=?
                """,
                (int(NanoBananaTaskStatus.processing), now, task_id),
            )
            conn.commit()

    def get_by_remote_task_id(self, remote_task_id: str) -> TaskRecord | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM tasks WHERE remote_task_id=? LIMIT 1", (remote_task_id,)).fetchone()
        return self._row_to_task_record(row) if row else None

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
        return self._row_to_task_record(row) if row else None

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
            records.append(self._row_to_task_record(row))
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
            params = (
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
            )
            if self._mysql:
                conn.execute(
                    """
                    INSERT INTO design_records (
                      task_id, status, prompt, negative_prompt, room_type, design_style,
                      color_preference, material_preference, budget_level, cultural_element,
                      keep_structure, draft_image_url, reference_image_url, mask_url,
                      result_image_url, error_message, created_at, updated_at, user_id
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON DUPLICATE KEY UPDATE
                      user_id=COALESCE(VALUES(user_id), user_id),
                      status=VALUES(status),
                      prompt=VALUES(prompt),
                      negative_prompt=VALUES(negative_prompt),
                      room_type=VALUES(room_type),
                      design_style=VALUES(design_style),
                      color_preference=VALUES(color_preference),
                      material_preference=VALUES(material_preference),
                      budget_level=VALUES(budget_level),
                      cultural_element=VALUES(cultural_element),
                      keep_structure=VALUES(keep_structure),
                      draft_image_url=VALUES(draft_image_url),
                      reference_image_url=VALUES(reference_image_url),
                      mask_url=VALUES(mask_url),
                      result_image_url=COALESCE(VALUES(result_image_url), result_image_url),
                      error_message=VALUES(error_message),
                      updated_at=VALUES(updated_at)
                    """,
                    params,
                )
            else:
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
                    params,
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

    def count_design_records(self, design_style: str | None = None, user_id: int | None = None) -> int:
        sql = "SELECT COUNT(*) AS total FROM design_records"
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
        with self._connect() as conn:
            row = conn.execute(sql, params).fetchone()
        return int(row["total"] if row else 0)

    def list_design_records(
        self,
        limit: int = 50,
        design_style: str | None = None,
        user_id: int | None = None,
        offset: int = 0,
    ) -> list[DesignRecord]:
        limit = max(1, min(limit, 200))
        offset = max(0, offset)
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
        sql += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [self._row_to_design_record(row) for row in rows]

    def update_design_feedback(
        self,
        task_id: str,
        feedback: DesignFeedbackRequest,
        *,
        user_id: int | None = None,
    ) -> DesignRecord | None:
        now = int(time.time())
        with self._connect() as conn:
            if user_id is None:
                cur = conn.execute(
                    """
                    UPDATE design_records
                    SET lighting_score=?,
                        style_match_score=?,
                        space_utilization_score=?,
                        satisfaction_score=?,
                        feedback_text=?,
                        feedback_updated_at=?,
                        updated_at=?
                    WHERE task_id=?
                    """,
                    (
                        feedback.lighting_score,
                        feedback.style_match_score,
                        feedback.space_utilization_score,
                        feedback.satisfaction_score,
                        feedback.feedback_text,
                        now,
                        now,
                        task_id,
                    ),
                )
                row = conn.execute("SELECT * FROM design_records WHERE task_id=?", (task_id,)).fetchone()
            else:
                cur = conn.execute(
                    """
                    UPDATE design_records
                    SET lighting_score=?,
                        style_match_score=?,
                        space_utilization_score=?,
                        satisfaction_score=?,
                        feedback_text=?,
                        feedback_updated_at=?,
                        updated_at=?
                    WHERE task_id=? AND user_id=?
                    """,
                    (
                        feedback.lighting_score,
                        feedback.style_match_score,
                        feedback.space_utilization_score,
                        feedback.satisfaction_score,
                        feedback.feedback_text,
                        now,
                        now,
                        task_id,
                        user_id,
                    ),
                )
                row = conn.execute(
                    "SELECT * FROM design_records WHERE task_id=? AND user_id=?",
                    (task_id, user_id),
                ).fetchone()
            conn.commit()
        if cur.rowcount <= 0 or not row:
            return None
        return self._row_to_design_record(row)

    def delete_design_record(self, task_id: str, user_id: int | None = None) -> bool:
        with self._connect() as conn:
            if user_id is None:
                cur = conn.execute("DELETE FROM design_records WHERE task_id=?", (task_id,))
            else:
                cur = conn.execute("DELETE FROM design_records WHERE task_id=? AND user_id=?", (task_id, user_id))
            conn.commit()
            return cur.rowcount > 0

    def admin_delete_design_record(self, task_id: str) -> bool:
        with self._connect() as conn:
            cur = conn.execute("DELETE FROM design_records WHERE task_id=?", (task_id,))
            conn.execute("DELETE FROM favorite_schemes WHERE task_id=?", (task_id,))
            conn.execute("DELETE FROM tasks WHERE task_id=?", (task_id,))
            conn.commit()
            return cur.rowcount > 0

    def create_user(self, username: str, password_hash: str) -> UserProfile:
        now = int(time.time())
        role = "admin" if username == "admin" else "user"
        with self._connect() as conn:
            try:
                cur = conn.execute(
                    "INSERT INTO users (username, password_hash, role, created_at) VALUES (?, ?, ?, ?)",
                    (username, password_hash, role, now),
                )
            except Exception as exc:
                if exc.__class__.__name__ == "IntegrityError":
                    raise ValueError("username already exists") from exc
                raise
            conn.commit()
            user_id = int(cur.lastrowid)
        return UserProfile(id=user_id, username=username, role=role, created_at=now)

    def username_exists(self, username: str) -> bool:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT 1 FROM users WHERE username=? LIMIT 1",
                (username,),
            ).fetchone()
        return row is not None

    def get_user_by_username(self, username: str) -> tuple[UserProfile, str] | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
        if not row:
            return None
        return (
            UserProfile(id=row["id"], username=row["username"], role=row["role"], created_at=row["created_at"]),
            row["password_hash"],
        )

    def create_session(self, token: str, user_id: int, expires_at: int | None = None) -> None:
        now = int(time.time())
        with self._connect() as conn:
            if self._mysql:
                conn.execute(
                    """
                    INSERT INTO sessions (token, user_id, created_at, expires_at)
                    VALUES (?, ?, ?, ?)
                    ON DUPLICATE KEY UPDATE
                      user_id=VALUES(user_id),
                      created_at=VALUES(created_at),
                      expires_at=VALUES(expires_at)
                    """,
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
        return UserProfile(id=row["id"], username=row["username"], role=row["role"], created_at=row["created_at"])

    def delete_session(self, token: str) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM sessions WHERE token=?", (token,))
            conn.commit()

    def save_favorite_scheme(self, user_id: int, scheme: FavoriteSchemeCreate) -> FavoriteScheme:
        now = int(time.time())
        with self._connect() as conn:
            if self._mysql:
                cur = conn.execute(
                    """
                    INSERT INTO favorite_schemes (user_id, task_id, title, style, image, created_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    ON DUPLICATE KEY UPDATE
                      title=VALUES(title),
                      style=VALUES(style),
                      image=VALUES(image)
                    """,
                    (user_id, scheme.task_id, scheme.title, scheme.style, scheme.image, now),
                )
                last_id = self._last_insert_id(cur)
                row = conn.execute(
                    """
                    SELECT * FROM favorite_schemes
                    WHERE user_id=? AND ((task_id IS NULL AND id=?) OR task_id=?)
                    ORDER BY id DESC LIMIT 1
                    """,
                    (user_id, last_id, scheme.task_id),
                ).fetchone()
            else:
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

    def add_system_log(
        self,
        *,
        action: str,
        level: str = "info",
        user_id: int | None = None,
        username: str | None = None,
        target_type: str | None = None,
        target_id: str | None = None,
        message: str | None = None,
        duration_ms: int | None = None,
        request_path: str | None = None,
        ip_address: str | None = None,
    ) -> None:
        now = int(time.time())
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO system_logs (
                  user_id, username, level, action, target_type, target_id,
                  message, duration_ms, request_path, ip_address, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    user_id,
                    username,
                    level[:32],
                    action[:80],
                    target_type[:80] if target_type else None,
                    target_id[:191] if target_id else None,
                    message[:1000] if message else None,
                    duration_ms,
                    request_path[:191] if request_path else None,
                    ip_address[:64] if ip_address else None,
                    now,
                ),
            )
            conn.commit()

    def list_system_logs(
        self,
        *,
        limit: int = 100,
        level: str | None = None,
        action: str | None = None,
        username: str | None = None,
        start_at: int | None = None,
        end_at: int | None = None,
    ) -> list[SystemLog]:
        limit = max(1, min(limit, 300))
        filters: list[str] = []
        params: list[object] = []
        if level:
            filters.append("level=?")
            params.append(level)
        if action:
            filters.append("action=?")
            params.append(action)
        if username:
            filters.append("username=?")
            params.append(username)
        if start_at:
            filters.append("created_at>=?")
            params.append(start_at)
        if end_at:
            filters.append("created_at<=?")
            params.append(end_at)
        where = (" WHERE " + " AND ".join(filters)) if filters else ""
        params.append(limit)
        with self._connect() as conn:
            rows = conn.execute(
                f"SELECT * FROM system_logs{where} ORDER BY created_at DESC LIMIT ?",
                params,
            ).fetchall()
        return [self._row_to_system_log(row) for row in rows]

    def admin_dashboard(
        self,
        limit: int = 120,
        offset: int = 0,
        start_at: int | None = None,
        end_at: int | None = None,
        username: str | None = None,
        room_type: str | None = None,
        design_style: str | None = None,
        color_preference: str | None = None,
        status: int | None = None,
    ) -> dict[str, Any]:
        limit = max(1, min(limit, 300))
        offset = max(0, offset)
        filters: list[str] = []
        params: list[object] = []
        if start_at:
            filters.append("created_at>=?")
            params.append(start_at)
        if end_at:
            filters.append("created_at<=?")
            params.append(end_at)
        record_where = (" WHERE " + " AND ".join(filters)) if filters else ""
        list_filters = [f"design_records.{item}" if item.startswith("created_at") else item for item in filters]
        list_params = list(params)
        if username:
            list_filters.append("users.username=?")
            list_params.append(username)
        if room_type:
            list_filters.append("design_records.room_type=?")
            list_params.append(room_type)
        if design_style:
            list_filters.append("design_records.design_style=?")
            list_params.append(design_style)
        if color_preference:
            list_filters.append("design_records.color_preference=?")
            list_params.append(color_preference)
        if status is not None:
            list_filters.append("design_records.status=?")
            list_params.append(status)
        list_where = (" WHERE " + " AND ".join(list_filters)) if list_filters else ""
        date_expr = "DATE(FROM_UNIXTIME(created_at))" if self._mysql else "date(created_at, 'unixepoch', 'localtime')"
        with self._connect() as conn:
            totals = conn.execute(
                f"""
                SELECT
                  (SELECT COUNT(*) FROM users) AS users,
                  (SELECT COUNT(*) FROM design_records{record_where}) AS records,
                  (SELECT COUNT(*) FROM favorite_schemes) AS favorites,
                  (SELECT COUNT(*) FROM design_records{record_where + (' AND' if record_where else ' WHERE')} status=3) AS successes,
                  (SELECT COUNT(*) FROM design_records{record_where + (' AND' if record_where else ' WHERE')} status=4) AS failures,
                  (SELECT COUNT(*) FROM design_records{record_where + (' AND' if record_where else ' WHERE')} satisfaction_score IS NOT NULL) AS feedbacks,
                  (SELECT ROUND(AVG(satisfaction_score), 2) FROM design_records{record_where + (' AND' if record_where else ' WHERE')} satisfaction_score IS NOT NULL) AS avg_satisfaction,
                  (SELECT ROUND(AVG(lighting_score), 2) FROM design_records{record_where + (' AND' if record_where else ' WHERE')} lighting_score IS NOT NULL) AS avg_lighting,
                  (SELECT ROUND(AVG(style_match_score), 2) FROM design_records{record_where + (' AND' if record_where else ' WHERE')} style_match_score IS NOT NULL) AS avg_style_match,
                  (SELECT ROUND(AVG(space_utilization_score), 2) FROM design_records{record_where + (' AND' if record_where else ' WHERE')} space_utilization_score IS NOT NULL) AS avg_space_utilization
                """,
                tuple(params * 8),
            ).fetchone()
            users = conn.execute(
                """
                SELECT
                  users.id,
                  users.username,
                  users.role,
                  users.created_at,
                  COUNT(design_records.task_id) AS total_records,
                  SUM(CASE WHEN design_records.status=3 THEN 1 ELSE 0 END) AS success_records,
                  SUM(CASE WHEN design_records.status=4 THEN 1 ELSE 0 END) AS failed_records,
                  ROUND(AVG(design_records.satisfaction_score), 2) AS avg_satisfaction,
                  MAX(design_records.updated_at) AS last_used_at
                FROM users
                LEFT JOIN design_records ON design_records.user_id=users.id
                GROUP BY users.id
                ORDER BY COALESCE(last_used_at, users.created_at) DESC
                """
            ).fetchall()
            style_rows = conn.execute(
                f"""
                SELECT COALESCE(design_style, '未设置') AS name, COUNT(*) AS value
                FROM design_records
                {record_where}
                GROUP BY COALESCE(design_style, '未设置')
                ORDER BY value DESC
                """,
                params,
            ).fetchall()
            room_rows = conn.execute(
                f"""
                SELECT COALESCE(room_type, '未设置') AS name, COUNT(*) AS value
                FROM design_records
                {record_where}
                GROUP BY COALESCE(room_type, '未设置')
                ORDER BY value DESC
                """,
                params,
            ).fetchall()
            color_rows = conn.execute(
                f"""
                SELECT COALESCE(color_preference, '未设置') AS name, COUNT(*) AS value
                FROM design_records
                {record_where}
                GROUP BY COALESCE(color_preference, '未设置')
                ORDER BY value DESC
                """,
                params,
            ).fetchall()
            material_rows = conn.execute(
                f"""
                SELECT COALESCE(material_preference, '未设置') AS name, COUNT(*) AS value
                FROM design_records
                {record_where}
                GROUP BY COALESCE(material_preference, '未设置')
                ORDER BY value DESC
                """,
                params,
            ).fetchall()
            status_rows = conn.execute(
                f"""
                SELECT status AS name, COUNT(*) AS value
                FROM design_records
                {record_where}
                GROUP BY status
                ORDER BY status ASC
                """,
                params,
            ).fetchall()
            daily_rows = conn.execute(
                f"""
                SELECT {date_expr} AS day, COUNT(*) AS value
                FROM design_records
                {record_where}
                GROUP BY day
                ORDER BY day DESC
                LIMIT 7
                """,
                params,
            ).fetchall()
            records = conn.execute(
                f"""
                SELECT design_records.*, users.username
                FROM design_records
                LEFT JOIN users ON users.id=design_records.user_id
                {list_where}
                ORDER BY design_records.created_at DESC
                LIMIT ? OFFSET ?
                """,
                (*list_params, limit, offset),
            ).fetchall()
            records_total_row = conn.execute(
                f"""
                SELECT COUNT(*) AS total
                FROM design_records
                LEFT JOIN users ON users.id=design_records.user_id
                {list_where}
                """,
                list_params,
            ).fetchone()
            option_rows = {
                "username": conn.execute(
                    f"""
                    SELECT DISTINCT users.username AS value
                    FROM design_records
                    LEFT JOIN users ON users.id=design_records.user_id
                    {record_where.replace('created_at', 'design_records.created_at')}
                    ORDER BY users.username
                    """,
                    params,
                ).fetchall(),
                "room_type": conn.execute(
                    f"SELECT DISTINCT room_type AS value FROM design_records {record_where} ORDER BY room_type",
                    params,
                ).fetchall(),
                "design_style": conn.execute(
                    f"SELECT DISTINCT design_style AS value FROM design_records {record_where} ORDER BY design_style",
                    params,
                ).fetchall(),
                "color_preference": conn.execute(
                    f"SELECT DISTINCT color_preference AS value FROM design_records {record_where} ORDER BY color_preference",
                    params,
                ).fetchall(),
                "status": conn.execute(
                    f"SELECT DISTINCT status AS value FROM design_records {record_where} ORDER BY status",
                    params,
                ).fetchall(),
            }
            recent_log_rows = conn.execute(
                """
                SELECT *
                FROM system_logs
                ORDER BY created_at DESC
                LIMIT 80
                """
            ).fetchall()

        return {
            "summary": self._plain_dict(totals),
            "users": [self._plain_dict(row) for row in users],
            "styleStats": [self._plain_dict(row) for row in style_rows],
            "roomStats": [self._plain_dict(row) for row in room_rows],
            "colorStats": [self._plain_dict(row) for row in color_rows],
            "materialStats": [self._plain_dict(row) for row in material_rows],
            "statusStats": [self._plain_dict(row) for row in status_rows],
            "dailyStats": list(reversed([self._plain_dict(row) for row in daily_rows])),
            "records": [self._plain_dict(row) for row in records],
            "recentLogs": [self._plain_dict(row) for row in recent_log_rows],
            "filterOptions": {
                key: [row["value"] for row in rows if row["value"] not in {None, ""}]
                for key, rows in option_rows.items()
            },
            "recordsTotal": int((dict(records_total_row) if records_total_row else {}).get("total") or 0),
            "recordsLimit": limit,
            "recordsOffset": offset,
        }

    def _row_to_system_log(self, row: Any) -> SystemLog:
        return SystemLog(
            id=row["id"],
            user_id=row["user_id"],
            username=row["username"],
            level=row["level"],
            action=row["action"],
            target_type=row["target_type"],
            target_id=row["target_id"],
            message=row["message"],
            duration_ms=row["duration_ms"],
            request_path=row["request_path"],
            ip_address=row["ip_address"],
            created_at=row["created_at"],
        )

    def _row_to_task_record(self, row: Any) -> TaskRecord:
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

    def _row_to_favorite_scheme(self, row: Any) -> FavoriteScheme:
        return FavoriteScheme(
            id=row["id"],
            user_id=row["user_id"],
            task_id=row["task_id"],
            title=row["title"],
            style=row["style"],
            image=row["image"],
            created_at=row["created_at"],
        )

    def _row_to_design_record(self, row: Any) -> DesignRecord:
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
            lighting_score=row["lighting_score"],
            style_match_score=row["style_match_score"],
            space_utilization_score=row["space_utilization_score"],
            satisfaction_score=row["satisfaction_score"],
            feedback_text=row["feedback_text"],
            feedback_updated_at=row["feedback_updated_at"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
