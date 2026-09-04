"""验证旧档案库（无 extra_ips 列）打开后自动迁移。"""
import os
import sqlite3
import sys
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from nicmanager.storage import ProfileStore

legacy = os.path.join(os.path.dirname(os.path.abspath(__file__)), f"mig_{uuid.uuid4().hex[:6]}.db")
conn = sqlite3.connect(legacy)
conn.execute(
    """CREATE TABLE profiles (id INTEGER PRIMARY KEY AUTOINCREMENT,
       adapter_name TEXT NOT NULL, name TEXT NOT NULL, mode TEXT NOT NULL DEFAULT 'static',
       ip TEXT NOT NULL DEFAULT '', prefix INTEGER NOT NULL DEFAULT 24,
       gateway TEXT NOT NULL DEFAULT '', dns1 TEXT NOT NULL DEFAULT '', dns2 TEXT NOT NULL DEFAULT '',
       note TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
       UNIQUE(adapter_name, name))"""
)
conn.execute(
    "INSERT INTO profiles (adapter_name,name,mode,ip,prefix,gateway,created_at,updated_at)"
    " VALUES ('以太网','老档案','static','10.0.0.5',24,'10.0.0.1','t','t')"
)
conn.commit()
conn.close()

s = ProfileStore(legacy)
rows = s.list_by_adapter("以太网")
print("migrated rows:", len(rows), "| extra_ips:", rows[0].extra_ips, "| ip:", rows[0].ip)
os.unlink(legacy)
print("MIGRATION OK")
