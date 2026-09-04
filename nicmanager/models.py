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


@dataclass
class Profile:
    """一块网卡上保存的某一套配置档案。"""

    adapter_name: str          # 绑定网卡名（与 AdapterInfo.name 一致）
    name: str                  # 档案名称，如"办公室-静态IP"
    mode: str = "static"       # 'static' | 'dhcp'
    ip: str = ""               # 静态 IPv4
    prefix: int = 24           # 前缀长度
    gateway: str = ""          # 默认网关
    dns1: str = ""             # 首选 DNS
    dns2: str = ""             # 备用 DNS
    note: str = ""             # 备注
    id: Optional[int] = None   # 数据库主键
    created_at: str = ""       # ISO 时间
    updated_at: str = ""

    def validate(self) -> List[str]:
        """校验档案字段，返回错误列表（空列表=合法）。"""
        errors: List[str] = []
        if not self.adapter_name.strip():
            errors.append("绑定网卡不能为空")
        if not self.name.strip():
            errors.append("档案名称不能为空")
        if self.mode == "static":
            from nicmanager.iputil import is_valid_ipv4, is_valid_mask, prefix_to_mask
            if not is_valid_ipv4(self.ip):
                errors.append("IP 地址不合法")
            if self.prefix is None or not (0 <= self.prefix <= 32):
                errors.append("子网前缀长度必须为 0-32")
            if self.gateway and not is_valid_ipv4(self.gateway):
                errors.append("网关地址不合法")
            if self.dns1 and not is_valid_ipv4(self.dns1):
                errors.append("首选 DNS 不合法")
            if self.dns2 and not is_valid_ipv4(self.dns2):
                errors.append("备用 DNS 不合法")
            if self.dns1 == self.dns2 and self.dns1:
                errors.append("首选与备用 DNS 不能相同")
            # 掩码覆盖检查：网关/主机不在网段内仅提示性，不强制
            if prefix_to_mask(self.prefix) is None:
                errors.append("子网掩码非法")
        else:
            if self.ip or self.gateway or self.dns1 or self.dns2:
                pass  # DHCP 模式下填写的静态字段将被忽略，不报错
        return errors

    def summary(self) -> str:
        if self.mode == "dhcp":
            return "DHCP 自动获取"
        return f"静态 {self.ip}/{self.prefix}" + (f"  网关 {self.gateway}" if self.gateway else "")


def now_iso() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
