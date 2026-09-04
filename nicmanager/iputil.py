"""IPv4 地址/掩码/前缀的校验与转换工具。"""
from __future__ import annotations

import ipaddress
import re
from typing import Optional

IPV4_RE = re.compile(r"^\d{1,3}(\.\d{1,3}){3}$")


def is_valid_ipv4(text: str) -> bool:
    """判断是否为合法的点分 IPv4 地址。"""
    if not text or not IPV4_RE.match(text.strip()):
        return False
    try:
        ipaddress.IPv4Address(text.strip())
        return True
    except ipaddress.AddressValueError:
        return False


def is_valid_mask(text: str) -> bool:
    """判断是否为合法的子网掩码（如 255.255.255.0）。"""
    if not text or not IPV4_RE.match(text.strip()):
        return False
    try:
        ip = ipaddress.IPv4Address(text.strip())
    except ipaddress.AddressValueError:
        return False
    # 掩码必须连续为 1：255.255.255.0 -> 11111111... 00000000
    n = int(ip)
    inv = (~n) & 0xFFFFFFFF
    return (inv & (inv + 1)) == 0


def mask_to_prefix(mask: str) -> Optional[int]:
    """把掩码字符串转成前缀长度，非法返回 None。"""
    if not is_valid_mask(mask):
        return None
    return bin(int(ipaddress.IPv4Address(mask))).count("1")


def prefix_to_mask(prefix: int) -> Optional[str]:
    """把前缀长度(0-32)转成掩码字符串。"""
    if not isinstance(prefix, int) or not (0 <= prefix <= 32):
        return None
    n = (0xFFFFFFFF << (32 - prefix)) & 0xFFFFFFFF if prefix else 0
    return str(ipaddress.IPv4Address(n))


def parse_cidr(text: str):
    """解析 '192.168.1.10/24' 或 '192.168.1.10/255.255.255.0'，返回 (ip, prefix)。非法返回 None。"""
    if not text:
        return None
    text = text.strip()
    if "/" not in text:
        return None
    ip_part, _, pre_part = text.partition("/")
    if not is_valid_ipv4(ip_part):
        return None
    if is_valid_mask(pre_part):
        prefix = mask_to_prefix(pre_part)
    elif pre_part.isdigit():
        prefix = int(pre_part)
        if not (0 <= prefix <= 32):
            return None
    else:
        return None
    return ip_part, prefix


def format_prefix(ip: str, prefix: int) -> str:
    """生成 CIDR 表示。"""
    return f"{ip}/{prefix}"


def normalize_address_list(values) -> list[str]:
    """把 DNS 等可能为 str/list 的取值归一为 list[str]，过滤非法 IPv4。"""
    if values is None:
        return []
    if isinstance(values, str):
        values = [values]
    out = []
    for v in values:
        v = str(v).strip()
        if is_valid_ipv4(v) and v not in out:
            out.append(v)
    return out
