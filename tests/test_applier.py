import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from nicmanager.models import AdapterInfo, Profile  # noqa: E402
from nicmanager.system.applier import ProfileApplier  # noqa: E402


class TestVerify(unittest.TestCase):
    """校验逻辑单测：通过 mock 读取结果验证比对正确性（不真改系统）。"""

    def _verify_with(self, adapter_info, profile):
        """在 mock 上下文中执行 _verify（patch 需与调用同生命周期）。"""
        from unittest import mock
        with mock.patch("nicmanager.system.applier.time.sleep"):  # 跳过延迟
            with mock.patch("nicmanager.system.reader.read_adapters",
                            return_value=([adapter_info], "mock")):
                return ProfileApplier()._verify(adapter_info, profile)

    def test_static_all_match(self):
        a = AdapterInfo(index=10, name="以太网", dhcp_enabled=False,
                        ipv4=["10.0.0.5/24"], gateways=["10.0.0.1"],
                        dns_servers=["223.5.5.5"])
        p = Profile(adapter_name="以太网", name="A", mode="static",
                    ip="10.0.0.5", prefix=24, gateway="10.0.0.1", dns1="223.5.5.5")
        res = self._verify_with(a, p)
        self.assertTrue(res.ok, res.detail)

    def test_static_multi_ip_match(self):
        a = AdapterInfo(index=10, name="以太网", dhcp_enabled=False,
                        ipv4=["10.0.0.5/24", "192.168.1.9/24"],
                        gateways=["10.0.0.1"], dns_servers=[])
        p = Profile(adapter_name="以太网", name="A", mode="static",
                    ip="10.0.0.5", prefix=24, extra_ips=["192.168.1.9/24"],
                    gateway="10.0.0.1")
        res = self._verify_with(a, p)
        self.assertTrue(res.ok, res.detail)

    def test_static_missing_addr_fails(self):
        a = AdapterInfo(index=10, name="以太网", dhcp_enabled=False,
                        ipv4=["10.0.0.5/24"], gateways=["10.0.0.1"], dns_servers=[])
        p = Profile(adapter_name="以太网", name="A", mode="static",
                    ip="10.9.9.9", prefix=24, gateway="10.0.0.1")
        res = self._verify_with(a, p)
        self.assertFalse(res.ok)
        self.assertIn("未生效", res.detail)

    def test_dhcp_match(self):
        a = AdapterInfo(index=2, name="WLAN", dhcp_enabled=True, ipv4=[], gateways=[], dns_servers=[])
        p = Profile(adapter_name="WLAN", name="B", mode="dhcp")
        res = self._verify_with(a, p)
        self.assertTrue(res.ok, res.detail)

    def test_gateway_missing_fails(self):
        a = AdapterInfo(index=10, name="以太网", dhcp_enabled=False,
                        ipv4=["10.0.0.5/24"], gateways=[], dns_servers=[])
        p = Profile(adapter_name="以太网", name="A", mode="static",
                    ip="10.0.0.5", prefix=24, gateway="10.0.0.1")
        res = self._verify_with(a, p)
        self.assertFalse(res.ok)
        self.assertIn("网关", res.detail)




