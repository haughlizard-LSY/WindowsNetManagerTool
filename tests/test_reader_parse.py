import os
import unittest

from nicmanager.system import reader


def _load(name):
    path = os.path.join(os.path.dirname(__file__), "fixtures", name)
    with open(path, encoding="utf-8") as f:
        return f.read()


class TestInterfaceTable(unittest.TestCase):
    def test_parse_interfaces_table(self):
        rows = reader._list_interfaces_netsh()  # noqa: SLF001
        self.assertTrue(rows, "无网卡")
        names = {r["name"] for r in rows}
        self.assertIn("WLAN", names)
        self.assertIn("以太网", names)
        for r in rows:
            self.assertGreater(r["index"], 0)


class TestConfigBlocks(unittest.TestCase):
    def test_split_config_blocks_zh_header(self):
        text = _load("netsh_show_dnsservers.txt")
        blocks = reader._split_config_blocks(text)
        self.assertIn("WLAN", blocks)
        self.assertIn("以太网", blocks)

    def test_split_config_blocks_en_header(self):
        text = _load("netsh_show_config.txt")
        blocks = reader._split_config_blocks(text)
        self.assertIn("WLAN", blocks)
        self.assertIn("以太网", blocks)

    def test_parse_static_block(self):
        text = _load("netsh_show_config.txt")
        blocks = reader._split_config_blocks(text)
        detail = reader._parse_config_block(blocks["以太网"])
        self.assertIs(detail["dhcp"], False)
        self.assertTrue(any(ip.startswith("10.10.100.") for ip in detail["ipv4"]), detail)
        self.assertIn("10.10.100.1", detail["gateways"])
        self.assertEqual(detail["dns"], [])

    def test_parse_dhcp_block_wlan(self):
        text = _load("netsh_show_config.txt")
        blocks = reader._split_config_blocks(text)
        detail = reader._parse_config_block(blocks["WLAN"])
        self.assertIs(detail["dhcp"], True)
        self.assertTrue(any(ip.startswith("10.100.128.") for ip in detail["ipv4"]), detail["ipv4"])
        self.assertIn("10.100.128.1", detail["gateways"])
        self.assertIn("172.17.0.13", detail["dns"])
        self.assertIn("172.17.0.14", detail["dns"])

    def test_cidr_pairs_ip_with_prefix(self):
        text = _load("netsh_show_config.txt")
        blocks = reader._split_config_blocks(text)
        detail = reader._parse_config_block(blocks["以太网 3"])
        ips = detail["ipv4"]
        self.assertGreaterEqual(len(ips), 3, ips)
        self.assertTrue(all(x.endswith("/24") for x in ips), ips)


if __name__ == "__main__":
    unittest.main()
