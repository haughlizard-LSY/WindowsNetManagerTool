import os
import unittest

from nicmanager.iputil import (
    is_valid_ipv4,
    is_valid_mask,
    mask_to_prefix,
    parse_cidr,
    prefix_to_mask,
)


class TestIpUtil(unittest.TestCase):
    def test_ipv4_valid(self):
        self.assertTrue(is_valid_ipv4("192.168.1.1"))
        self.assertTrue(is_valid_ipv4("10.0.0.1"))
        self.assertFalse(is_valid_ipv4("256.1.1.1"))
        self.assertFalse(is_valid_ipv4("abc"))
        self.assertFalse(is_valid_ipv4("1.2.3"))
        self.assertFalse(is_valid_ipv4(""))

    def test_mask_valid(self):
        self.assertTrue(is_valid_mask("255.255.255.0"))
        self.assertTrue(is_valid_mask("255.255.0.0"))
        self.assertTrue(is_valid_mask("0.0.0.0"))
        self.assertFalse(is_valid_mask("255.0.255.0"))
        self.assertFalse(is_valid_mask("192.168.1.1"))

    def test_mask_prefix_roundtrip(self):
        self.assertEqual(mask_to_prefix("255.255.255.0"), 24)
        self.assertEqual(mask_to_prefix("255.255.0.0"), 16)
        self.assertEqual(mask_to_prefix("255.0.0.0"), 8)
        self.assertEqual(mask_to_prefix("255.255.255.255"), 32)
        self.assertIsNone(mask_to_prefix("192.168.1.1"))
        for p in (0, 8, 16, 24, 32):
            self.assertEqual(mask_to_prefix(prefix_to_mask(p)), p)

    def test_parse_cidr(self):
        self.assertEqual(parse_cidr("192.168.1.10/24"), ("192.168.1.10", 24))
        self.assertEqual(parse_cidr("10.0.0.5/255.255.255.0"), ("10.0.0.5", 24))
        self.assertIsNone(parse_cidr("x/24"))
        self.assertIsNone(parse_cidr("1.2.3.4/33"))
        self.assertIsNone(parse_cidr("1.2.3.4"))


if __name__ == "__main__":
    unittest.main()
