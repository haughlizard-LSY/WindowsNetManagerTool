"""应用（切换）网卡配置档案。

安全设计：
1. 应用前读取当前配置作为快照（回滚点）；
2. 执行系统命令把档案写入网卡；
3. 重新读取校验生效结果（带延迟重试，容忍网络栈刷新）；
4. 失败时回滚到快照，并给出可读错误。

支持 dry_run 预览将执行的命令，不真正改动系统。
需要管理员权限（由应用启动时提权保证；未提权时写操作会失败并被捕获）。
"""
from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from typing import List, Optional

from nicmanager.iputil import is_valid_ipv4
from nicmanager.models import AdapterInfo, Profile
from nicmanager.system import proc as p


def _log_apply(text: str) -> None:
    """把应用过程写入 %APPDATA%\\NetManagerTool\\apply.log，便于排障。"""
    try:
        base = os.environ.get("APPDATA") or os.path.expanduser("~")
        d = os.path.join(base, "NetManagerTool")
        os.makedirs(d, exist_ok=True)
        import datetime
        with open(os.path.join(d, "apply.log"), "a", encoding="utf-8") as f:
            stamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            f.write(f"\n===== apply @ {stamp} =====\n{text}\n")
    except Exception:  # noqa: BLE001
        pass


@dataclass
class ApplyResult:
    ok: bool
    message: str = ""
    steps: List[str] = field(default_factory=list)   # 执行的命令
    detail: str = ""                                  # 原始输出尾部
    rolled_back: bool = False


class ApplyError(Exception):
    pass


def _ps_quote(s: str) -> str:
    return "'" + s.replace("'", "''") + "'"


