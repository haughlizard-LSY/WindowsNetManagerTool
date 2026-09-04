"""Profile 的 SQLite 持久化。"""
from __future__ import annotations

import json
import os
import sqlite3
from contextlib import contextmanager
from typing import Iterator, List, Optional

from nicmanager.models import Profile, now_iso

_SCHEMA = """
CREATE TABLE IF NOT EXISTS profiles (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    adapter_name TEXT NOT NULL,
    name         TEXT NOT NULL,
    mode         TEXT NOT NULL DEFAULT 'static',
    ip           TEXT NOT NULL DEFAULT '',
    prefix       INTEGER NOT NULL DEFAULT 24,
    extra_ips    TEXT NOT NULL DEFAULT '[]',
    gateway      TEXT NOT NULL DEFAULT '',
    dns1         TEXT NOT NULL DEFAULT '',
    dns2         TEXT NOT NULL DEFAULT '',
    note         TEXT NOT NULL DEFAULT '',
    created_at   TEXT NOT NULL,
    updated_at   TEXT NOT NULL,
    UNIQUE(adapter_name, name)
);
"""


class ProfileStore:
    """基于 SQLite 的档案存储。

    默认路径依次尝试（保证任何环境下都能启动，避免 APPDATA 不可写时崩溃）：
      1. %APPDATA%/NetManagerTool/profiles.db   （常规）
      2. %LOCALAPPDATA%/NetManagerTool/profiles.db
      3. 用户主目录/.netmanager/profiles.db
    全部失败则抛异常（由上层给出明确错误提示）。
    """

    def __init__(self, db_path: Optional[str] = None):
        if db_path is None:
            db_path = self._resolve_default_path()
        self.db_path = db_path
        parent = os.path.dirname(db_path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        self._init_schema()

    @staticmethod
    def _resolve_default_path() -> str:
        candidates = []
        for env in ("APPDATA", "LOCALAPPDATA"):
            base = os.environ.get(env)
            if base:
                candidates.append(os.path.join(base, "NetManagerTool", "profiles.db"))
        home = os.path.expanduser("~")
        candidates.append(os.path.join(home, ".netmanager", "profiles.db"))
        errors = []
        for path in candidates:
            try:
                parent = os.path.dirname(path)
                os.makedirs(parent, exist_ok=True)
                # 写测试确认目录可写
                probe = os.path.join(parent, ".write_probe")
                with open(probe, "w", encoding="utf-8") as fh:
                    fh.write("ok")
                os.unlink(probe)
                return path
            except Exception as e:  # noqa: BLE001
                errors.append(f"{path}: {e}")
        raise OSError("无法找到可写目录保存数据。\n" + "\n".join(errors))

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    @contextmanager
    def _session(self) -> Iterator[sqlite3.Connection]:
        """打开连接并在退出时提交+关闭（Windows 上避免文件锁残留）。"""
        conn = self._connect()
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _init_schema(self) -> None:
        with self._session() as conn:
            conn.executescript(_SCHEMA)
            # 旧库迁移：老版本 profiles 表没有 extra_ips 列（v0.1 之前只支持单个静态 IP）
            cols = {row["name"] for row in conn.execute("PRAGMA table_info(profiles)").fetchall()}
            if "extra_ips" not in cols:
                conn.execute("ALTER TABLE profiles ADD COLUMN extra_ips TEXT NOT NULL DEFAULT '[]'")

    # ---------- CRUD ----------
    def add(self, p: Profile) -> Profile:
        ts = now_iso()
        extra = json.dumps(p.extra_ips, ensure_ascii=False)
        with self._session() as conn:
            cur = conn.execute(
                "INSERT INTO profiles (adapter_name,name,mode,ip,prefix,extra_ips,gateway,dns1,dns2,note,created_at,updated_at)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (p.adapter_name, p.name.strip(), p.mode, p.ip, p.prefix, extra, p.gateway, p.dns1, p.dns2,
                 p.note, ts, ts),
            )
            p.id = cur.lastrowid
            p.created_at = p.updated_at = ts
        return p

    def update(self, p: Profile) -> None:
        ts = now_iso()
        extra = json.dumps(p.extra_ips, ensure_ascii=False)
        with self._session() as conn:
            conn.execute(
                "UPDATE profiles SET adapter_name=?,name=?,mode=?,ip=?,prefix=?,extra_ips=?,gateway=?,dns1=?,dns2=?,note=?,updated_at=?"
                " WHERE id=?",
                (p.adapter_name, p.name.strip(), p.mode, p.ip, p.prefix, extra, p.gateway, p.dns1, p.dns2,
                 p.note, ts, p.id),
            )
            p.updated_at = ts

    def delete(self, profile_id: int) -> None:
        with self._session() as conn:
            conn.execute("DELETE FROM profiles WHERE id=?", (profile_id,))

    def get(self, profile_id: int) -> Optional[Profile]:
        with self._session() as conn:
            row = conn.execute("SELECT * FROM profiles WHERE id=?", (profile_id,)).fetchone()
        return self._row_to_profile(row) if row else None

    def list_by_adapter(self, adapter_name: str) -> List[Profile]:
        with self._session() as conn:
            rows = conn.execute(
                "SELECT * FROM profiles WHERE adapter_name=? ORDER BY name COLLATE NOCASE",
                (adapter_name,),
            ).fetchall()
        return [self._row_to_profile(r) for r in rows]

    def list_all(self) -> List[Profile]:
        with self._session() as conn:
            rows = conn.execute("SELECT * FROM profiles ORDER BY adapter_name, name").fetchall()
        return [self._row_to_profile(r) for r in rows]

    def adapters_with_profiles(self) -> List[str]:
        with self._session() as conn:
            rows = conn.execute("SELECT DISTINCT adapter_name FROM profiles ORDER BY adapter_name").fetchall()
        return [r["adapter_name"] for r in rows]

    def rename_adapter(self, old_name: str, new_name: str) -> int:
        """网卡名可能改变；用于重绑定。返回受影响行数。"""
        with self._session() as conn:
            cur = conn.execute(
                "UPDATE profiles SET adapter_name=? WHERE adapter_name=?",
                (new_name, old_name),
            )
            return cur.rowcount

    @staticmethod
    def _row_to_profile(row: sqlite3.Row) -> Profile:
        try:
            extra = json.loads(row["extra_ips"] or "[]")
        except (ValueError, TypeError):
            extra = []
        return Profile(
            id=row["id"],
            adapter_name=row["adapter_name"],
            name=row["name"],
            mode=row["mode"],
            ip=row["ip"],
            prefix=row["prefix"],
            extra_ips=[str(x) for x in extra if x],
            gateway=row["gateway"],
            dns1=row["dns1"],
            dns2=row["dns2"],
            note=row["note"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
