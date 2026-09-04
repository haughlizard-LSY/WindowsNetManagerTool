"""主窗口：网卡列表 | 当前配置 + 配置档案管理 + 应用切换。"""
from __future__ import annotations

from typing import List, Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from nicmanager import APP_NAME, __version__
from nicmanager.gui.profile_dialog import ProfileDialog
from nicmanager.gui.safe_slots import guard_slot
from nicmanager.gui.workers import ApplyThread, RefreshThread
from nicmanager.models import AdapterInfo, Profile
from nicmanager.storage import ProfileStore
from nicmanager.system.applier import ProfileApplier
from nicmanager.system.elevation import is_admin


class MainWindow(QMainWindow):
    def __init__(self, store: ProfileStore, parent=None):
        super().__init__(parent)
        self.store = store
        self.adapters: List[AdapterInfo] = []
        self.profiles: List[Profile] = []
        self.current_adapter: Optional[AdapterInfo] = None
        self.is_admin = is_admin()
        self._refresh_thread: Optional[RefreshThread] = None
        self._apply_thread: Optional[ApplyThread] = None

        self.setWindowTitle(f"{APP_NAME} v{__version__}")
        self.resize(1080, 720)
        self._build_ui()
        self._build_menu()
        self._update_admin_banner()
        self.refresh()

    # ================================================================ UI 构建
    def _build_ui(self) -> None:
        central = QWidget()
        root = QVBoxLayout(central)
        root.setContentsMargins(8, 8, 8, 8)

        # 权限提示条（非管理员时显示 + 提权按钮）
        banner = QWidget()
        banner_lay = QHBoxLayout(banner)
        banner_lay.setContentsMargins(6, 4, 6, 4)
        self.lbl_banner = QLabel()
        self.lbl_banner.setWordWrap(True)
        self.btn_elevate = QPushButton("以管理员身份重启")
        self.btn_elevate.setStyleSheet(
            "QPushButton{background:#1f6feb;color:white;padding:3px 12px;font-weight:bold;}"
            "QPushButton:hover{background:#388bfd;}"
        )
        banner_lay.addWidget(self.lbl_banner, 1)
        banner_lay.addWidget(self.btn_elevate)
        banner.setStyleSheet(
            "background:#fff3cd;color:#7a5b00;border-radius:4px;"
        )
        banner.setVisible(False)
        self._banner_widget = banner
        root.addWidget(banner)

        splitter = QSplitter(Qt.Horizontal)
        root.addWidget(splitter, 1)

        # ---- 左侧：网卡列表
        left = QWidget()
        left_lay = QVBoxLayout(left)
        left_lay.setContentsMargins(0, 0, 0, 0)
        left_lay.addWidget(QLabel("本机网卡"))
        self.list_adapters = QListWidget()
        self.list_adapters.setMinimumWidth(240)
        self.list_adapters.currentRowChanged.connect(self._on_adapter_selected)
        left_lay.addWidget(self.list_adapters, 1)
        splitter.addWidget(left)

        # ---- 右侧
        right = QWidget()
        right_lay = QVBoxLayout(right)
        right_lay.setContentsMargins(0, 0, 0, 0)

        # 当前配置
        grp_cur = QGroupBox("当前配置（只读）")
        cur_form = QFormLayout(grp_cur)
        self.lbl_name = self._detail_label()
        self.lbl_desc = self._detail_label()
        self.lbl_status = self._detail_label()
        self.lbl_mac = self._detail_label()
        self.lbl_dhcp = self._detail_label()
        self.lbl_ipv4 = self._detail_label()
        self.lbl_gw = self._detail_label()
        self.lbl_dns = self._detail_label()
        cur_form.addRow("网卡名称:", self.lbl_name)
        cur_form.addRow("描述:", self.lbl_desc)
        cur_form.addRow("连接状态:", self.lbl_status)
        cur_form.addRow("MAC 地址:", self.lbl_mac)
        cur_form.addRow("获取方式:", self.lbl_dhcp)
        cur_form.addRow("IPv4 地址:", self.lbl_ipv4)
        cur_form.addRow("默认网关:", self.lbl_gw)
        cur_form.addRow("DNS 服务器:", self.lbl_dns)
        right_lay.addWidget(grp_cur)

        # 档案区
        grp_profiles = QGroupBox("配置档案")
        pv = QVBoxLayout(grp_profiles)
        toolbar = QHBoxLayout()
        self.btn_new = QPushButton("新增档案")
        self.btn_edit = QPushButton("编辑")
        self.btn_del = QPushButton("删除")
        self.btn_apply = QPushButton("应用选中档案 ▶")
        self.btn_apply.setStyleSheet(
            "QPushButton{background:#1a7f37;color:white;font-weight:bold;padding:4px 14px;}"
            "QPushButton:disabled{background:#ccc;color:#888;}"
        )
        self.btn_preview = QPushButton("预览命令")
        self.btn_refresh = QPushButton("刷新")
        for b in (self.btn_new, self.btn_edit, self.btn_del, self.btn_preview):
            b.setEnabled(False)
        toolbar.addWidget(self.btn_new)
        toolbar.addWidget(self.btn_edit)
        toolbar.addWidget(self.btn_del)
        toolbar.addStretch(1)
        toolbar.addWidget(self.btn_preview)
        toolbar.addWidget(self.btn_apply)
        toolbar.addWidget(self.btn_refresh)
        pv.addLayout(toolbar)

        self.table_profiles = QTableWidget(0, 3)
        self.table_profiles.setHorizontalHeaderLabels(["档案名称", "配置", "备注"])
        self.table_profiles.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table_profiles.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table_profiles.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table_profiles.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table_profiles.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.table_profiles.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.table_profiles.verticalHeader().setVisible(False)
        self.table_profiles.itemSelectionChanged.connect(self._on_profile_selected)
        self.table_profiles.itemDoubleClicked.connect(lambda *_: self._edit_selected())
        pv.addWidget(self.table_profiles, 1)

        # 状态行
        self.lbl_statusline = QLabel("就绪")
        self.lbl_statusline.setStyleSheet("color:#555;")
        pv.addWidget(self.lbl_statusline)
        right_lay.addWidget(grp_profiles, 1)

        splitter.addWidget(right)
        splitter.setStretchFactor(1, 1)
        self.setCentralWidget(central)

        self.btn_refresh.clicked.connect(self.refresh)
        self.btn_new.clicked.connect(self._add_profile)
        self.btn_edit.clicked.connect(self._edit_selected)
        self.btn_del.clicked.connect(self._delete_selected)
        self.btn_apply.clicked.connect(self._apply_selected)
        self.btn_preview.clicked.connect(self._preview_selected)
        self.btn_elevate.clicked.connect(self._request_elevate)

    def _build_menu(self) -> None:
        mbar = self.menuBar()
        m_ops = mbar.addMenu("操作(&O)")
        act_refresh = QAction("刷新网卡", self)
        act_refresh.setShortcut("F5")
        act_refresh.triggered.connect(self.refresh)
        m_ops.addAction(act_refresh)
        m_ops.addSeparator()
        act_quit = QAction("退出", self)
        act_quit.triggered.connect(self.close)
        m_ops.addAction(act_quit)

        m_help = mbar.addMenu("帮助(&H)")
        act_about = QAction("关于", self)
        act_about.triggered.connect(self._show_about)
        m_help.addAction(act_about)

    def _detail_label(self) -> QLabel:
        lbl = QLabel("—")
        lbl.setTextInteractionFlags(Qt.TextSelectableByMouse)
        lbl.setWordWrap(True)
        return lbl

    # ================================================================ 状态
    @guard_slot("请求提权")
    def _request_elevate(self) -> None:
        """通过 UAC 以管理员身份重启；成功后本窗口应关闭。"""
        from nicmanager.system.elevation import relaunch_elevated

        ret = QMessageBox.question(
            self, "以管理员身份重启",
            "将触发 UAC 弹窗并以管理员权限重启程序，以便启用「应用配置」。\n"
            "继续吗？",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if ret != QMessageBox.Yes:
            return
        if relaunch_elevated(["--elevated"]):
            QMessageBox.information(
                self, "提权启动",
                "已请求管理员实例启动。\n"
                "若新窗口标题显示「管理员」即成功；此窗口即将关闭，请操作新窗口。",
            )
            self.close()
        else:
            QMessageBox.warning(
                self, "提权失败",
                "未能启动管理员实例（可能取消了 UAC 弹窗）。\n"
                "您仍可查看与编辑档案；应用配置需管理员权限。",
            )

    def _refresh_admin_state(self) -> None:
        """重新检测管理员权限并刷新标题/横幅/按钮。"""
        self.is_admin = is_admin()
        self._update_title()
        self._update_admin_banner()
        # 重算档案按钮可用性
        has = self._selected_profile() is not None
        self.btn_apply.setEnabled(has and self.is_admin)

    def _update_title(self) -> None:
        mode = "管理员" if self.is_admin else "普通权限（只读：可查看/建档，不能应用配置）"
        self.setWindowTitle(f"{APP_NAME} v{__version__}  —  [{mode}]")

    def _update_admin_banner(self) -> None:
        if self.is_admin:
            self._banner_widget.setVisible(False)
        else:
            self.lbl_banner.setText(
                "⚠ 当前窗口不是管理员权限：「应用选中档案」不可用。\n"
                "请点击右侧按钮通过 UAC 以管理员身份重启；若已提权却仍显示此条，"
                "说明本窗口是旧的未提权实例，请关闭后重新启动。"
            )
            self._banner_widget.setVisible(True)

    def _set_status(self, text: str) -> None:
        self.lbl_statusline.setText(text)

    # ================================================================ 刷新
    @guard_slot("刷新网卡")
    def refresh(self) -> None:
        self._set_status("正在读取网卡信息…")
        self.btn_refresh.setEnabled(False)
        thread = RefreshThread(self)
        self._refresh_thread = thread
        thread.finished_ok.connect(self._on_refreshed)
        thread.finished_err.connect(self._on_refresh_error)
        thread.finished.connect(thread.deleteLater)
        thread.start()

    @guard_slot("刷新完成")
    def _on_refreshed(self, adapters: List[AdapterInfo], channel: str) -> None:
        self._refresh_thread = None  # 避免访问已 deleteLater 的对象
        self.adapters = adapters
        self.btn_refresh.setEnabled(True)
        self.list_adapters.blockSignals(True)
        self.list_adapters.clear()
        for a in adapters:
            item = QListWidgetItem(f"{a.name}   [{a.status_label}]")
            item.setData(Qt.UserRole, a)
            item.setToolTip(f"{a.description}\nIPv4: {a.ipv4_label}")
            self.list_adapters.addItem(item)
        self.list_adapters.blockSignals(False)
        if adapters:
            self.list_adapters.setCurrentRow(0)
        self._set_status(f"已读取 {len(adapters)} 块网卡（数据源：{channel}）" + ("；管理员模式" if self.is_admin else ""))
        # 无网卡时禁用操作
        has = bool(adapters)
        self.btn_new.setEnabled(has)
        self.btn_preview.setEnabled(has)

    @guard_slot("刷新失败处理")
    def _on_refresh_error(self, msg: str) -> None:
        self._refresh_thread = None
        self.btn_refresh.setEnabled(True)
        self._set_status("读取失败")
        QMessageBox.critical(self, "读取失败", msg)

    # ================================================================ 选中逻辑
    @guard_slot("选择网卡")
    def _on_adapter_selected(self, row: int) -> None:
        if row < 0 or row >= len(self.adapters):
            return
        adapter = self.adapters[row]
        self.current_adapter = adapter
        self._render_current(adapter)
        self._load_profiles(adapter.name)

    def _render_current(self, a: AdapterInfo) -> None:
        self.lbl_name.setText(a.name)
        self.lbl_desc.setText(a.description or "—（netsh 通道不提供描述）")
        self.lbl_status.setText(a.status_label)
        self.lbl_mac.setText(a.mac or "—")
        self.lbl_dhcp.setText("DHCP 自动获取" if a.dhcp_enabled else ("静态 IP" if a.dhcp_enabled is False else "未知"))
        self.lbl_ipv4.setText(a.ipv4_label)
        self.lbl_gw.setText(a.gateway_label)
        self.lbl_dns.setText(a.dns_label)

    def _load_profiles(self, adapter_name: str) -> None:
        self.profiles = self.store.list_by_adapter(adapter_name)
        self._render_profiles()
        self.btn_new.setEnabled(True)
        self.btn_edit.setEnabled(False)
        self.btn_del.setEnabled(False)
        self.btn_apply.setEnabled(False)
        self.btn_preview.setEnabled(False)
        self._set_status(f"网卡「{adapter_name}」共有 {len(self.profiles)} 个配置档案")

    def _render_profiles(self) -> None:
        self.table_profiles.setRowCount(len(self.profiles))
        for i, p in enumerate(self.profiles):
            self.table_profiles.setItem(i, 0, QTableWidgetItem(p.name))
            cell = QTableWidgetItem(p.summary())
            if p.mode == "static":
                cell.setForeground(QColor("#1a7f37"))
            else:
                cell.setForeground(QColor("#0969da"))
            self.table_profiles.setItem(i, 1, cell)
            self.table_profiles.setItem(i, 2, QTableWidgetItem(p.note))
            self.table_profiles.item(i, 0).setData(Qt.UserRole, p)
        if self.profiles:
            self.table_profiles.selectRow(0)

    def _selected_profile(self) -> Optional[Profile]:
        rows = self.table_profiles.selectionModel().selectedRows()
        if not rows:
            return None
        row = rows[0].row()
        return self.profiles[row] if 0 <= row < len(self.profiles) else None

    @guard_slot("选中档案")
    def _on_profile_selected(self) -> None:
        p = self._selected_profile()
        has = p is not None
        self.btn_edit.setEnabled(has)
        self.btn_del.setEnabled(has)
        self.btn_apply.setEnabled(has and self.is_admin)
        self.btn_preview.setEnabled(has)
        if has and not self.is_admin:
            self.btn_apply.setToolTip("需要管理员权限：点击顶部黄色横幅上的「以管理员身份重启」")
        elif not has:
            self.btn_apply.setToolTip("请先在上方选中一个配置档案（或点击「新增档案」）")
        else:
            self.btn_apply.setToolTip("")
        if p:
            self._set_status(f"已选中档案「{p.name}」 → {p.summary()}")

    # ================================================================ 档案 CRUD
    def _current_adapter_for_edit(self) -> Optional[AdapterInfo]:
        if not self.current_adapter:
            QMessageBox.information(self, "提示", "请先在左侧选择一块网卡。")
            return None
        return self.current_adapter

    @guard_slot("新增档案")
    def _add_profile(self) -> None:
        a = self._current_adapter_for_edit()
        if not a:
            return
        existing = [p.name for p in self.profiles]
        dlg = ProfileDialog(self, adapter_name=a.name, existing_names=existing)
        if dlg.exec() == QDialog.Accepted and dlg.result_profile():
            p = dlg.result_profile()
            errs = p.validate()
            if errs:
                QMessageBox.warning(self, "校验失败", "\n".join(errs))
                return
            self.store.add(p)
            self._load_profiles(a.name)
            self._set_status(f"已新增档案「{p.name}」")

    @guard_slot("编辑档案")
    def _edit_selected(self) -> None:
        a = self.current_adapter
        p = self._selected_profile()
        if not a or not p:
            return
        existing = [x.name for x in self.profiles if x.id != p.id]
        dlg = ProfileDialog(self, adapter_name=a.name, profile=p, existing_names=existing)
        if dlg.exec() == QDialog.Accepted and dlg.result_profile():
            newp = dlg.result_profile()
            errs = newp.validate()
            if errs:
                QMessageBox.warning(self, "校验失败", "\n".join(errs))
                return
            self.store.update(newp)
            self._load_profiles(a.name)
            self._set_status(f"已更新档案「{newp.name}」")

    @guard_slot("删除档案")
    def _delete_selected(self) -> None:
        p = self._selected_profile()
        if not p:
            return
        ret = QMessageBox.question(
            self, "确认删除",
            f"确定删除网卡「{p.adapter_name}」下的档案「{p.name}」吗？\n"
            "（仅删除本工具的档案记录，不会改动系统网络配置）",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if ret == QMessageBox.Yes:
            self.store.delete(p.id)
            self._load_profiles(self.current_adapter.name)
            self._set_status(f"已删除档案「{p.name}」")

    # ================================================================ 预览与应用
    @guard_slot("预览命令")
    def _preview_selected(self) -> None:
        a, p = self.current_adapter, self._selected_profile()
        if not a or not p:
            return
        try:
            applier = ProfileApplier(dry_run=True)
            result = applier.apply(a, p)
            QMessageBox.information(self, "将执行的命令（预览）", result.message)
        except Exception as e:  # noqa: BLE001
            QMessageBox.critical(self, "预览失败", str(e))

    @guard_slot("应用档案")
    def _apply_selected(self) -> None:
        a, p = self.current_adapter, self._selected_profile()
        if not a or not p:
            return
        if not self.is_admin:
            QMessageBox.warning(
                self, "需要管理员权限",
                "应用配置需要管理员权限。请以管理员身份重新启动本程序后再试。",
            )
            return
        summary = p.summary()
        if p.mode == "static":
            extra = f"\nIP: {p.ip}/{p.prefix}"
            if p.gateway:
                extra += f"\n网关: {p.gateway}"
            if p.dns1:
                extra += f"\nDNS: {p.dns1}" + (f"、{p.dns2}" if p.dns2 else "")
        else:
            extra = "\n将启用 DHCP 自动获取 IP 与 DNS。"
        ret = QMessageBox.warning(
            self, "应用配置（将中断网络）",
            f"将把档案「{p.name}」应用到网卡「{a.name}」。\n\n"
            f"目标配置：{summary}{extra}\n\n"
            "⚠ 操作会立即修改网卡配置，可能导致当前网络连接短暂中断；\n"
            "若配置错误可能无法上网，请谨慎操作。",
            QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel,
            QMessageBox.No,
        )
        if ret != QMessageBox.Yes:
            return

        self.btn_apply.setEnabled(False)
        self._set_status(f"正在应用档案「{p.name}」到「{a.name}」…（期间网络可能中断）")
        thread = ApplyThread(a, p, parent=self)
        self._apply_thread = thread
        thread.finished.connect(self._on_applied)
        thread.finished.connect(thread.deleteLater)
        thread.start()

    @guard_slot("应用结果")
    def _on_applied(self, result) -> None:
        self._apply_thread = None  # 避免访问已 deleteLater 的对象
        self.btn_apply.setEnabled(self.is_admin)
        if result.ok:
            QMessageBox.information(self, "应用成功", result.message)
        else:
            QMessageBox.critical(self, "应用失败", result.message)
        self._set_status(result.message.splitlines()[0] if result.message else "完成")
        # 应用后自动刷新，展示最新系统配置
        self.refresh()

    # ================================================================ 其它
    @guard_slot("关于")
    def _show_about(self) -> None:
        QMessageBox.about(
            self, f"关于 {APP_NAME}",
            f"{APP_NAME} v{__version__}\n\n"
            "Windows 本地网卡配置管理工具：\n"
            "· 查看本机网卡当前配置\n"
            "· 为每块网卡维护多套配置档案（静态 IP / DHCP）\n"
            "· 一键应用/切换配置档案\n\n"
            "数据来源：PowerShell / netsh（需要管理员权限执行写操作）",
        )

    @guard_slot("窗口关闭")
    def closeEvent(self, event) -> None:
        # 确保后台线程退出
        for t in (self._refresh_thread, self._apply_thread):
            if t is not None:
                try:
                    if t.isRunning():
                        t.wait(3000)
                except RuntimeError:
                    pass  # 线程对象已被 deleteLater
        super().closeEvent(event)
