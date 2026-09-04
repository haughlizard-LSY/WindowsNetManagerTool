"""配置档案的新增/编辑对话框。"""
from __future__ import annotations

from typing import Optional

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
    QRadioButton,
    QVBoxLayout,
    QWidget,
)

from nicmanager.iputil import is_valid_ipv4, mask_to_prefix, prefix_to_mask
from nicmanager.models import Profile

_PREFIX_CHOICES = [24, 25, 26, 27, 28, 29, 30, 31, 32, 16, 8, 0, 1, 2, 3, 4, 5, 6, 7, 9, 10, 11, 12, 13, 14, 15, 17, 18, 19, 20, 21, 22, 23]


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
    ):
        super().__init__(parent)
        self.adapter_name = adapter_name
        self.profile = profile
        self.existing_names = set(existing_names or [])
        self._result_profile: Optional[Profile] = None

        self.setWindowTitle("编辑配置档案" if profile else "新增配置档案")
        self.setMinimumWidth(420)
        self._build_ui()
        if profile:
            self._load_profile(profile)

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

        # 静态参数
        self.edt_ip = QLineEdit()
        self.edt_ip.setPlaceholderText("如 192.168.1.100")
        form.addRow("IP 地址", self.edt_ip)

        prefix_row = QWidget()
        pl = QHBoxLayout(prefix_row)
        pl.setContentsMargins(0, 0, 0, 0)
        self.cmb_prefix = QComboBox()
        for p in sorted(set(_PREFIX_CHOICES), reverse=True):
            self.cmb_prefix.addItem(f"/{p}  (掩码 {prefix_to_mask(p)})", p)
        self.cmb_prefix.setCurrentIndex(self.cmb_prefix.findData(24))
        self.lbl_mask = QLabel()
        pl.addWidget(self.cmb_prefix, 1)
        pl.addWidget(self.lbl_mask)
        form.addRow("子网前缀", prefix_row)
        self.cmb_prefix.currentIndexChanged.connect(self._update_mask_hint)

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
        self._update_mask_hint()

    # ---------------------------------------------------------------- 逻辑
    def _toggle_mode(self, static_checked: bool) -> None:
        static = bool(static_checked)
        for w in (self.edt_ip, self.cmb_prefix, self.edt_gateway, self.edt_dns1, self.edt_dns2):
            w.setEnabled(static)
        self.lbl_hint.setText(
            "" if static else "DHCP 模式下将忽略下方填写的 IP/网关/DNS 字段。"
        )

    def _update_mask_hint(self) -> None:
        prefix = self.cmb_prefix.currentData()
        mask = prefix_to_mask(prefix) if isinstance(prefix, int) else "?"
        self.lbl_mask.setText(mask if mask else "无效前缀")

    def _load_profile(self, p: Profile) -> None:
        self.edt_name.setText(p.name)
        if p.mode == "dhcp":
            self.rb_dhcp.setChecked(True)
            self.rb_static.setChecked(False)
        else:
            self.rb_static.setChecked(True)
        self.edt_ip.setText(p.ip)
        idx = self.cmb_prefix.findData(p.prefix)
        if idx >= 0:
            self.cmb_prefix.setCurrentIndex(idx)
        else:
            self.cmb_prefix.addItem(f"/{p.prefix}  (掩码 {prefix_to_mask(p.prefix)})", p.prefix)
            self.cmb_prefix.setCurrentIndex(self.cmb_prefix.count() - 1)
        self.edt_gateway.setText(p.gateway)
        self.edt_dns1.setText(p.dns1)
        self.edt_dns2.setText(p.dns2)
        self.edt_note.setPlainText(p.note)
        self._toggle_mode(self.rb_static.isChecked())

    def _on_accept(self) -> None:
        name = self.edt_name.text().strip()
        if not name:
            QMessageBox.warning(self, "校验失败", "请填写档案名称。")
            return
        if name in self.existing_names and (self.profile is None or name != self.profile.name):
            QMessageBox.warning(self, "校验失败", f"该网卡下已存在名为「{name}」的档案。")
            return

        mode = "static" if self.rb_static.isChecked() else "dhcp"
        ip = self.edt_ip.text().strip()
        prefix = self.cmb_prefix.currentData()
        gateway = self.edt_gateway.text().strip()
        dns1 = self.edt_dns1.text().strip()
        dns2 = self.edt_dns2.text().strip()
        note = self.edt_note.toPlainText().strip()

        if mode == "static":
            if not is_valid_ipv4(ip):
                QMessageBox.warning(self, "校验失败", "IP 地址不合法。")
                return
            if not isinstance(prefix, int) or not (0 <= prefix <= 32):
                QMessageBox.warning(self, "校验失败", "子网前缀长度不合法。")
                return
            # 支持填掩码形式 → 转前缀
            if gateway and not is_valid_ipv4(gateway) and mask_to_prefix(gateway) is not None:
                pass
            for label, val in (("网关", gateway), ("首选 DNS", dns1), ("备用 DNS", dns2)):
                if val and not is_valid_ipv4(val):
                    QMessageBox.warning(self, "校验失败", f"{label}「{val}」不是合法的 IPv4 地址。")
                    return
            if dns1 and dns1 == dns2:
                QMessageBox.warning(self, "校验失败", "首选与备用 DNS 不能相同。")
                return

        if self.profile is not None:
            p = self.profile
            p.name = name
            p.mode = mode
            p.ip = ip
            p.prefix = prefix if mode == "static" else 24
            p.gateway = gateway if mode == "static" else ""
            p.dns1 = dns1 if mode == "static" else ""
            p.dns2 = dns2 if mode == "static" else ""
            p.note = note
        else:
            p = Profile(
                adapter_name=self.adapter_name,
                name=name,
                mode=mode,
                ip=ip,
                prefix=prefix if mode == "static" else 24,
                gateway=gateway if mode == "static" else "",
                dns1=dns1 if mode == "static" else "",
                dns2=dns2 if mode == "static" else "",
                note=note,
            )
        self._result_profile = p
        self.accept()

    def result_profile(self) -> Optional[Profile]:
        return self._result_profile
