"""Persistent, page-level job state used for recovery and desktop control."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .models import JobState, PreflightReport


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class JobStore:
    """SQLite-backed state store. All paths are scoped to one job workspace."""

    def __init__(self, database_path: Path):
        self.database_path = database_path
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        return connection

    @contextmanager
    def _transaction(self):
        """Commit and close every SQLite connection deterministically on Windows."""

        connection = self._connect()
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def _initialize(self) -> None:
        with self._transaction() as connection:
            connection.executescript(
                """
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS jobs (
                    job_id TEXT PRIMARY KEY,
                    source_path TEXT NOT NULL,
                    source_sha256 TEXT NOT NULL,
                    state TEXT NOT NULL,
                    config_json TEXT NOT NULL,
                    preflight_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    error_message TEXT
                );
                CREATE TABLE IF NOT EXISTS pages (
                    page_index INTEGER PRIMARY KEY,
                    state TEXT NOT NULL,
                    image_path TEXT,
                    warning_json TEXT NOT NULL DEFAULT '[]',
                    updated_at TEXT NOT NULL
                );
                """
            )

    def create(
        self,
        *,
        job_id: str,
        source_path: Path,
        config: dict[str, Any],
        preflight: PreflightReport,
    ) -> None:
        with self._transaction() as connection:
            connection.execute(
                """
                INSERT INTO jobs(job_id, source_path, source_sha256, state, config_json, preflight_json, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    job_id,
                    str(source_path),
                    file_sha256(source_path),
                    JobState.CREATED.value,
                    json.dumps(config, ensure_ascii=False),
                    json.dumps(preflight.to_dict(), ensure_ascii=False),
                    utc_now(),
                    utc_now(),
                ),
            )
            connection.executemany(
                "INSERT INTO pages(page_index, state, updated_at) VALUES (?, ?, ?)",
                [(index, "pending", utc_now()) for index in range(preflight.page_count)],
            )

    def set_state(self, state: JobState, *, error_message: str | None = None) -> None:
        with self._transaction() as connection:
            connection.execute(
                "UPDATE jobs SET state=?, error_message=?, updated_at=?",
                (state.value, error_message, utc_now()),
            )

    def state(self) -> JobState:
        with self._transaction() as connection:
            row = connection.execute("SELECT state FROM jobs LIMIT 1").fetchone()
        if row is None:
            raise RuntimeError("任务数据库未初始化。")
        return JobState(row["state"])

    def job_details(self) -> dict[str, Any]:
        with self._transaction() as connection:
            row = connection.execute("SELECT * FROM jobs LIMIT 1").fetchone()
        if row is None:
            raise RuntimeError("任务数据库未初始化。")
        return dict(row)

    def mark_page(self, page_index: int, *, state: str, image_path: Path | None = None, warnings: list[str] | None = None) -> None:
        with self._transaction() as connection:
            connection.execute(
                """
                UPDATE pages SET state=?, image_path=?, warning_json=?, updated_at=? WHERE page_index=?
                """,
                (state, str(image_path) if image_path else None, json.dumps(warnings or [], ensure_ascii=False), utc_now(), page_index),
            )

    def completed_page_paths(self) -> dict[int, Path]:
        with self._transaction() as connection:
            rows = connection.execute(
                "SELECT page_index, image_path FROM pages WHERE state='rendered' AND image_path IS NOT NULL"
            ).fetchall()
        return {int(row["page_index"]): Path(row["image_path"]) for row in rows}

    def should_cancel(self) -> bool:
        return self.state() in {JobState.CANCELLING, JobState.CANCELLED}


class JobWorkspace:
    """Filesystem layout for one isolated conversion job."""

    def __init__(self, root: Path, job_id: str):
        self.root = root.resolve()
        self.job_id = job_id
        self.path = self.root / "jobs" / job_id
        self.pages_dir = self.path / "pages"
        self.output_dir = self.path / "output"
        self.logs_dir = self.path / "logs"
        self.store = JobStore(self.path / "state.sqlite")

    @classmethod
    def create(cls, root: str | Path) -> "JobWorkspace":
        workspace = cls(Path(root), uuid.uuid4().hex)
        workspace.pages_dir.mkdir(parents=True, exist_ok=False)
        workspace.output_dir.mkdir(parents=True, exist_ok=True)
        workspace.logs_dir.mkdir(parents=True, exist_ok=True)
        return workspace

    @classmethod
    def open(cls, root: str | Path, job_id: str) -> "JobWorkspace":
        # Validate before constructing JobStore: its initializer deliberately creates
        # the SQLite file, which must never turn an invalid resume request into a
        # new, empty job directory.
        root_path = Path(root).resolve()
        database_path = root_path / "jobs" / job_id / "state.sqlite"
        if not database_path.is_file():
            raise FileNotFoundError(f"找不到可恢复的任务：{job_id}")
        return cls(root_path, job_id)

    def page_dir(self, page_index: int) -> Path:
        directory = self.pages_dir / f"{page_index + 1:04d}"
        directory.mkdir(parents=True, exist_ok=True)
        return directory