class TestToProfile(unittest.TestCase):
    def test_static_current_to_profile(self):
        a = AdapterInfo(index=10, name="以太网", dhcp_enabled=False,
                        ipv4=["10.10.100.24/24", "192.168.1.5/24"],
                        gateways=["10.10.100.1"], dns_servers=["114.114.114.114", "8.8.8.8"])
        p = a.to_profile()
        self.assertEqual(p.mode, "static")
        self.assertEqual(p.ip, "10.10.100.24")
        self.assertEqual(p.prefix, 24)
        self.assertEqual(p.extra_ips, ["192.168.1.5/24"])
        self.assertEqual(p.gateway, "10.10.100.1")
        self.assertEqual(p.dns1, "114.114.114.114")
        self.assertEqual(p.dns2, "8.8.8.8")

    def test_dhcp_current_to_profile(self):
        a = AdapterInfo(index=2, name="WLAN", dhcp_enabled=True,
                        ipv4=["10.100.128.192/21"], gateways=["10.100.128.1"],
                        dns_servers=["172.17.0.13"])
        p = a.to_profile()
        self.assertEqual(p.mode, "dhcp")
        # DHCP 下忽略静态值（虽然存在当前地址）
        self.assertEqual(p.ip, "")
        self.assertEqual(p.extra_ips, [])

    def test_linklocal_filtered(self):
        a = AdapterInfo(index=10, name="以太网", dhcp_enabled=False,
                        ipv4=["169.254.10.5/16", "10.0.0.8/24"])
        p = a.to_profile()
        self.assertEqual(p.ip, "10.0.0.8")
        self.assertEqual(p.extra_ips, [])

    def test_no_addresses(self):
        a = AdapterInfo(index=10, name="以太网", dhcp_enabled=False, ipv4=[])
        p = a.to_profile()
        self.assertEqual(p.mode, "static")
        self.assertEqual(p.ip, "")
        # 无地址且未命名 → 校验会提示缺名称与缺主 IP
        errors = p.validate()
        self.assertTrue(any("名称" in e for e in errors))
        self.assertTrue(any("主 IP" in e for e in errors))



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

    def test_extra_ips_valid(self):
        p = Profile(adapter_name="以太网", name="多IP", mode="static", ip="192.168.1.5", prefix=24,
                    extra_ips=["10.0.0.9/24", "172.16.1.1/16"])
        self.assertEqual(p.validate(), [])

    def test_extra_ips_duplicate_rejected(self):
        p = Profile(adapter_name="以太网", name="多IP", mode="static", ip="192.168.1.5", prefix=24,
                    extra_ips=["192.168.1.5/24"])
        self.assertTrue(p.validate())

    def test_extra_ips_bad_format(self):
        p = Profile(adapter_name="以太网", name="多IP", mode="static", ip="192.168.1.5", prefix=24,
                    extra_ips=["not-an-ip", "9.9.9.9/99"])
        errors = p.validate()
        self.assertTrue(any("格式" in e or "不合法" in e for e in errors), errors)

    def test_extra_ips_self_duplicate_rejected(self):
        p = Profile(adapter_name="以太网", name="多IP", mode="static", ip="192.168.1.5", prefix=24,
                    extra_ips=["10.0.0.9/24", "10.0.0.9/24"])
        self.assertTrue(p.validate())

    def test_all_addresses_order(self):
        p = Profile(adapter_name="以太网", name="多IP", mode="static", ip="192.168.1.5", prefix=24,
                    extra_ips=["10.0.0.9/24"])
        addrs = p.all_addresses()
        self.assertEqual(addrs, [{"ip": "192.168.1.5", "prefix": 24}, {"ip": "10.0.0.9", "prefix": 24}])

    def test_summary_with_extra(self):
        p = Profile(adapter_name="以太网", name="多IP", mode="static", ip="192.168.1.5", prefix=24,
                    extra_ips=["10.0.0.9/24"])
        self.assertIn("192.168.1.5/24", p.summary())
        self.assertIn("10.0.0.9/24", p.summary())


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
        self.assertIn("New-NetIPAddress -InterfaceIndex 10 -IPAddress 192.168.1.5 -PrefixLength 24", joined)
        # 网关改为独立 New-NetRoute（修复 DefaultGateway already exists）
        self.assertIn("New-NetRoute -DestinationPrefix '0.0.0.0/0' -InterfaceIndex 10 -NextHop 192.168.1.1", joined)
        # 先清残留默认路由，避免 already exists
        self.assertIn("Get-NetRoute -InterfaceIndex 10 -DestinationPrefix '0.0.0.0/0'", joined)
        self.assertNotIn("-DefaultGateway", joined)
        self.assertIn("Set-DnsClientServerAddress", joined)
        self.assertIn("223.5.5.5", joined)

    def test_static_multi_ip_cmds(self):
        p = Profile(adapter_name="以太网", name="多IP", mode="static", ip="192.168.1.5", prefix=24,
                    extra_ips=["10.0.0.9/24", "172.16.1.1/16"],
                    gateway="192.168.1.1", dns1="223.5.5.5")
        applier = ProfileApplier()
        cmds = applier._build_commands(self.adapter, p)  # noqa: SLF001
        joined = "\n".join(cmds)
        # 主地址/附加地址各一条 New-NetIPAddress（网关不再绑在建址命令上）
        self.assertIn("New-NetIPAddress -InterfaceIndex 10 -IPAddress 192.168.1.5 -PrefixLength 24", joined)
        self.assertIn("New-NetIPAddress -InterfaceIndex 10 -IPAddress 10.0.0.9 -PrefixLength 24", joined)
        self.assertIn("New-NetIPAddress -InterfaceIndex 10 -IPAddress 172.16.1.1 -PrefixLength 16", joined)
        self.assertIn("New-NetRoute -DestinationPrefix '0.0.0.0/0' -InterfaceIndex 10 -NextHop 192.168.1.1", joined)
        self.assertIn("Set-DnsClientServerAddress", joined)
        self.assertEqual(joined.count("New-NetIPAddress"), 3)
        self.assertNotIn("-DefaultGateway", joined)

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
