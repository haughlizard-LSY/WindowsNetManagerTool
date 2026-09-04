"""配置档案的新增/编辑对话框。

支持多个静态 IP：第一行为主 IP，其余为附加 IP（可增删）。
"""
from __future__ import annotations

from typing import List, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QButtonGroup,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QRadioButton,
    QVBoxLayout,
    QWidget,
)

from nicmanager.iputil import is_valid_ipv4
from nicmanager.models import Profile, split_cidr

_PREFIX_CHOICES = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17,
                   18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31, 32]


class _AddrRow:
    """单个地址输入行：IP 输入 + 前缀下拉 + 删除按钮。"""

    def __init__(self, ip: str = "", prefix: int = 24):
        self.widget = QWidget()
        lay = QHBoxLayout(self.widget)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)

        self.edt_ip = QLineEdit(ip)
        self.edt_ip.setPlaceholderText("如 192.168.1.100")
        self.cmb_prefix = QComboBox()
        for p in sorted(set(_PREFIX_CHOICES), reverse=True):
            self.cmb_prefix.addItem(f"/{p}", p)
        self.set_prefix(prefix)
        self.btn_del = QPushButton("✕")
        self.btn_del.setToolTip("删除此行 IP")
        self.btn_del.setFixedWidth(28)
        self.btn_del.setStyleSheet(
            "QPushButton{color:#b00;font-weight:bold;}"
            "QPushButton:disabled{color:#bbb;}"
        )

        lay.addWidget(self.edt_ip, 1)
        lay.addWidget(self.cmb_prefix)
        lay.addWidget(self.btn_del)

    def set_prefix(self, prefix: int) -> None:
        idx = self.cmb_prefix.findData(prefix)
        if idx >= 0:
            self.cmb_prefix.setCurrentIndex(idx)
        else:
            self.cmb_prefix.addItem(f"/{prefix}", prefix)
            self.cmb_prefix.setCurrentIndex(self.cmb_prefix.count() - 1)

    def values(self) -> tuple:
        return self.edt_ip.text().strip(), self.cmb_prefix.currentData()


