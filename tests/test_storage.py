import os
import shutil
import unittest

from nicmanager.models import Profile
from nicmanager.storage import ProfileStore

_TMP_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".tmp_db")


class TestProfileStore(unittest.TestCase):
    def setUp(self):
        os.makedirs(_TMP_ROOT, exist_ok=True)
        self.db = os.path.join(_TMP_ROOT, "profiles.db")
        if os.path.exists(self.db):
            os.unlink(self.db)
        self.store = ProfileStore(self.db)

    def tearDown(self):
        shutil.rmtree(_TMP_ROOT, ignore_errors=True)

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


if __name__ == "__main__":
    unittest.main()
