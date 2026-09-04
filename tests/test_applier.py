import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from nicmanager.models import AdapterInfo, Profile  # noqa: E402
from nicmanager.system.applier import ProfileApplier  # noqa: E402


class TestProfileValidation(unittest.TestCase):
    def test_static_valid(self):
        p = Profile(adapter_name="以太网", name="A", mode="static", ip="192.168.1.5", prefix=24,
                    gateway="192.168.1.1", dns1="223.5.5.5", dns2="119.29.29.29")
        self.assertEqual(p.validate(), [])

    def test_static_invalid_ip(self):
        p = Profile(adapter_name="以太网", name="A", mode="static", ip="999.1.1.1", prefix=24)
        self.assertTrue(p.validate())

    def test_static_bad_prefix(self):
        p = Profile(adapter_name="以太网", name="A", mode="static", ip="1.1.1.1", prefix=99)
        self.assertTrue(p.validate())

    def test_dhcp_ignores_static_fields(self):
        p = Profile(adapter_name="WLAN", name="B", mode="dhcp", ip="bad", prefix=99)
        self.assertEqual(p.validate(), [])

    def test_missing_name(self):
        p = Profile(adapter_name="以太网", name="", mode="static", ip="1.1.1.1", prefix=24)
        self.assertTrue(p.validate())

    def test_same_dns_rejected(self):
        p = Profile(adapter_name="以太网", name="A", mode="static", ip="1.1.1.1", prefix=24,
                    dns1="8.8.8.8", dns2="8.8.8.8")
        self.assertTrue(p.validate())

    def test_summary(self):
        p = Profile(adapter_name="WLAN", name="家", mode="dhcp")
        self.assertEqual(p.summary(), "DHCP 自动获取")
        p2 = Profile(adapter_name="WLAN", name="办", mode="static", ip="10.0.0.9", prefix=24)
        self.assertEqual(p2.summary(), "静态 10.0.0.9/24")


class TestCommandBuild(unittest.TestCase):
    def setUp(self):
        self.adapter = AdapterInfo(index=10, name="以太网")

    def test_static_cmds(self):
        p = Profile(adapter_name="以太网", name="A", mode="static", ip="192.168.1.5", prefix=24,
                    gateway="192.168.1.1", dns1="223.5.5.5")
        applier = ProfileApplier()
        cmds = applier._build_commands(self.adapter, p)  # noqa: SLF001
        joined = "\n".join(cmds)
        self.assertIn("-Dhcp Disabled", joined)
        self.assertIn("-IPAddress 192.168.1.5", joined)
        self.assertIn("-PrefixLength 24", joined)
        self.assertIn("-DefaultGateway 192.168.1.1", joined)
        self.assertIn("Set-DnsClientServerAddress", joined)
        self.assertIn("223.5.5.5", joined)

    def test_dhcp_cmds(self):
        p = Profile(adapter_name="WLAN", name="B", mode="dhcp")
        applier = ProfileApplier()
        cmds = applier._build_commands(self.adapter, p)  # noqa: SLF001
        joined = "\n".join(cmds)
        self.assertIn("-Dhcp Enabled", joined)
        self.assertIn("-ResetServerAddresses", joined)

    def test_dry_run_no_side_effect(self):
        p = Profile(adapter_name="以太网", name="A", mode="static", ip="192.168.1.5", prefix=24)
        applier = ProfileApplier(dry_run=True)
        res = applier.apply(self.adapter, p)
        self.assertTrue(res.ok)
        self.assertIn("DRY-RUN", res.message)
        self.assertTrue(res.steps)


if __name__ == "__main__":
    unittest.main()