class ProfileDialog(QDialog):
    """新增/编辑档案对话框。

    通过 result_profile() 获取编辑后的 Profile；取消返回 None。
    """

    def __init__(
        self,
        parent: Optional[QWidget] = None,
        adapter_name: str = "",
        profile: Optional[Profile] = None,
        existing_names=None,
        prefill: Optional[Profile] = None,
    ):
        """参数：
        - profile: 非空表示编辑已有档案
        - prefill: 仅预填字段的新建对话框（例如"保存当前配置为档案"）
        """
        super().__init__(parent)
        self.adapter_name = adapter_name
        self.profile = profile
        self.existing_names = set(existing_names or [])
        self._result_profile: Optional[Profile] = None
        self._addr_rows: List[_AddrRow] = []

        self.setWindowTitle(
            "编辑配置档案" if profile else ("新增配置档案" if prefill is None else "保存为配置档案")
        )
        self.setMinimumWidth(500)
        self._build_ui()
        # 初始给两行空地址（静态模式可直接填主/附加 IP）
        self._add_row()
        self._add_row()
        if profile:
            self._load_profile(profile)
        elif prefill is not None:
            self._load_profile(prefill)
        self._toggle_mode(self.rb_static.isChecked())

    # ---------------------------------------------------------------- UI
    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        form = QFormLayout()
        form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)

        self.edt_name = QLineEdit()
        self.edt_name.setPlaceholderText("例如：办公室-静态IP")
        form.addRow("档案名称 *", self.edt_name)

        # 获取方式
        self.rb_static = QRadioButton("静态 IP（手动指定）")
        self.rb_dhcp = QRadioButton("DHCP（自动获取）")
        self.rb_static.setChecked(True)
        mode_box = QWidget()
        mode_layout = QHBoxLayout(mode_box)
        mode_layout.setContentsMargins(0, 0, 0, 0)
        mode_layout.addWidget(self.rb_static)
        mode_layout.addWidget(self.rb_dhcp)
        self.mode_group = QButtonGroup(self)
        self.mode_group.addButton(self.rb_static)
        self.mode_group.addButton(self.rb_dhcp)
        form.addRow("获取方式", mode_box)

        # ---- 地址行容器（静态模式可用）----
        addr_box = QWidget()
        addr_layout = QVBoxLayout(addr_box)
        addr_layout.setContentsMargins(0, 0, 0, 0)
        addr_layout.setSpacing(2)
        self._addr_layout = addr_layout

        self.lbl_addr_note = QLabel("支持多个静态 IP（第一行为主 IP）")
        self.lbl_addr_note.setStyleSheet("color:#666;")
        addr_layout.addWidget(self.lbl_addr_note)

        self.addr_container = QWidget()
        self.addr_v = QVBoxLayout(self.addr_container)
        self.addr_v.setContentsMargins(0, 0, 0, 0)
        self.addr_v.setSpacing(2)
        addr_layout.addWidget(self.addr_container)

        self.btn_add_ip = QPushButton("＋ 添加一个 IP")
        self.btn_add_ip.clicked.connect(lambda: self._add_row())
        addr_layout.addWidget(self.btn_add_ip)

        form.addRow("IP 地址", addr_box)

        self.edt_gateway = QLineEdit()
        self.edt_gateway.setPlaceholderText("如 192.168.1.1（可留空）")
        form.addRow("默认网关", self.edt_gateway)

        self.edt_dns1 = QLineEdit()
        self.edt_dns1.setPlaceholderText("如 223.5.5.5（可留空）")
        form.addRow("首选 DNS", self.edt_dns1)

        self.edt_dns2 = QLineEdit()
        self.edt_dns2.setPlaceholderText("备用（可留空）")
        form.addRow("备用 DNS", self.edt_dns2)

        self.edt_note = QPlainTextEdit()
        self.edt_note.setFixedHeight(60)
        form.addRow("备注", self.edt_note)

        layout.addLayout(form)

        self.lbl_hint = QLabel()
        self.lbl_hint.setStyleSheet("color: gray;")
        self.lbl_hint.setWordWrap(True)
        layout.addWidget(self.lbl_hint)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText("保存")
        buttons.button(QDialogButtonBox.Cancel).setText("取消")
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self.rb_static.toggled.connect(self._toggle_mode)

    # ---------------------------------------------------------------- 地址行
    def _add_row(self, ip: str = "", prefix: int = 24) -> _AddrRow:
        row = _AddrRow(ip, prefix)
        row.btn_del.clicked.connect(lambda: self._remove_row(row))
        # 主地址行（第一行）不允许删除
        row.btn_del.setEnabled(len(self._addr_rows) > 0)
        self._addr_rows.append(row)
        self.addr_v.addWidget(row.widget)
        self._sync_del_buttons()
        return row

    def _remove_row(self, row: _AddrRow) -> None:
        if len(self._addr_rows) <= 1:
            return  # 至少保留一行
        self.addr_v.removeWidget(row.widget)
        row.widget.deleteLater()
        self._addr_rows.remove(row)
        self._sync_del_buttons()

    def _sync_del_buttons(self) -> None:
        # 仅剩一行时禁删；其余可删。但第一行(主IP)其实也可删空后由后续补位——
        # 简化：只保留一行的语义 = 所有行均可删，删到剩 1 行时自动加空行兜底
        for i, row in enumerate(self._addr_rows):
            row.btn_del.setEnabled(len(self._addr_rows) > 1)
            row.edt_ip.setPlaceholderText(
                "主 IP（如 192.168.1.100）" if i == 0 else "附加 IP（如 10.0.0.5）"
            )

    def _toggle_mode(self, static_checked: bool) -> None:
        static = bool(static_checked)
        for w in (self.lbl_addr_note, self.addr_container, self.btn_add_ip,
                  self.edt_gateway, self.edt_dns1, self.edt_dns2):
            w.setEnabled(static)
        if static:
            self.lbl_hint.setText("提示：Windows 同一网卡可配置多个静态 IP，第一行为主 IP。")
        else:
            self.lbl_hint.setText("DHCP 模式下将忽略下方填写的 IP/网关/DNS 字段。")

    def _load_profile(self, p: Profile) -> None:
        self.edt_name.setText(p.name)
        # 清掉初始两行空行
        while self._addr_rows:
            r = self._addr_rows.pop()
            self.addr_v.removeWidget(r.widget)
            r.widget.deleteLater()
        # 主地址
        if p.ip:
            self._add_row(p.ip, p.prefix)
        # 附加地址
        for cidr in p.extra_ips:
            ip, prefix = split_cidr(cidr)
            if ip:
                self._add_row(ip, prefix or 24)
        if not self._addr_rows:
            self._add_row()
        self._sync_del_buttons()

        if p.mode == "dhcp":
            self.rb_dhcp.setChecked(True)
            self.rb_static.setChecked(False)
        else:
            self.rb_static.setChecked(True)
        self.edt_gateway.setText(p.gateway)
        self.edt_dns1.setText(p.dns1)
        self.edt_dns2.setText(p.dns2)
        self.edt_note.setPlainText(p.note)
        self._toggle_mode(self.rb_static.isChecked())

    # ---------------------------------------------------------------- 提交
    def _collect_addrs(self) -> list:
        """收集全部行（跳过完全空白的行），返回 [(ip,prefix),...]。"""
        out = []
        for row in self._addr_rows:
            ip, prefix = row.values()
            if ip:
                out.append((ip, prefix))
        return out

    def _on_accept(self) -> None:
        name = self.edt_name.text().strip()
        if not name:
            QMessageBox.warning(self, "校验失败", "请填写档案名称。")
            return
        if name in self.existing_names and (self.profile is None or name != self.profile.name):
            QMessageBox.warning(self, "校验失败", f"该网卡下已存在名为「{name}」的档案。")
            return

        mode = "static" if self.rb_static.isChecked() else "dhcp"
        gateway = self.edt_gateway.text().strip()
        dns1 = self.edt_dns1.text().strip()
        dns2 = self.edt_dns2.text().strip()
        note = self.edt_note.toPlainText().strip()

        addrs = self._collect_addrs()

        if mode == "static":
            if not addrs:
                QMessageBox.warning(self, "校验失败", "请至少填写一个静态 IP 地址。")
                return
            seen = set()
            for ip, prefix in addrs:
                if not is_valid_ipv4(ip):
                    QMessageBox.warning(self, "校验失败", f"IP 地址「{ip}」不合法。")
                    return
                if not isinstance(prefix, int) or not (0 <= prefix <= 32):
                    QMessageBox.warning(self, "校验失败", "子网前缀长度必须为 0-32。")
                    return
                if ip in seen:
                    QMessageBox.warning(self, "校验失败", f"IP「{ip}」重复，请勿重复填写。")
                    return
                seen.add(ip)
            for label, val in (("网关", gateway), ("首选 DNS", dns1), ("备用 DNS", dns2)):
                if val and not is_valid_ipv4(val):
                    QMessageBox.warning(self, "校验失败", f"{label}「{val}」不是合法的 IPv4 地址。")
                    return
            if dns1 and dns1 == dns2:
                QMessageBox.warning(self, "校验失败", "首选与备用 DNS 不能相同。")
                return

        # 组装 Profile：第一行为主 IP
        primary_ip, primary_prefix = addrs[0] if addrs else ("", 24)
        extra_cidrs = [f"{ip}/{prefix}" for ip, prefix in addrs[1:]]

        if self.profile is not None:
            p = self.profile
            p.name = name
            p.mode = mode
            p.ip = primary_ip if mode == "static" else ""
            p.prefix = primary_prefix if mode == "static" else 24
            p.extra_ips = extra_cidrs if mode == "static" else []
            p.gateway = gateway if mode == "static" else ""
            p.dns1 = dns1 if mode == "static" else ""
            p.dns2 = dns2 if mode == "static" else ""
            p.note = note
        else:
            p = Profile(
                adapter_name=self.adapter_name,
                name=name,
                mode=mode,
                ip=primary_ip if mode == "static" else "",
                prefix=primary_prefix if mode == "static" else 24,
                extra_ips=extra_cidrs if mode == "static" else [],
                gateway=gateway if mode == "static" else "",
                dns1=dns1 if mode == "static" else "",
                dns2=dns2 if mode == "static" else "",
                note=note,
            )
        self._result_profile = p
        self.accept()

    def result_profile(self) -> Optional[Profile]:
        return self._result_profile
