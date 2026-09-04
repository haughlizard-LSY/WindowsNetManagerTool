"""网卡与当前配置读取层。

双通道设计：
- PowerShell JSON（主通道）：结构化输出，字段齐全（含 MAC/描述/DHCP 状态），
  真实机器上普通管理员权限即可运行；
- netsh 文本（降级通道）：适用于 CIM 不可用/受限环境，信息较少（无 MAC/描述）。
"""
from __future__ import annotations

import json
import re
from typing import List, Optional, Tuple

from nicmanager.models import AdapterInfo
from nicmanager.system import proc as p

# ---------------------------------------------------------------- PowerShell 主通道

_PS_QUERY = r"""
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$ErrorActionPreference = 'SilentlyContinue'
$rows = @()
foreach ($a in (Get-NetAdapter | Sort-Object ifIndex)) {
    $idx = $a.ifIndex
    $dhcp = $null
    $iface = Get-NetIPInterface -InterfaceIndex $idx -AddressFamily IPv4 -ErrorAction SilentlyContinue
    if ($iface) { $dhcp = [bool]$iface.Dhcp }
    $addrs = @(Get-NetIPAddress -InterfaceIndex $idx -AddressFamily IPv4 -ErrorAction SilentlyContinue)
    $ipv4 = @()
    $ll = ''
    foreach ($ad in $addrs) {
        $isLl = ($ad.IPAddress -like 'fe80:*')
        if ($isLl) { $ll = $ad.IPAddress; continue }
        $ipv4 += ("{0}/{1}" -f $ad.IPAddress, $ad.PrefixLength)
    }
    $gw = @()
    $cfg = Get-NetIPConfiguration -InterfaceIndex $idx -ErrorAction SilentlyContinue
    if ($cfg.IPv4DefaultGateway) { foreach ($g in $cfg.IPv4DefaultGateway) { $gw += $g.NextHop } }
    $dns = @()
    $dnsAd = Get-DnsClientServerAddress -InterfaceIndex $idx -AddressFamily IPv4 -ErrorAction SilentlyContinue
    if ($dnsAd) { foreach ($d in $dnsAd.ServerAddresses) { if ($d -notin $dns) { $dns += $d } } }
    $rows += [pscustomobject]@{
        index       = $idx
        name        = $a.Name
        description = $a.InterfaceDescription
        status      = $a.Status
        mac         = $a.MacAddress
        virtual     = [bool]$a.Virtual
        dhcp        = $dhcp
        ipv4        = $ipv4
        ipv6ll      = $ll
        gateways    = @($gw)
        dns         = @($dns)
    }
}
ConvertTo-Json -InputObject @($rows) -Depth 4 -Compress
"""


def _parse_ps_adapters(text: str) -> List[AdapterInfo]:
    data = json.loads(text)
    if not isinstance(data, list):
        data = [data]
    adapters: List[AdapterInfo] = []
    for d in data:
        if not isinstance(d, dict):
            continue
        adapters.append(
            AdapterInfo(
                index=int(d.get("index") or 0),
                name=str(d.get("name") or ""),
                description=str(d.get("description") or ""),
                status=str(d.get("status") or ""),
                mac=str(d.get("mac") or ""),
                is_virtual=bool(d.get("virtual")),
                dhcp_enabled=d.get("dhcp"),
                ipv4=[str(x) for x in (d.get("ipv4") or []) if x],
                ipv6_link_local=str(d.get("ipv6ll") or ""),
                gateways=[str(x) for x in (d.get("gateways") or []) if x],
                dns_servers=[str(x) for x in (d.get("dns") or []) if x],
            )
        )
    return adapters


# ---------------------------------------------------------------- netsh 降级通道

# 网卡索引表：Idx Met MTU State Name（列名英文，跨语言稳定）
_INTERFACE_LINE = re.compile(r"^\s*(\d+)\s+\d+\s+\d+\s+(\S+)\s+(.+?)\s*$")
# show config 接口块头（英文或中文）
_CONFIG_HEADER_EN = re.compile(r'^Configuration for interface\s+"(.+)"')
_CONFIG_HEADER_ZH = re.compile(r'^接口\s*"(.+)"\s*的配置')
# DHCP 状态行：DHCP enabled: Yes / DHCP 已启用: 是
_DHCP_LINE = re.compile(r"DHCP\s+enabled\s*:\s*(Yes|No)", re.IGNORECASE)
_DHCP_LINE_ZH = re.compile(r"DHCP\s+已启用\s*:\s*(是|否)")
# IP Address / Subnet Prefix / Default Gateway（值段英文标签，相对稳定）
_IP_LINE = re.compile(r"IP\s+Address\s*:\s*([0-9.]+)")
_PREFIX_LINE = re.compile(r"Subnet\s+Prefix\s*:\s*([0-9.]+)/(\d+)\s*\(mask\s*([0-9.]+)\)")
_GW_LINE = re.compile(r"Default\s+Gateway\s*:\s*([0-9.]+)")
_IPV4_TOKEN = re.compile(r"\b(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})\b")
_DNS_HEAD = re.compile(r"(DNS\s+servers|DNS\s+服务器)\s*:", re.IGNORECASE)


