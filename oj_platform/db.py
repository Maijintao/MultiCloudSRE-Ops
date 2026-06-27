import os
import sqlite3

from . import settings
from .timeutil import utc_now


def connect():
    settings.STATE_DIR.mkdir(parents=True, exist_ok=True)
    if str(settings.DB_FILE) != ":memory:":
        settings.DB_FILE.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(settings.DB_FILE, timeout=30)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA journal_mode=MEMORY" if os.name == "nt" else "PRAGMA journal_mode=WAL")
    except sqlite3.OperationalError:
        pass
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def row_to_dict(row):
    return dict(row) if row else None


def ensure_column(conn, table, column, ddl):
    columns = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    if column not in columns:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")


def init_db():
    from .security import hash_password

    with connect() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL CHECK(role IN ('admin', 'contestant')),
                disabled INTEGER NOT NULL DEFAULT 0,
                api_base_url TEXT,
                api_key TEXT,
                api_key_mask TEXT,
                model TEXT,
                skill TEXT NOT NULL DEFAULT '',
                skills_json TEXT,
                soul_md TEXT NOT NULL DEFAULT '',
                grader_api_key TEXT,
                grader_api_key_mask TEXT,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS submissions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL REFERENCES users(id),
                case_id TEXT NOT NULL,
                source_kind TEXT NOT NULL DEFAULT 'case',
                test_set_id TEXT,
                test_set_name TEXT,
                test_set_case_index INTEGER,
                display_case_name TEXT,
                submission_group_id TEXT,
                status TEXT NOT NULL,
                api_base_url TEXT NOT NULL,
                api_key TEXT,
                api_key_mask TEXT NOT NULL,
                grader_api_key TEXT,
                grader_api_key_mask TEXT,
                grader_base_url TEXT,
                grader_model TEXT,
                model TEXT NOT NULL,
                prompt TEXT NOT NULL,
                answer_mcp_servers_json TEXT,
                skill TEXT NOT NULL DEFAULT '',
                skills_json TEXT,
                soul_md TEXT NOT NULL DEFAULT '',
                answer_transcript TEXT,
                answer_output TEXT,
                answer_returncode INTEGER,
                grade_transcript TEXT,
                grade_output TEXT,
                grade_json TEXT,
                score INTEGER,
                verdict TEXT,
                result_summary TEXT,
                error TEXT,
                run_log TEXT,
                runner_kind TEXT,
                runner_meta TEXT,
                created_at TEXT NOT NULL,
                started_at TEXT,
                finished_at TEXT,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS app_settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_submissions_status_id ON submissions(status, id);
            CREATE INDEX IF NOT EXISTS idx_submissions_user_id ON submissions(user_id, id);
            CREATE INDEX IF NOT EXISTS idx_submissions_user_case_score ON submissions(user_id, case_id, score);
            CREATE INDEX IF NOT EXISTS idx_submissions_created_id ON submissions(created_at, id);
            CREATE INDEX IF NOT EXISTS idx_submissions_case_created_id ON submissions(case_id, created_at, id);
            CREATE INDEX IF NOT EXISTS idx_submissions_source_display_created_id
                ON submissions(source_kind, display_case_name, created_at, id);
            """
        )
        for table, column, ddl in (
            ("users", "api_base_url", "TEXT"),
            ("users", "api_key", "TEXT"),
            ("users", "api_key_mask", "TEXT"),
            ("users", "model", "TEXT"),
            ("users", "skill", "TEXT NOT NULL DEFAULT ''"),
            ("users", "skills_json", "TEXT"),
            ("users", "soul_md", "TEXT NOT NULL DEFAULT ''"),
            ("users", "grader_api_key", "TEXT"),
            ("users", "grader_api_key_mask", "TEXT"),
            ("submissions", "run_log", "TEXT"),
            ("submissions", "skills_json", "TEXT"),
            ("submissions", "soul_md", "TEXT NOT NULL DEFAULT ''"),
            ("submissions", "runner_kind", "TEXT"),
            ("submissions", "runner_meta", "TEXT"),
            ("submissions", "grader_api_key", "TEXT"),
            ("submissions", "grader_api_key_mask", "TEXT"),
            ("submissions", "grader_base_url", "TEXT"),
            ("submissions", "grader_model", "TEXT"),
            ("submissions", "answer_mcp_servers_json", "TEXT"),
            ("submissions", "source_kind", "TEXT NOT NULL DEFAULT 'case'"),
            ("submissions", "test_set_id", "TEXT"),
            ("submissions", "test_set_name", "TEXT"),
            ("submissions", "test_set_case_index", "INTEGER"),
            ("submissions", "display_case_name", "TEXT"),
            ("submissions", "submission_group_id", "TEXT"),
        ):
            ensure_column(conn, table, column, ddl)

        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_submissions_display_created_id "
            "ON submissions(display_case_name, created_at, id)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_submissions_source_display_created_id "
            "ON submissions(source_kind, display_case_name, created_at, id)"
        )

        protected_admin = conn.execute(
            "SELECT id, role, disabled FROM users WHERE username = ?",
            (settings.ADMIN_USERNAME,),
        ).fetchone()
        if not protected_admin:
            conn.execute(
                """
                INSERT INTO users (username, password_hash, role, created_at)
                VALUES (?, ?, 'admin', ?)
                """,
                (settings.ADMIN_USERNAME, hash_password(settings.ADMIN_PASSWORD), utc_now()),
            )
        else:
            conn.execute(
                "UPDATE users SET role = 'admin', disabled = 0 WHERE id = ?",
                (protected_admin["id"],),
            )


def get_setting(key, default=""):
    with connect() as conn:
        row = conn.execute("SELECT value FROM app_settings WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else default


def set_setting(key, value):
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO app_settings (key, value, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at
            """,
            (key, value or "", utc_now()),
        )
