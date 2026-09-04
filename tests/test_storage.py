import os
import shutil
import sqlite3
import uuid
import unittest

from nicmanager.models import Profile
from nicmanager.storage import ProfileStore

_TMP_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".tmp_db")


class TestProfileStore(unittest.TestCase):
    def setUp(self):
        os.makedirs(_TMP_ROOT, exist_ok=True)
        # 每个测试独立 db 文件，避免 Windows 文件锁与迁移用例互相干扰
        self.db = os.path.join(_TMP_ROOT, f"t_{uuid.uuid4().hex[:8]}.db")
        self.store = ProfileStore(self.db)

    def tearDown(self):
        try:
            del self.store
        except Exception:  # noqa: BLE001
            pass
        try:
            shutil.rmtree(_TMP_ROOT, ignore_errors=True)
        except Exception:  # noqa: BLE001
            pass

    def test_add_list_get(self):
        p = Profile(
            adapter_name="以太网", name="办公室-静态", mode="static",
            ip="10.0.0.5", prefix=24, gateway="10.0.0.1",
            dns1="114.114.114.114", dns2="8.8.8.8", note="测试",
        )
        self.store.add(p)
        self.assertIsNotNone(p.id)
        rows = self.store.list_by_adapter("以太网")
        self.assertEqual(len(rows), 1)
        got = self.store.get(p.id)
        self.assertEqual(got.name, "办公室-静态")
        self.assertEqual(got.ip, "10.0.0.5")
        self.assertEqual(got.prefix, 24)

    def test_unique_name_per_adapter(self):
        p1 = Profile(adapter_name="WLAN", name="A", mode="dhcp")
        p2 = Profile(adapter_name="WLAN", name="A", mode="static", ip="1.1.1.1", prefix=24)
        self.store.add(p1)
        with self.assertRaises(Exception):
            self.store.add(p2)

    def test_same_name_different_adapter_ok(self):
        p1 = Profile(adapter_name="WLAN", name="A", mode="dhcp")
        p2 = Profile(adapter_name="以太网", name="A", mode="static", ip="1.1.1.1", prefix=24)
        self.store.add(p1)
        self.store.add(p2)  # 不抛异常
        self.assertEqual(len(self.store.list_by_adapter("以太网")), 1)

    def test_update_and_delete(self):
        p = Profile(adapter_name="以太网", name="旧名", mode="static", ip="1.1.1.1", prefix=24)
        self.store.add(p)
        p.name = "新名"
        p.ip = "2.2.2.2"
        self.store.update(p)
        got = self.store.get(p.id)
        self.assertEqual(got.name, "新名")
        self.assertEqual(got.ip, "2.2.2.2")
        self.store.delete(p.id)
        self.assertIsNone(self.store.get(p.id))

    def test_rename_adapter(self):
        self.store.add(Profile(adapter_name="以太网", name="A", mode="dhcp"))
        self.store.add(Profile(adapter_name="以太网", name="B", mode="static", ip="1.1.1.1", prefix=24))
        n = self.store.rename_adapter("以太网", "以太网-新")
        self.assertEqual(n, 2)
        self.assertIn("以太网-新", self.store.adapters_with_profiles())

    def test_persistence_reopen(self):
        p = Profile(adapter_name="WLAN", name="P", mode="static", ip="9.9.9.9", prefix=24)
        self.store.add(p)
        store2 = ProfileStore(self.db)  # 重新打开
        rows = store2.list_by_adapter("WLAN")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].ip, "9.9.9.9")

    def test_extra_ips_roundtrip(self):
        p = Profile(adapter_name="以太网", name="多IP", mode="static", ip="10.0.0.1", prefix=24,
                    extra_ips=["172.16.1.1/16", "192.168.50.10/24"])
        self.store.add(p)
        got = self.store.get(p.id)
        self.assertEqual(got.extra_ips, ["172.16.1.1/16", "192.168.50.10/24"])
        # 更新附加地址
        got.extra_ips = ["8.8.4.4/32"]
        self.store.update(got)
        got2 = self.store.get(p.id)
        self.assertEqual(got2.extra_ips, ["8.8.4.4/32"])

    def test_legacy_db_migration(self):
        """模拟旧库（无 extra_ips 列）打开时自动迁移。"""
        legacy = self.db + ".legacy.db"
        # 用旧 schema 建库（无 extra_ips 列）
        conn = sqlite3.connect(legacy)
        try:
            conn.execute(
                "CREATE TABLE profiles (id INTEGER PRIMARY KEY AUTOINCREMENT,"
                " adapter_name TEXT NOT NULL, name TEXT NOT NULL, mode TEXT NOT NULL DEFAULT 'static',"
                " ip TEXT NOT NULL DEFAULT '', prefix INTEGER NOT NULL DEFAULT 24,"
                " gateway TEXT NOT NULL DEFAULT '', dns1 TEXT NOT NULL DEFAULT '',"
                " dns2 TEXT NOT NULL DEFAULT '', note TEXT NOT NULL DEFAULT '',"
                " created_at TEXT NOT NULL, updated_at TEXT NOT NULL, UNIQUE(adapter_name,name))"
            )
            conn.commit()
        finally:
            conn.close()
        # 打开触发迁移（不应抛异常）
        store2 = ProfileStore(legacy)
        p = Profile(adapter_name="以太网", name="旧档案", mode="static", ip="1.1.1.1", prefix=24)
        store2.add(p)
        got = store2.get(p.id)
        self.assertEqual(got.extra_ips, [])
        self.assertEqual(got.ip, "1.1.1.1")


if __name__ == "__main__":
    unittest.main()