def _split_config_blocks(text: str) -> dict:
    """把 show config 全文拆成 {interface_name: [lines]}。"""
    blocks: dict = {}
    cur_name: Optional[str] = None
    buf: List[str] = []
    for raw in text.splitlines():
        line = raw.strip()
        m = _CONFIG_HEADER_EN.match(line) or _CONFIG_HEADER_ZH.match(line)
        if m:
            if cur_name is not None:
                blocks[cur_name] = buf
            cur_name = m.group(1)
            buf = []
        elif cur_name is not None:
            buf.append(line)
    if cur_name is not None:
        blocks[cur_name] = buf
    return blocks


def _parse_config_block(lines: List[str]) -> dict:
    """从单个接口的 config 行中解析 {dhcp, ipv4(CIDR), gateways, dns}。"""
    out = {"dhcp": None, "ipv4": [], "gateways": [], "dns": []}
    cur_ip: Optional[str] = None

    def commit(fallback_prefix: Optional[str]):
        """把挂起的 IP 落盘（无后续 prefix 时用 fallback）。"""
        nonlocal cur_ip
        if cur_ip is not None:
            out["ipv4"].append(f"{cur_ip}/{fallback_prefix}" if fallback_prefix else f"{cur_ip}/32")
            cur_ip = None

    for line in lines:
        m = _DHCP_LINE.search(line) or _DHCP_LINE_ZH.search(line)
        if m:
            out["dhcp"] = (m.group(1).lower() in ("yes", "是"))
            continue
        m = _IP_LINE.search(line)
        if m:
            commit(None)  # 前一个 IP 没有等到 prefix
            cur_ip = m.group(1)
            continue
        m = _PREFIX_LINE.search(line)
        if m and cur_ip:
            # prefix 行含网络号与掩码；IP 用实际主机地址，前缀长度取自 prefix 行
            out["ipv4"].append(f"{cur_ip}/{m.group(2)}")
            cur_ip = None
            continue
        m = _GW_LINE.search(line)
        if m:
            out["gateways"].append(m.group(1))
    commit(None)
    # DNS 区域：DNS 头行可能同行带 IP（如"…DNS 服务器: 172.17.0.13"），
    # 也可能值在后续缩进行；跟随头之后的独立 IPv4 行也计入。
    dns_started = False
    for line in lines:
        if _DNS_HEAD.search(line):
            dns_started = True
            m = _IPV4_TOKEN.search(line)
            if m:
                out["dns"].append(m.group(1))
            continue
        if dns_started:
            if re.search(r"register|注册", line, re.IGNORECASE) and ":" not in line:
                break
            m = _IPV4_TOKEN.search(line)
            if m and _IP_LINE.search(line) is None and _GW_LINE.search(line) is None:
                out["dns"].append(m.group(1))
    return out


def _list_interfaces_netsh() -> List[dict]:
    """netsh interface ipv4 show interfaces -> [{index,state,name}]"""
    rc, out, err = p.run_netsh(["interface", "ipv4", "show", "interfaces"])
    rows = []
    if rc != 0:
        return rows
    for line in out.splitlines():
        if not line.strip() or line.strip().startswith("---") or "Idx" in line:
            continue
        m = _INTERFACE_LINE.match(line.rstrip())
        if m:
            rows.append({"index": int(m.group(1)), "state": m.group(2), "name": m.group(3).strip()})
    return rows


def read_adapters_netsh() -> List[AdapterInfo]:
    """降级读取：netsh 枚举 + 每接口 show config。"""
    interfaces = _list_interfaces_netsh()
    adapters: List[AdapterInfo] = []
    for itf in interfaces:
        name = itf["name"]
        rc, out, err = p.run_netsh(["interface", "ipv4", "show", "config", "name=" + name])
        detail = {"dhcp": None, "ipv4": [], "gateways": [], "dns": []}
        if rc == 0:
            blocks = _split_config_blocks(out)
            if name in blocks:
                detail = _parse_config_block(blocks[name])
            elif blocks:
                # 名字匹配失败时取唯一块兜底
                if len(blocks) == 1:
                    detail = _parse_config_block(next(iter(blocks.values())))
        adapters.append(
            AdapterInfo(
                index=itf["index"],
                name=name,
                description="",
                status="connected" if itf["state"].lower() == "connected" else "disconnected",
                mac="",
                dhcp_enabled=detail["dhcp"],
                ipv4=detail["ipv4"],   # 已是 CIDR（ip/前缀）
                gateways=detail["gateways"],
                dns_servers=detail["dns"],
                is_current_admin=False,
            )
        )
    return adapters


def read_adapters() -> Tuple[List[AdapterInfo], str]:
    """返回 (适配器列表, 使用的通道名 'powershell' | 'netsh')。先 PS，失败降级。"""
    try:
        rc, out, err = p.run_powershell_script(_PS_QUERY, timeout=30.0)
        if rc == 0 and out.strip():
            parsed = _parse_ps_adapters(out)
            if parsed:
                return parsed, "powershell"
    except Exception:
        pass
    return read_adapters_netsh(), "netsh"
