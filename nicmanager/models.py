"""数据模型：网卡信息与网卡配置档案（Profile）。"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional


@dataclass
class AdapterInfo:
    """网卡及其当前生效配置的只读快照。"""

    index: int                     # InterfaceIndex（系统接口索引）
    name: str                      # 网卡名（InterfaceAlias / netsh 显示名）
    description: str = ""          # 网卡描述（型号）
    status: str = ""               # 连接状态: connected / disconnected / disabled
    mac: str = ""                  # MAC 地址
    is_virtual: bool = False       # 是否虚拟网卡（尽力判断）
    dhcp_enabled: Optional[bool] = None   # 当前 IPv4 是否 DHCP
    ipv4: List[str] = field(default_factory=list)      # 当前 IPv4 地址列表 (CIDR)
    gateways: List[str] = field(default_factory=list)  # 默认网关列表
    dns_servers: List[str] = field(default_factory=list)  # DNS 服务器列表
    ipv6_link_local: str = ""      # 链路本地 IPv6（展示用）
    is_current_admin: bool = False # 读取时是否管理员权限

    @property
    def status_label(self) -> str:
        mapping = {
            "connected": "已连接",
            "disconnected": "已断开",
            "disabled": "已禁用",
            "media disconnected": "电缆已断开",
            "up": "已连接",
            "down": "已断开",
        }
        return mapping.get(self.status.lower(), self.status or "未知")

    @property
    def ipv4_label(self) -> str:
        return "、".join(self.ipv4) if self.ipv4 else "—"

    @property
    def gateway_label(self) -> str:
        return "、".join(self.gateways) if self.gateways else "—"

    @property
    def dns_label(self) -> str:
        return "、".join(self.dns_servers) if self.dns_servers else "—"

    def to_profile(self) -> "Profile":
        """把网卡当前生效配置转成 Profile（供"保存当前配置为档案"）。

        - DHCP 开启 → mode=dhcp（静态字段忽略）
        - 静态     → 主 IP = 第一个地址，其余 IPv4 作为附加地址；
                     网关/DNS 依当前值预填。
        """
        from nicmanager.models import Profile, split_cidr

        p = Profile(
            adapter_name=self.name,
            name="",  # 名称由用户在对话框中填写
            mode="dhcp" if self.dhcp_enabled is True else "static",
            ip="",
            prefix=24,
            extra_ips=[],
        )
        if self.dhcp_enabled is True:
            return p
        # 静态模式：解析当前地址（过滤链路本地 169.254/回环 127 等非真实配置）
        addrs = []
        for cidr in self.ipv4:
            ip, prefix = split_cidr(cidr)
            if not ip or ip.startswith("169.254.") or ip.startswith("127."):
                continue
            addrs.append((ip, prefix or 24))
        if addrs:
            p.ip, p.prefix = addrs[0]
            p.extra_ips = [f"{ip}/{pre}" for ip, pre in addrs[1:]]
        if self.gateways:
            p.gateway = self.gateways[0]
        if self.dns_servers:
            p.dns1 = self.dns_servers[0]
        if len(self.dns_servers) > 1:
            p.dns2 = self.dns_servers[1]
        return p


@dataclass
class Profile:
    """一块网卡上保存的某一套配置档案。"""

    adapter_name: str          # 绑定网卡名（与 AdapterInfo.name 一致）
    name: str                  # 档案名称，如"办公室-静态IP"
    mode: str = "static"       # 'static' | 'dhcp'
    ip: str = ""               # 静态 IPv4（主地址）
    prefix: int = 24           # 主地址前缀长度
    extra_ips: list = field(default_factory=list)  # 附加静态 IP，元素为 "ip/prefix" 字符串
    gateway: str = ""          # 默认网关
    dns1: str = ""             # 首选 DNS
    dns2: str = ""             # 备用 DNS
    note: str = ""             # 备注
    id: Optional[int] = None   # 数据库主键
    created_at: str = ""       # ISO 时间
    updated_at: str = ""

    # ------------------------------------------------------------ 地址工具
    def all_addresses(self) -> list:
        """返回所有静态地址，元素为 dict {ip, prefix}。主地址在前。"""
        addrs = [{"ip": self.ip, "prefix": self.prefix}]
        for cidr in self.extra_ips:
            ip, prefix = split_cidr(cidr)
            if ip:
                addrs.append({"ip": ip, "prefix": prefix})
        return addrs

    def primary_cidr(self) -> str:
        return f"{self.ip}/{self.prefix}"

    def validate(self) -> List[str]:
        """校验档案字段，返回错误列表（空列表=合法）。"""
        errors: List[str] = []
        if not self.adapter_name.strip():
            errors.append("绑定网卡不能为空")
        if not self.name.strip():
            errors.append("档案名称不能为空")
        if self.mode == "static":
            from nicmanager.iputil import is_valid_ipv4, prefix_to_mask
            if not is_valid_ipv4(self.ip):
                errors.append("主 IP 地址不合法")
            if self.prefix is None or not (0 <= self.prefix <= 32):
                errors.append("主地址子网前缀长度必须为 0-32")
            # 附加地址逐个校验
            seen = {self.ip}
            for cidr in self.extra_ips:
                ip, prefix = split_cidr(cidr)
                if not ip:
                    errors.append(f"附加 IP「{cidr}」格式应为 ip/前缀，如 192.168.1.2/24")
                    continue
                if not is_valid_ipv4(ip):
                    errors.append(f"附加 IP「{ip}」不合法")
                if not (0 <= prefix <= 32):
                    errors.append(f"附加 IP「{cidr}」前缀长度必须为 0-32")
                if ip in seen:
                    errors.append(f"IP「{ip}」重复（主地址与附加地址不能重复）")
                seen.add(ip)
            if self.gateway and not is_valid_ipv4(self.gateway):
                errors.append("网关地址不合法")
            if self.dns1 and not is_valid_ipv4(self.dns1):
                errors.append("首选 DNS 不合法")
            if self.dns2 and not is_valid_ipv4(self.dns2):
                errors.append("备用 DNS 不合法")
            if self.dns1 == self.dns2 and self.dns1:
                errors.append("首选与备用 DNS 不能相同")
            if prefix_to_mask(self.prefix) is None:
                errors.append("子网掩码非法")
        else:
            if self.ip or self.gateway or self.dns1 or self.dns2:
                pass  # DHCP 模式下填写的静态字段将被忽略，不报错
        return errors

    def summary(self) -> str:
        if self.mode == "dhcp":
            return "DHCP 自动获取"
        parts = [self.primary_cidr()]
        for cidr in self.extra_ips:
            parts.append(cidr)
        text = "静态 " + "、".join(parts)
        if self.gateway:
            text += f"  网关 {self.gateway}"
        return text


def split_cidr(cidr: str):
    """把 '192.168.1.2/24' 拆成 (ip, prefix)；非法返回 (None, None)。"""
    from nicmanager.iputil import parse_cidr
    return parse_cidr(cidr) or (None, None)


def now_iso() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