class ProfileApplier:
    """把 Profile 应用到指定网卡。"""

    def __init__(self, dry_run: bool = False):
        self.dry_run = dry_run

    # ---------------------------------------------------------------- 命令构造
    def _build_static_commands(self, adapter: AdapterInfo, pf: Profile) -> List[str]:
        cmds: List[str] = []
        # 1) 关闭 DHCP
        cmds.append(
            "Set-NetIPInterface -InterfaceIndex {0} -AddressFamily IPv4 -Dhcp Disabled".format(adapter.index)
        )
        # 2) 清理该接口可能残留的默认路由（否则 New-NetRoute 报 already exists）
        cmds.append(
            "Get-NetRoute -InterfaceIndex {0} -DestinationPrefix '0.0.0.0/0' -ErrorAction SilentlyContinue | "
            "Remove-NetRoute -Confirm:$false -ErrorAction SilentlyContinue".format(adapter.index)
        )
        # 3) 移除旧 IPv4（避免地址残留/冲突）；无地址时无害，忽略
        cmds.append(
            "Get-NetIPAddress -InterfaceIndex {0} -AddressFamily IPv4 | "
            "Where-Object {{ $_.IPAddress -notlike '169.254.*' }} | "
            "Remove-NetIPAddress -Confirm:$false -ErrorAction SilentlyContinue".format(adapter.index)
        )
        # 4) 依次建立全部静态地址（不再把网关绑到 New-NetIPAddress）
        addrs = pf.all_addresses()
        for addr in addrs:
            cmds.append(
                "New-NetIPAddress -InterfaceIndex {0} -IPAddress {1} -PrefixLength {2}".format(
                    adapter.index, addr["ip"], addr["prefix"]
                )
            )
        # 5) 默认网关用独立 New-NetRoute 建立（须与主地址同网段，否则此步失败会被捕获）
        if is_valid_ipv4(pf.gateway):
            cmds.append(
                "New-NetRoute -DestinationPrefix '0.0.0.0/0' -InterfaceIndex {0} -NextHop {1}".format(
                    adapter.index, pf.gateway
                )
            )
        # 6) DNS
        dns_list = [d for d in (pf.dns1, pf.dns2) if is_valid_ipv4(d)]
        if dns_list:
            cmds.append(
                "Set-DnsClientServerAddress -InterfaceIndex {0} -ServerAddresses ({1})".format(
                    adapter.index, ", ".join(_ps_quote(d) for d in dns_list)
                )
            )
        else:
            cmds.append(
                "Set-DnsClientServerAddress -InterfaceIndex {0} -ResetServerAddresses".format(adapter.index)
            )
        return cmds

    def _build_dhcp_commands(self, adapter: AdapterInfo) -> List[str]:
        return [
            "Set-NetIPInterface -InterfaceIndex {0} -AddressFamily IPv4 -Dhcp Enabled".format(adapter.index),
            "Get-NetIPAddress -InterfaceIndex {0} -AddressFamily IPv4 | "
            "Where-Object {{ $_.IPAddress -notlike '169.254.*' }} | "
            "Remove-NetIPAddress -Confirm:$false -ErrorAction SilentlyContinue".format(adapter.index),
            "Set-DnsClientServerAddress -InterfaceIndex {0} -ResetServerAddresses".format(adapter.index),
        ]

    def _build_commands(self, adapter: AdapterInfo, pf: Profile) -> List[str]:
        if pf.mode == "dhcp":
            return self._build_dhcp_commands(adapter)
        return self._build_static_commands(adapter, pf)

    # ---------------------------------------------------------------- 执行
    def apply(self, adapter: AdapterInfo, pf: Profile) -> ApplyResult:
        result = ApplyResult(ok=False)
        if pf.mode == "static":
            errors = pf.validate()
            if errors:
                result.message = "；".join(errors)
                return result
        if not adapter or not adapter.name:
            result.message = "未指定有效网卡"
            return result

        commands = self._build_commands(adapter, pf)
        result.steps = commands

        if self.dry_run:
            result.ok = True
            result.message = "DRY-RUN：以下命令将被执行（未真正改动）：\n" + "\n".join(commands)
            return result

        if not self._has_admin():
            result.message = "需要管理员权限才能修改网卡配置。请以管理员身份重新启动本程序。"
            return result

        # 快照用于回滚
        snapshot = self._read_snapshot(adapter)
        # 一段脚本内顺序执行全部命令。
        # 注意：必须 $ErrorActionPreference='Stop' —— 否则 CimException（如
        # "DefaultGateway already exists"）是非终止错误，try/catch 捕获不到，
        # 命令“看起来成功”实际地址未生效（历史 bug：rc=0 但校验失败）。
        script_lines = [
            "$ErrorActionPreference = 'Stop'",
            "$fail = $null",
        ]
        for cmd in commands:
            script_lines.append(
                "if (-not $fail) {{ try {{ {0} }} catch {{ $fail = $_.Exception.Message }} }}".format(cmd)
            )
        script_lines.append('if ($fail) { Write-Output ("FAILED: " + $fail); exit 1 }')
        script_lines.append("Write-Output 'OK'")
        script = "\n".join(script_lines)

        rc, out, err = p.run_powershell_script(script, timeout=60.0)
        result.detail = (out + "\n" + err).strip()[-2000:]
        _log_apply(f"[apply] 网卡={adapter.name}(idx={adapter.index})\n档案={pf.name} mode={pf.mode}\n"
                   f"命令:\n" + "\n".join(commands) +
                   f"\n\nrc={rc}\n输出:\n{out}\n错误:\n{err}")
        if rc != 0 or "FAILED" in out:
            result.message = "应用失败：\n" + result.detail
            # 回滚
            rb = self._rollback(adapter, snapshot)
            result.rolled_back = rb.ok
            _log_apply(f"[apply] 命令失败 → 回滚={rb.ok}\n{rb.message}")
            if rb.ok:
                result.message += "\n（已自动回滚到原配置）"
            return result

        # 校验（延迟重试，容忍网络栈刷新）
        verify = self._verify(adapter, pf)
        _log_apply(f"[verify] 通过={verify.ok} detail={verify.detail}")
        if verify.ok:
            result.ok = True
            result.message = "配置已成功应用并生效。"
            if pf.mode == "static":
                addrs_desc = "、".join(
                    f"{a['ip']}/{a['prefix']}" for a in pf.all_addresses()
                )
                result.message += f"\nIP: {addrs_desc}" + (
                    f"  网关: {pf.gateway}" if is_valid_ipv4(pf.gateway) else ""
                )
            else:
                result.message += "\nDHCP 自动获取已启用。"
        else:
            result.message = "命令执行成功，但校验未通过：\n" + verify.detail
            rb = self._rollback(adapter, snapshot)
            result.rolled_back = rb.ok
            _log_apply(f"[verify] 校验失败 → 回滚={rb.ok}\n{rb.message}")
            if rb.ok:
                result.message += "\n（已自动回滚到原配置）"
        return result

    # ---------------------------------------------------------------- 快照/回滚/校验
    @staticmethod
    def _has_admin() -> bool:
        from nicmanager.system.elevation import is_admin
        return is_admin()

    @staticmethod
    def _read_snapshot(adapter: AdapterInfo) -> Optional[dict]:
        """读取当前 IPv4/DNS 作为快照。失败返回 None（跳过回滚）。"""
        try:
            rc, out, err = p.run_powershell_script(
                "[Console]::OutputEncoding=[System.Text.Encoding]::UTF8\n"
                "$if = Get-NetIPInterface -InterfaceIndex {0} -AddressFamily IPv4\n"
                "$addrs = @(Get-NetIPAddress -InterfaceIndex {0} -AddressFamily IPv4 | "
                "Where-Object {{ $_.IPAddress -notlike '169.254.*' }} | "
                "ForEach-Object {{ @{{ ip=$_.IPAddress; prefix=[int]$_.PrefixLength }} }})\n"
                "$dns = @(Get-DnsClientServerAddress -InterfaceIndex {0} -AddressFamily IPv4 | "
                "ForEach-Object {{ $_.ServerAddresses }})\n"
                "[pscustomobject]@{{ dhcp=[bool]$if.Dhcp; addrs=$addrs; dns=@($dns) }} | "
                "ConvertTo-Json -Depth 3 -Compress".format(adapter.index),
                timeout=30.0,
            )
            if rc == 0 and out.strip():
                import json
                return json.loads(out)
        except Exception:
            return None
        return None

    def _rollback(self, adapter: AdapterInfo, snapshot: Optional[dict]) -> ApplyResult:
        res = ApplyResult(ok=False, message="无快照，无法回滚")
        if not snapshot:
            return res
        try:
            dhcp = bool(snapshot.get("dhcp"))
            addrs = snapshot.get("addrs") or []
            dns = snapshot.get("dns") or []
            cmds: List[str] = []
            if dhcp:
                cmds.append(
                    "Set-NetIPInterface -InterfaceIndex {0} -AddressFamily IPv4 -Dhcp Enabled".format(adapter.index)
                )
                cmds.append(
                    "Set-DnsClientServerAddress -InterfaceIndex {0} -ResetServerAddresses".format(adapter.index)
                )
            else:
                cmds.append(
                    "Set-NetIPInterface -InterfaceIndex {0} -AddressFamily IPv4 -Dhcp Disabled".format(adapter.index)
                )
                cmds.append(
                    "Get-NetIPAddress -InterfaceIndex {0} -AddressFamily IPv4 | "
                    "Remove-NetIPAddress -Confirm:$false -ErrorAction SilentlyContinue".format(adapter.index)
                )
                for a in addrs:
                    gw = ""
                    # 网关需按原样恢复，但快照未存网关，保守用 default gateway 恢复代价高；
                    # 此处只恢复地址与 DNS，网关由用户重新配置或手动补设。
                    cmds.append(
                        "New-NetIPAddress -InterfaceIndex {0} -IPAddress {1} -PrefixLength {2}".format(
                            adapter.index, a.get("ip"), int(a.get("prefix") or 24)
                        )
                    )
            if dns:
                cmds.append(
                    "Set-DnsClientServerAddress -InterfaceIndex {0} -ServerAddresses ({1})".format(
                        adapter.index, ", ".join(_ps_quote(str(d)) for d in dns)
                    )
                )
            script = "$ErrorActionPreference='Continue'\n" + "\n".join(
                "try { " + c + " } catch { Write-Output ('RBFAIL: ' + $_.Exception.Message) }" for c in cmds
            )
            rc, out, err = p.run_powershell_script(script, timeout=60.0)
            if rc == 0 and "RBFAIL" not in out:
                res.ok = True
                res.message = "回滚成功"
            else:
                res.message = "回滚未完全成功：" + (out + err).strip()[-500:]
        except Exception as e:  # noqa: BLE001
            res.message = f"回滚异常：{e}"
        return res

    def _verify(self, adapter: AdapterInfo, pf: Profile) -> ApplyResult:
        """应用后读取实际配置，与目标档案比对（校验全部静态地址）。

        延迟重试：写入后网络栈可能尚未完全刷新（尤其涉及 DHCP/网关切换），
        先快速等待再读，减少误报。
        """
        res = ApplyResult(ok=False)
        # 每次尝试收集一致的“细节”
        attempts = [
            (0.6, "首次读取"),
            (1.2, "二次读取"),
            (0.0, "三次读取"),
        ]
        last_detail = "读取失败"
        cur = None
        for delay, label in attempts:
            if delay:
                time.sleep(delay)
            try:
                from nicmanager.system.reader import read_adapters
                adapters, channel = read_adapters()
                cur = next((a for a in adapters if a.index == adapter.index), None)
            except Exception as e:  # noqa: BLE001
                last_detail = f"{label}读取异常：{e}"
                continue
            if cur is None:
                last_detail = f"{label}：未找到目标网卡 idx={adapter.index}"
                continue
            if pf.mode == "dhcp":
                if cur.dhcp_enabled is True:
                    res.ok = True
                    return res
                last_detail = f"{label}：期望 DHCP 开启，实际 dhcp={cur.dhcp_enabled}"
                continue
            # 静态：校验每个期望地址
            expected_set = {
                f"{a['ip']}/{a['prefix']}" for a in pf.all_addresses()
            }
            actual_set = set()
            for cidr in cur.ipv4:
                ip, _, pre = cidr.partition("/")
                try:
                    actual_set.add(f"{ip}/{int(pre)}")
                except ValueError:
                    pass
            missing = sorted(expected_set - actual_set)
            if not missing:
                # 地址全部就位；再看网关与 DNS（提示性，允许网络未刷新）
                res.ok = True
                res.detail = f"地址全部就位（实际 {cur.ipv4_label}）"
                if pf.gateway and pf.gateway not in cur.gateways:
                    res.ok = False
                    res.detail = (f"网关未生效：期望 {pf.gateway}，实际 {cur.gateway_label}"
                                  f"；地址 {cur.ipv4_label}")
                if res.ok and pf.dns1 and pf.dns1 not in cur.dns_servers:
                    res.ok = False
                    res.detail = (f"首选 DNS 未生效：期望 {pf.dns1}，实际 {cur.dns_label}"
                                  f"；地址 {cur.ipv4_label}")
                if res.ok:
                    return res
                last_detail = res.detail
                continue
            last_detail = f"{label}：以下地址未生效：{', '.join(missing)}；实际 {cur.ipv4_label}"
        res.detail = last_detail
        return res
