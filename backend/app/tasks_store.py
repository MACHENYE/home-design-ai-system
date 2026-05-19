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


class MySQLConnectionAdapter:  # 封装 PyMySQL 连接，使其提供接近 sqlite 的执行接口
    def __init__(self, conn: Any):  # 初始化对象并保存必要的连接或配置状态
        self._conn = conn

    def __enter__(self) -> "MySQLConnectionAdapter":  # 进入数据库连接上下文并返回适配器自身
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:  # 退出上下文时关闭底层数据库连接
        self._conn.close()

    def execute(self, sql: str, params: list[object] | tuple[object, ...] = ()):  # 执行 SQL 语句并把 sqlite 风格占位符转换为 MySQL 占位符
        cursor = self._conn.cursor()
        cursor.execute(sql.replace("?", "%s"), params)
        return cursor

    def cursor(self):  # 返回底层 PyMySQL 游标，供复杂查询直接使用
        return self._conn.cursor()

    def commit(self) -> None:  # 提交当前数据库事务，确保写入生效
        self._conn.commit()


class TasksStore:  # 封装任务、用户、设计记录、收藏和日志等数据库访问逻辑
    def __init__(self, database_url: str):  # 初始化对象并保存必要的连接或配置状态
        self._database_url = database_url.strip()
        self._mysql = self._database_url.startswith(("mysql://", "mysql+pymysql://"))
        if not self._mysql:
            raise RuntimeError("DATABASE_URL must be configured with a MySQL connection string.")
        self._init()

    def _connect(self):  # 根据数据库 URL 创建一个新的 MySQL 连接
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

    def _execute(self, conn: Any, sql: str, params: list[object] | tuple[object, ...] = ()):  # 统一执行 SQL 语句，兼容不同数据库占位符写法
        if not self._mysql:
            return conn.execute(sql, params)
        cursor = conn.cursor()
        cursor.execute(sql.replace("?", "%s"), params)
        return cursor

    def _fetchone(self, conn: Any, sql: str, params: list[object] | tuple[object, ...] = ()):  # 执行查询并返回第一条数据库记录
        return self._execute(conn, sql, params).fetchone()

    def _fetchall(self, conn: Any, sql: str, params: list[object] | tuple[object, ...] = ()):  # 执行查询并返回全部数据库记录
        return self._execute(conn, sql, params).fetchall()

    def _create_table(self, conn: Any, sql: str) -> None:  # 创建数据表，并在 MySQL 下转换字段类型定义
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

    def _last_insert_id(self, cursor: Any) -> int:  # 读取最近一次插入操作产生的自增主键
        return int(cursor.lastrowid)

    def _row_dict(self, row: Any) -> dict[str, Any]:  # 将数据库行对象转换为普通字典
        return dict(row) if row else {}

    def _plain_dict(self, row: Any) -> dict[str, Any]:  # 将数据库行中的 Decimal 和日期等值转换为可 JSON 化数据
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

    def _init(self) -> None:  # 初始化全部业务表、字段、外键、索引和种子数据
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
                CREATE TABLE IF NOT EXISTS task_cancellations (
                  task_id TEXT PRIMARY KEY,
                  remote_task_id TEXT NULL,
                  user_id INTEGER NULL,
                  created_at INTEGER NOT NULL
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
                  mask_url TEXT NULL,
                  result_image_url TEXT NULL,
                  error_message TEXT NULL,
                  source_task_id TEXT NULL,
                  iteration_no INTEGER NOT NULL DEFAULT 1,
                  interaction_notes_json TEXT NULL,
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
            self._create_table(
                conn,
                """
                CREATE TABLE IF NOT EXISTS design_assets (
                  id INTEGER PRIMARY KEY AUTOINCREMENT,
                  task_id VARCHAR(191) NULL,
                  user_id INTEGER NULL,
                  asset_type VARCHAR(40) NOT NULL,
                  url TEXT NOT NULL,
                  source VARCHAR(40) NOT NULL DEFAULT 'upload',
                  mime_type VARCHAR(80) NULL,
                  created_at INTEGER NOT NULL,
                  FOREIGN KEY(task_id) REFERENCES tasks(task_id) ON DELETE CASCADE,
                  FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE SET NULL
                )
                """
            )
            self._create_table(
                conn,
                """
                CREATE TABLE IF NOT EXISTS design_iterations (
                  id INTEGER PRIMARY KEY AUTOINCREMENT,
                  task_id VARCHAR(191) NOT NULL,
                  iteration_no INTEGER NOT NULL,
                  room_type VARCHAR(80) NULL,
                  design_style VARCHAR(80) NULL,
                  source_task_id VARCHAR(191) NULL,
                  interaction_notes_json TEXT NULL,
                  mode VARCHAR(40) NOT NULL,
                  provider VARCHAR(40) NOT NULL,
                  prompt_snapshot TEXT NOT NULL,
                  status INTEGER NOT NULL,
                  score DECIMAL(5,2) NULL,
                  created_at INTEGER NOT NULL,
                  updated_at INTEGER NOT NULL,
                  UNIQUE(task_id, iteration_no),
                  FOREIGN KEY(task_id) REFERENCES tasks(task_id) ON DELETE CASCADE
                )
                """
            )
            self._create_table(
                conn,
                """
                CREATE TABLE IF NOT EXISTS generation_metrics (
                  id INTEGER PRIMARY KEY AUTOINCREMENT,
                  task_id VARCHAR(191) NOT NULL UNIQUE,
                  provider VARCHAR(40) NOT NULL,
                  remote_task_id VARCHAR(191) NULL,
                  queued_at INTEGER NULL,
                  started_at INTEGER NULL,
                  finished_at INTEGER NULL,
                  duration_ms INTEGER NULL,
                  image_count INTEGER NOT NULL DEFAULT 1,
                  result_format VARCHAR(20) NULL,
                  error_code VARCHAR(80) NULL,
                  created_at INTEGER NOT NULL,
                  updated_at INTEGER NOT NULL,
                  FOREIGN KEY(task_id) REFERENCES tasks(task_id) ON DELETE CASCADE
                )
                """
            )
            self._create_table(
                conn,
                """
                CREATE TABLE IF NOT EXISTS style_knowledge_base (
                  id INTEGER PRIMARY KEY AUTOINCREMENT,
                  category VARCHAR(80) NOT NULL,
                  name VARCHAR(120) NOT NULL,
                  color_palette VARCHAR(191) NULL,
                  materials VARCHAR(191) NULL,
                  description TEXT NULL,
                  prompt_hint TEXT NULL,
                  created_at INTEGER NOT NULL,
                  updated_at INTEGER NOT NULL,
                  UNIQUE(category, name)
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
            self._ensure_column(conn, "design_records", "source_task_id", "VARCHAR(191) NULL")
            self._ensure_column(conn, "design_records", "iteration_no", "INTEGER NOT NULL DEFAULT 1")
            self._ensure_column(conn, "design_records", "interaction_notes_json", "TEXT NULL")
            self._ensure_column(conn, "users", "role", "TEXT NOT NULL DEFAULT 'user'")
            self._ensure_column(conn, "system_logs", "duration_ms", "INTEGER NULL")
            self._ensure_column(conn, "system_logs", "request_path", "TEXT NULL")
            self._ensure_column(conn, "system_logs", "ip_address", "TEXT NULL")
            self._ensure_column(conn, "design_iterations", "room_type", "VARCHAR(80) NULL")
            self._ensure_column(conn, "design_iterations", "design_style", "VARCHAR(80) NULL")
            self._ensure_column(conn, "design_iterations", "source_task_id", "VARCHAR(191) NULL")
            self._ensure_column(conn, "design_iterations", "interaction_notes_json", "TEXT NULL")
            self._remove_project_room_tables(conn)
            self._remove_reference_image_column(conn)
            self._normalize_mysql_schema(conn)
            if not self._mysql:
                conn.execute("DROP INDEX IF EXISTS idx_users_username_lower")
            conn.execute("UPDATE users SET role='user' WHERE username!='admin' AND role='admin'")
            conn.execute("UPDATE users SET role='admin' WHERE username='admin'")
            conn.commit()
        self._backfill_design_records()
        self._seed_analytics_tables()

    def _seed_analytics_tables(self) -> None:  # 根据已有设计记录回填素材、迭代、指标和知识库辅助数据
        now = int(time.time())
        styles = [
            ("风格", "现代简约", "暖白、原木、黑白灰", "原木、微水泥、金属线条", "强调干净线条、功能收纳和通透采光。", "减少装饰噪声，保留空间边界，突出自然光与克制材质。"),
            ("风格", "新中式", "米色、胡桃木、留白", "原木、格栅、布艺", "融合东方秩序感与现代居住舒适度。", "保留对称关系，使用木质格栅、温润墙面和雅致软装。"),
            ("风格", "北欧", "暖白、浅木色、低饱和色", "原木、布艺、藤编", "强调自然、轻盈和家庭友好。", "使用柔和自然光、浅色木纹和简洁家具比例。"),
            ("风格", "侘寂风", "深灰、米灰、低饱和莫兰迪", "微水泥、亚麻、陶土", "强调材质肌理、安静氛围和克制留白。", "突出墙面肌理与自然漫射光，避免过度装饰。"),
            ("风格", "奶油风", "奶油色、浅咖、暖白", "布艺、木饰面、柔光灯带", "适合柔和温暖、明亮舒适的居住场景。", "加入圆角家具、柔和墙面和低对比暖光。"),
            ("风格", "中古风", "米色、胡桃木、复古棕", "胡桃木、藤编、皮革", "强调复古家具尺度和温润层次。", "使用胡桃木家具、复古灯具和沉稳材质对比。"),
            ("空间", "客厅", "暖白、米色、局部强调色", "布艺、原木、石材", "家庭会客与日常活动中心。", "优先保证动线、采光、电视墙和收纳关系。"),
            ("空间", "卧室", "低饱和、暖白、浅木色", "布艺、原木、软包", "强调休息氛围与舒适尺度。", "减少强对比，强调床头、灯光与收纳整合。"),
            ("空间", "书房", "深灰、木色、低饱和色", "微水泥、原木、金属", "强调专注、安静和低干扰。", "控制视觉噪声，突出书桌、书架和局部照明。"),
            ("材料", "原木", "暖木色、浅木色、胡桃木", "木饰面、木地板、格栅", "增强自然感和居住温度。", "表现清晰木纹，避免塑料感和比例失真。"),
            ("材料", "微水泥", "灰、米灰、深灰", "连续墙地面、肌理涂料", "提升整体性和高级克制感。", "强调细腻颗粒、手工抹痕和柔和光影。"),
            ("材料", "布艺", "米白、奶油、莫兰迪", "沙发、窗帘、软包", "提升柔和触感和生活气息。", "突出织物纹理，家具比例真实自然。"),
        ]
        with self._connect() as conn:
            for item in styles:
                conn.execute(
                    """
                    INSERT INTO style_knowledge_base (
                      category, name, color_palette, materials, description,
                      prompt_hint, created_at, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ON DUPLICATE KEY UPDATE
                      color_palette=VALUES(color_palette),
                      materials=VALUES(materials),
                      description=VALUES(description),
                      prompt_hint=VALUES(prompt_hint),
                      updated_at=VALUES(updated_at)
                    """,
                    (*item, now, now),
                )

            rows = conn.execute(
                """
                SELECT
                  design_records.*,
                  users.username,
                  tasks.raw_json,
                  tasks.remote_task_id
                FROM design_records
                LEFT JOIN users ON users.id=design_records.user_id
                LEFT JOIN tasks ON tasks.task_id=design_records.task_id
                ORDER BY design_records.created_at ASC
                """
            ).fetchall()
            iteration_counts: dict[tuple[int | None, str], int] = {}

            for row in rows:
                user_id = row["user_id"]
                room_type = row["room_type"] or "未设置空间"
                design_style = row["design_style"] or "未设置风格"
                iteration_key = (user_id, room_type)
                iteration_counts[iteration_key] = iteration_counts.get(iteration_key, 0) + 1
                iteration_no = iteration_counts[iteration_key]

                raw = {}
                if row.get("raw_json"):
                    try:
                        raw = json.loads(row["raw_json"])
                    except json.JSONDecodeError:
                        raw = {}
                request_data = raw.get("request") if isinstance(raw, dict) else {}
                provider = str(raw.get("provider") or ("nanobanana" if row.get("remote_task_id") else "unknown"))
                mode = str(request_data.get("mode") or "basic") if isinstance(request_data, dict) else "basic"
                output_format = str(request_data.get("output_format") or "png") if isinstance(request_data, dict) else "png"
                score_values = [
                    row.get("lighting_score"),
                    row.get("style_match_score"),
                    row.get("space_utilization_score"),
                    row.get("satisfaction_score"),
                ]
                numeric_scores = [int(score) for score in score_values if score is not None]
                avg_score = round(sum(numeric_scores) / len(numeric_scores), 2) if numeric_scores else None

                conn.execute(
                    """
                    INSERT INTO design_iterations (
                      task_id, iteration_no, room_type, design_style, source_task_id,
                      interaction_notes_json, mode, provider, prompt_snapshot, status,
                      score, created_at, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON DUPLICATE KEY UPDATE
                      room_type=VALUES(room_type),
                      design_style=VALUES(design_style),
                      source_task_id=VALUES(source_task_id),
                      interaction_notes_json=VALUES(interaction_notes_json),
                      mode=VALUES(mode),
                      provider=VALUES(provider),
                      prompt_snapshot=VALUES(prompt_snapshot),
                      status=VALUES(status),
                      score=VALUES(score),
                      updated_at=VALUES(updated_at)
                    """,
                    (
                        row["task_id"],
                        iteration_no,
                        room_type,
                        design_style,
                        row.get("source_task_id"),
                        row.get("interaction_notes_json"),
                        mode,
                        provider,
                        row["prompt"],
                        row["status"],
                        avg_score,
                        row["created_at"],
                        row["updated_at"],
                    ),
                )

                duration_ms = None
                if row["created_at"] and row["updated_at"]:
                    duration_ms = max(0, int(row["updated_at"] - row["created_at"]) * 1000)
                conn.execute(
                    """
                    INSERT INTO generation_metrics (
                      task_id, provider, remote_task_id, queued_at, started_at,
                      finished_at, duration_ms, image_count, result_format,
                      error_code, created_at, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON DUPLICATE KEY UPDATE
                      provider=VALUES(provider),
                      remote_task_id=VALUES(remote_task_id),
                      finished_at=VALUES(finished_at),
                      duration_ms=VALUES(duration_ms),
                      result_format=VALUES(result_format),
                      error_code=VALUES(error_code),
                      updated_at=VALUES(updated_at)
                    """,
                    (
                        row["task_id"],
                        provider,
                        row.get("remote_task_id"),
                        row["created_at"],
                        row["created_at"],
                        row["updated_at"],
                        duration_ms,
                        1 if row.get("result_image_url") else 0,
                        output_format,
                        "GENERATION_FAILED" if row.get("error_message") else None,
                        row["created_at"],
                        row["updated_at"],
                    ),
                )

                assets = [
                    ("draft", row.get("draft_image_url"), "upload"),
                    ("mask", row.get("mask_url"), "mask"),
                    ("result", row.get("result_image_url"), "generation"),
                ]
                for asset_type, url, source in assets:
                    if not url:
                        continue
                    existing = conn.execute(
                        """
                        SELECT id FROM design_assets
                        WHERE task_id=? AND asset_type=? AND url=?
                        LIMIT 1
                        """,
                        (row["task_id"], asset_type, url),
                    ).fetchone()
                    if existing:
                        continue
                    mime_type = "image/png" if str(url).lower().endswith(".png") or asset_type in {"mask", "result"} else "image/jpeg"
                    conn.execute(
                        """
                        INSERT INTO design_assets (
                          task_id, user_id, asset_type, url, source, mime_type, created_at
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                        """,
                        (row["task_id"], user_id, asset_type, url, source, mime_type, row["created_at"]),
                    )
            conn.commit()

    def _ensure_column(self, conn: Any, table: str, column: str, definition: str) -> None:  # 检查字段是否存在，不存在时自动添加
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

    def _drop_foreign_keys_for_column(self, conn: Any, table: str, column: str) -> None:  # 删除指定表字段上的外键约束，便于迁移旧结构
        rows = conn.execute(
            """
            SELECT CONSTRAINT_NAME AS name
            FROM INFORMATION_SCHEMA.KEY_COLUMN_USAGE
            WHERE TABLE_SCHEMA=DATABASE()
              AND TABLE_NAME=?
              AND COLUMN_NAME=?
              AND REFERENCED_TABLE_NAME IS NOT NULL
            """,
            (table, column),
        ).fetchall()
        for row in rows:
            conn.execute(f"ALTER TABLE {table} DROP FOREIGN KEY {row['name']}")

    def _drop_index_if_exists(self, conn: Any, table: str, index_name: str) -> None:  # 检查索引是否存在，存在时删除该索引
        row = conn.execute(
            """
            SELECT INDEX_NAME AS name
            FROM INFORMATION_SCHEMA.STATISTICS
            WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME=? AND INDEX_NAME=?
            LIMIT 1
            """,
            (table, index_name),
        ).fetchone()
        if row:
            conn.execute(f"ALTER TABLE {table} DROP INDEX {index_name}")

    def _drop_column_if_exists(self, conn: Any, table: str, column: str) -> None:  # 检查字段是否存在，存在时删除该字段
        row = conn.execute(
            """
            SELECT COLUMN_NAME AS name
            FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME=? AND COLUMN_NAME=?
            LIMIT 1
            """,
            (table, column),
        ).fetchone()
        if row:
            conn.execute(f"ALTER TABLE {table} DROP COLUMN {column}")

    def _remove_project_room_tables(self, conn: Any) -> None:  # 清理已经废弃的项目表和房间表及相关字段
        if not self._mysql:
            return
        for column in ("project_id", "room_id"):
            self._drop_foreign_keys_for_column(conn, "design_iterations", column)
        self._drop_index_if_exists(conn, "design_iterations", "idx_design_iterations_project")
        self._drop_index_if_exists(conn, "design_iterations", "idx_design_iterations_room")
        self._drop_column_if_exists(conn, "design_iterations", "project_id")
        self._drop_column_if_exists(conn, "design_iterations", "room_id")
        conn.execute("DROP TABLE IF EXISTS project_rooms")
        conn.execute("DROP TABLE IF EXISTS design_projects")

    def _remove_reference_image_column(self, conn: Any) -> None:  # 清理已废弃的风格参考图字段和素材记录
        if not self._mysql:
            return
        self._drop_column_if_exists(conn, "design_records", "reference_image_url")
        conn.execute("DELETE FROM design_assets WHERE asset_type='reference'")

    def _normalize_mysql_schema(self, conn: Any) -> None:  # 统一 MySQL 字段类型、历史数据、外键和索引结构
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

        # 创建外键前先规范历史数据，避免旧记录导致约束创建失败
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
        self._ensure_foreign_key(conn, "design_assets", "fk_design_assets_task", "task_id", "tasks", "task_id", "ON DELETE CASCADE")
        self._ensure_foreign_key(conn, "design_assets", "fk_design_assets_user", "user_id", "users", "id", "ON DELETE SET NULL")
        self._ensure_foreign_key(conn, "design_iterations", "fk_design_iterations_task", "task_id", "tasks", "task_id", "ON DELETE CASCADE")
        self._ensure_foreign_key(conn, "generation_metrics", "fk_generation_metrics_task", "task_id", "tasks", "task_id", "ON DELETE CASCADE")

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
            "design_assets": [
                ("idx_design_assets_task", "task_id"),
                ("idx_design_assets_user", "user_id"),
                ("idx_design_assets_type", "asset_type"),
            ],
            "design_iterations": [
                ("idx_design_iterations_task", "task_id"),
                ("idx_design_iterations_room_type", "room_type"),
                ("idx_design_iterations_style", "design_style"),
                ("idx_design_iterations_status", "status"),
                ("idx_design_iterations_created", "created_at"),
            ],
            "generation_metrics": [
                ("idx_generation_metrics_provider", "provider"),
                ("idx_generation_metrics_remote", "remote_task_id"),
                ("idx_generation_metrics_duration", "duration_ms"),
            ],
            "style_knowledge_base": [
                ("idx_style_knowledge_category", "category"),
                ("idx_style_knowledge_name", "name"),
            ],
        }
        for table, specs in index_specs.items():
            for index_name, columns in specs:
                self._ensure_index(conn, table, index_name, columns)

    def _modify_column_if_exists(self, conn: Any, table: str, column: str, definition: str) -> None:  # 字段存在时修改其 MySQL 类型定义
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

    def _ensure_index(self, conn: Any, table: str, index_name: str, columns: str) -> None:  # 确保某个业务查询需要的索引已经创建
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
    ) -> None:  # 确保业务表之间的外键约束已经创建
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

    def _backfill_design_records(self) -> None:  # 把旧任务 raw_json 中的请求信息补写到设计记录表
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
                      keep_structure, draft_image_url, mask_url, result_image_url,
                      error_message, created_at, updated_at, user_id
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                        request.get("mask_url"),
                        row["result_image_url"],
                        row["error_message"],
                        row["created_at"],
                        row["updated_at"],
                        row["user_id"] if "user_id" in row.keys() else None,
                    ),
                )
            conn.commit()

    def upsert(self, task_id: str, status: NanoBananaTaskStatus, *, raw: dict[str, Any] | None = None, user_id: int | None = None) -> None:  # 新增或更新任务基础状态、结果和原始响应数据
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

    def attach_remote_task(self, task_id: str, remote_task_id: str, *, raw: dict[str, Any] | None = None) -> None:  # 把本地任务编号与远程模型任务编号绑定
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

    def get_by_remote_task_id(self, remote_task_id: str) -> TaskRecord | None:  # 根据远程任务编号反查本地任务记录
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
    ) -> None:  # 更新任务的最终状态、结果图片和错误信息
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

    def get(self, task_id: str) -> TaskRecord | None:  # 根据任务编号查询单条任务记录
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM tasks WHERE task_id=?", (task_id,)).fetchone()
        return self._row_to_task_record(row) if row else None

    def list_recent(self, limit: int = 50, user_id: int | None = None) -> list[TaskRecord]:  # 按用户维度查询最近提交的任务记录
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

    def cancel_task(self, task_id: str, user_id: int, message: str) -> TaskRecord | None:  # 将当前用户的运行中任务标记为失败，用错误信息区分用户终止
        now = int(time.time())
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT * FROM tasks
                WHERE task_id=? AND (user_id=? OR user_id IS NULL)
                LIMIT 1
                """,
                (task_id, user_id),
            ).fetchone()
            if not row:
                return None
            if int(row["status"]) not in {int(NanoBananaTaskStatus.created), int(NanoBananaTaskStatus.processing)}:
                return self._row_to_task_record(row)
            raw = {}
            if row.get("raw_json"):
                try:
                    raw = json.loads(row["raw_json"])
                except json.JSONDecodeError:
                    raw = {}
            raw_json = json.dumps({**raw, "cancelled": True, "cancel_reason": message}, ensure_ascii=False)
            conn.execute(
                """
                UPDATE tasks
                SET status=?, updated_at=?, error_message=?, raw_json=?
                WHERE task_id=? AND status IN (?, ?)
                """,
                (
                    int(NanoBananaTaskStatus.failed),
                    now,
                    message,
                    raw_json,
                    task_id,
                    int(NanoBananaTaskStatus.created),
                    int(NanoBananaTaskStatus.processing),
                ),
            )
            conn.execute(
                """
                UPDATE design_records
                SET status=?, updated_at=?, error_message=?
                WHERE task_id=?
                """,
                (int(NanoBananaTaskStatus.failed), now, message, task_id),
            )
            conn.execute(
                """
                UPDATE design_iterations
                SET status=?, updated_at=?
                WHERE task_id=?
                """,
                (int(NanoBananaTaskStatus.failed), now, task_id),
            )
            conn.commit()
            updated = conn.execute("SELECT * FROM tasks WHERE task_id=?", (task_id,)).fetchone()
        return self._row_to_task_record(updated) if updated else None

    def cancel_and_delete_task(self, task_id: str, user_id: int) -> bool:  # 记录取消标记后删除当前用户的任务和设计记录
        now = int(time.time())
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT task_id, user_id, remote_task_id, raw_json
                FROM tasks
                WHERE task_id=? AND (user_id=? OR user_id IS NULL)
                LIMIT 1
                """,
                (task_id, user_id),
            ).fetchone()
            if not row:
                return False
            raw = {}
            if row.get("raw_json"):
                try:
                    raw = json.loads(row["raw_json"])
                except json.JSONDecodeError:
                    raw = {}
            remote_task_id = row.get("remote_task_id") or raw.get("remote_task_id")
            conn.execute(
                """
                INSERT INTO task_cancellations (task_id, remote_task_id, user_id, created_at)
                VALUES (?, ?, ?, ?)
                ON DUPLICATE KEY UPDATE
                  remote_task_id=VALUES(remote_task_id),
                  user_id=VALUES(user_id),
                  created_at=VALUES(created_at)
                """,
                (task_id, str(remote_task_id) if remote_task_id else None, user_id, now),
            )
            conn.execute("DELETE FROM favorite_schemes WHERE task_id=? AND (user_id=? OR user_id IS NULL)", (task_id, user_id))
            conn.execute("DELETE FROM design_records WHERE task_id=? AND (user_id=? OR user_id IS NULL)", (task_id, user_id))
            cur = conn.execute("DELETE FROM tasks WHERE task_id=? AND (user_id=? OR user_id IS NULL)", (task_id, user_id))
            conn.commit()
            return cur.rowcount > 0

    def is_cancelled_task_identifier(self, task_id: str) -> bool:  # 判断本地或远程任务编号是否已经被用户取消删除
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT 1
                FROM task_cancellations
                WHERE task_id=? OR remote_task_id=?
                LIMIT 1
                """,
                (task_id, task_id),
            ).fetchone()
        return bool(row)

    def expire_stale_tasks(self, timeout_s: int, *, user_id: int | None = None, task_id: str | None = None, message: str) -> int:  # 将超过时限仍未完成的任务自动标记为失败
        if timeout_s <= 0:
            return 0
        now = int(time.time())
        threshold = now - timeout_s
        where = ["status IN (?, ?)", "created_at<=?"]
        params: list[object] = [int(NanoBananaTaskStatus.created), int(NanoBananaTaskStatus.processing), threshold]
        if user_id is not None:
            where.append("user_id=?")
            params.append(user_id)
        if task_id is not None:
            where.append("task_id=?")
            params.append(task_id)
        where_sql = " AND ".join(where)
        raw_marker = json.dumps({"timed_out": True, "timeout_message": message}, ensure_ascii=False)
        with self._connect() as conn:
            rows = conn.execute(f"SELECT task_id, raw_json FROM tasks WHERE {where_sql}", params).fetchall()
            if not rows:
                return 0
            task_ids = [row["task_id"] for row in rows]
            for row in rows:
                raw = {}
                if row.get("raw_json"):
                    try:
                        raw = json.loads(row["raw_json"])
                    except json.JSONDecodeError:
                        raw = {}
                raw_json = json.dumps({**raw, **json.loads(raw_marker)}, ensure_ascii=False)
                conn.execute(
                    """
                    UPDATE tasks
                    SET status=?, updated_at=?, error_message=?, raw_json=?
                    WHERE task_id=? AND status IN (?, ?)
                    """,
                    (
                        int(NanoBananaTaskStatus.failed),
                        now,
                        message,
                        raw_json,
                        row["task_id"],
                        int(NanoBananaTaskStatus.created),
                        int(NanoBananaTaskStatus.processing),
                    ),
                )
            placeholders = ",".join(["?"] * len(task_ids))
            conn.execute(
                f"""
                UPDATE design_records
                SET status=?, updated_at=?, error_message=?
                WHERE task_id IN ({placeholders})
                """,
                [int(NanoBananaTaskStatus.failed), now, message, *task_ids],
            )
            conn.execute(
                f"""
                UPDATE design_iterations
                SET status=?, updated_at=?
                WHERE task_id IN ({placeholders})
                """,
                [int(NanoBananaTaskStatus.failed), now, *task_ids],
            )
            conn.commit()
        return len(task_ids)

    def save_design_request(
        self,
        task_id: str,
        req: GenerateRequest,
        *,
        status: NanoBananaTaskStatus,
        result_image_url: str | None = None,
        error_message: str | None = None,
        user_id: int | None = None,
    ) -> None:  # 保存一次生成请求的空间、风格、图片和提示词参数
        now = int(time.time())
        draft_image_url = req.image_urls[0] if len(req.image_urls) >= 1 else None
        with self._connect() as conn:
            source_task_id = req.source_task_id.strip() if req.source_task_id else None
            iteration_no = self._next_iteration_no(conn, source_task_id, user_id)
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
                req.mask_url,
                result_image_url,
                error_message,
                source_task_id,
                iteration_no,
                req.interaction_notes_json,
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
                      keep_structure, draft_image_url, mask_url, result_image_url,
                      error_message, source_task_id, iteration_no, interaction_notes_json,
                      created_at, updated_at, user_id
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                      mask_url=VALUES(mask_url),
                      result_image_url=COALESCE(VALUES(result_image_url), result_image_url),
                      error_message=VALUES(error_message),
                      source_task_id=VALUES(source_task_id),
                      iteration_no=VALUES(iteration_no),
                      interaction_notes_json=VALUES(interaction_notes_json),
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
                      keep_structure, draft_image_url, mask_url, result_image_url,
                      error_message, source_task_id, iteration_no, interaction_notes_json,
                      created_at, updated_at, user_id
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                      mask_url=excluded.mask_url,
                      result_image_url=COALESCE(excluded.result_image_url, design_records.result_image_url),
                      error_message=excluded.error_message,
                      source_task_id=excluded.source_task_id,
                      iteration_no=excluded.iteration_no,
                      interaction_notes_json=excluded.interaction_notes_json,
                      updated_at=excluded.updated_at
                    """,
                    params,
                )
            conn.execute(
                """
                INSERT INTO design_iterations (
                  task_id, iteration_no, room_type, design_style, source_task_id,
                  interaction_notes_json, mode, provider, prompt_snapshot, status,
                  created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON DUPLICATE KEY UPDATE
                  room_type=VALUES(room_type),
                  design_style=VALUES(design_style),
                  source_task_id=VALUES(source_task_id),
                  interaction_notes_json=VALUES(interaction_notes_json),
                  mode=VALUES(mode),
                  provider=VALUES(provider),
                  prompt_snapshot=VALUES(prompt_snapshot),
                  status=VALUES(status),
                  updated_at=VALUES(updated_at)
                """,
                (
                    task_id,
                    iteration_no,
                    req.room_type,
                    req.design_style,
                    source_task_id,
                    req.interaction_notes_json,
                    req.mode.value,
                    "nanobanana",
                    req.prompt,
                    int(status),
                    now,
                    now,
                ),
            )
            conn.commit()

    def _next_iteration_no(self, conn: Any, source_task_id: str | None, user_id: int | None) -> int:  # 根据同一方案链的最大版号计算下一版编号
        if not source_task_id:
            return 1
        params: list[object] = []
        where = ""
        if user_id is not None:
            where = "WHERE user_id=? OR user_id IS NULL"
            params.append(user_id)
        rows = conn.execute(
            f"SELECT task_id, source_task_id, iteration_no FROM design_records {where}",
            params,
        ).fetchall()
        by_id = {row["task_id"]: row for row in rows}
        if source_task_id not in by_id:
            return 2

        def root_of(task_id: str) -> str:
            seen: set[str] = set()
            current = task_id
            while current in by_id and current not in seen:
                seen.add(current)
                parent_id = by_id[current].get("source_task_id")
                if not parent_id or parent_id not in by_id:
                    return current
                current = parent_id
            return current

        root_task_id = root_of(source_task_id)
        max_iteration = 1
        for row in rows:
            if root_of(row["task_id"]) == root_task_id:
                max_iteration = max(max_iteration, int(row.get("iteration_no") or 1))
        return max_iteration + 1

    def update_design_result(
        self,
        task_id: str,
        *,
        status: NanoBananaTaskStatus,
        result_image_url: str | None,
        error_message: str | None,
    ) -> None:  # 同步更新设计记录中的生成结果和错误信息
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
            conn.execute(
                """
                UPDATE design_iterations
                SET status=?, updated_at=?
                WHERE task_id=?
                """,
                (int(status), now, task_id),
            )
            conn.commit()

    def get_design_record(self, task_id: str, user_id: int | None = None) -> DesignRecord | None:  # 查询当前用户可访问的单条设计记录详情
        with self._connect() as conn:
            if user_id is None:
                row = conn.execute("SELECT * FROM design_records WHERE task_id=?", (task_id,)).fetchone()
            else:
                row = conn.execute("SELECT * FROM design_records WHERE task_id=? AND user_id=?", (task_id, user_id)).fetchone()
        return self._row_to_design_record(row) if row else None

    def count_design_records(self, design_style: str | None = None, user_id: int | None = None) -> int:  # 按用户或风格条件统计设计记录数量
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
    ) -> list[DesignRecord]:  # 按当前用户和筛选条件返回设计记录列表
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
    ) -> DesignRecord | None:  # 更新设计记录的评分、文字反馈和反馈时间
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

    def delete_task(self, task_id: str, user_id: int | None = None) -> bool:  # 删除任务及其关联的设计记录、收藏、素材和统计数据
        with self._connect() as conn:
            if user_id is None:
                fav_cur = conn.execute("DELETE FROM favorite_schemes WHERE task_id=?", (task_id,))
                record_cur = conn.execute("DELETE FROM design_records WHERE task_id=?", (task_id,))
                task_cur = conn.execute("DELETE FROM tasks WHERE task_id=?", (task_id,))
            else:
                task_row = conn.execute(
                    "SELECT 1 FROM tasks WHERE task_id=? AND (user_id=? OR user_id IS NULL) LIMIT 1",
                    (task_id, user_id),
                ).fetchone()
                record_row = conn.execute(
                    "SELECT 1 FROM design_records WHERE task_id=? AND (user_id=? OR user_id IS NULL) LIMIT 1",
                    (task_id, user_id),
                ).fetchone()
                if not task_row and not record_row:
                    return False
                fav_cur = conn.execute("DELETE FROM favorite_schemes WHERE task_id=? AND (user_id=? OR user_id IS NULL)", (task_id, user_id))
                record_cur = conn.execute("DELETE FROM design_records WHERE task_id=? AND (user_id=? OR user_id IS NULL)", (task_id, user_id))
                task_cur = conn.execute("DELETE FROM tasks WHERE task_id=? AND (user_id=? OR user_id IS NULL)", (task_id, user_id))
            conn.commit()
            return (fav_cur.rowcount + record_cur.rowcount + task_cur.rowcount) > 0

    def delete_design_record(self, task_id: str, user_id: int | None = None) -> bool:  # 删除当前用户自己的设计记录并清理缓存
        return self.delete_task(task_id, user_id=user_id)

    def admin_delete_design_record(self, task_id: str) -> bool:  # 管理员删除任意用户的设计记录并写入日志
        with self._connect() as conn:
            cur = conn.execute("DELETE FROM design_records WHERE task_id=?", (task_id,))
            conn.execute("DELETE FROM favorite_schemes WHERE task_id=?", (task_id,))
            conn.execute("DELETE FROM tasks WHERE task_id=?", (task_id,))
            conn.commit()
            return cur.rowcount > 0

    def create_user(self, username: str, password_hash: str) -> UserProfile:  # 向用户表写入新账号并返回用户资料
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

    def username_exists(self, username: str) -> bool:  # 判断指定用户名是否已经注册
        with self._connect() as conn:
            row = conn.execute(
                "SELECT 1 FROM users WHERE username=? LIMIT 1",
                (username,),
            ).fetchone()
        return row is not None

    def get_user_by_username(self, username: str) -> tuple[UserProfile, str] | None:  # 查询用户资料和密码哈希用于登录校验
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
        if not row:
            return None
        return (
            UserProfile(id=row["id"], username=row["username"], role=row["role"], created_at=row["created_at"]),
            row["password_hash"],
        )

    def create_session(self, token: str, user_id: int, expires_at: int | None = None) -> None:  # 写入登录会话令牌和过期时间
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

    def get_user_by_token(self, token: str) -> UserProfile | None:  # 根据会话令牌查询对应用户，并清理过期会话
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

    def delete_session(self, token: str) -> None:  # 删除指定登录令牌对应的会话
        with self._connect() as conn:
            conn.execute("DELETE FROM sessions WHERE token=?", (token,))
            conn.commit()

    def save_favorite_scheme(self, user_id: int, scheme: FavoriteSchemeCreate) -> FavoriteScheme:  # 保存或更新用户收藏的设计方案
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

    def list_favorite_schemes(self, user_id: int, limit: int = 50) -> list[FavoriteScheme]:  # 查询用户最近收藏的设计方案列表
        limit = max(1, min(limit, 200))
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM favorite_schemes WHERE user_id=? ORDER BY created_at DESC LIMIT ?",
                (user_id, limit),
            ).fetchall()
        return [self._row_to_favorite_scheme(row) for row in rows]

    def delete_favorite_scheme(self, user_id: int, favorite_id: int) -> bool:  # 删除用户指定的收藏方案记录
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
    ) -> None:  # 写入一条系统运行或用户操作日志
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
    ) -> list[SystemLog]:  # 按条件分页查询系统日志记录
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
    ) -> dict[str, Any]:  # 查询管理员后台所需的统计概览、用户列表和生成记录
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

    def _row_to_system_log(self, row: Any) -> SystemLog:  # 把数据库日志行转换为 SystemLog 模型
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

    def _row_to_task_record(self, row: Any) -> TaskRecord:  # 把数据库任务行转换为 TaskRecord 模型
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

    def _row_to_favorite_scheme(self, row: Any) -> FavoriteScheme:  # 把数据库收藏行转换为 FavoriteScheme 模型
        return FavoriteScheme(
            id=row["id"],
            user_id=row["user_id"],
            task_id=row["task_id"],
            title=row["title"],
            style=row["style"],
            image=row["image"],
            created_at=row["created_at"],
        )

    def _row_to_design_record(self, row: Any) -> DesignRecord:  # 把数据库设计记录行转换为 DesignRecord 模型
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
            mask_url=row["mask_url"],
            result_image_url=row["result_image_url"],
            error_message=row["error_message"],
            source_task_id=row.get("source_task_id"),
            iteration_no=int(row.get("iteration_no") or 1),
            interaction_notes_json=row.get("interaction_notes_json"),
            lighting_score=row["lighting_score"],
            style_match_score=row["style_match_score"],
            space_utilization_score=row["space_utilization_score"],
            satisfaction_score=row["satisfaction_score"],
            feedback_text=row["feedback_text"],
            feedback_updated_at=row["feedback_updated_at"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
