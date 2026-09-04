"""后台线程：把耗时的系统读/写操作移出 GUI 主线程。"""
from __future__ import annotations

from typing import List, Optional

from PySide6.QtCore import QThread, Signal

from nicmanager.models import AdapterInfo, Profile
from nicmanager.system.applier import ApplyResult, ProfileApplier
from nicmanager.system.reader import read_adapters


class RefreshThread(QThread):
    """刷新网卡列表与当前配置。"""

    finished_ok = Signal(list, str)        # adapters: List[AdapterInfo], channel
    finished_err = Signal(str)             # 错误消息

    def __init__(self, parent=None):
        super().__init__(parent)

    def run(self) -> None:
        try:
            adapters, channel = read_adapters()
            self.finished_ok.emit(adapters, channel)
        except Exception as e:  # noqa: BLE001
            self.finished_err.emit(f"读取网卡失败：{e}")


class ApplyThread(QThread):
    """后台应用配置档案。"""

    finished = Signal(object)              # ApplyResult

    def __init__(self, adapter: AdapterInfo, profile: Profile, dry_run: bool = False, parent=None):
        super().__init__(parent)
        self.adapter = adapter
        self.profile = profile
        self.dry_run = dry_run

    def run(self) -> None:
        try:
            applier = ProfileApplier(dry_run=self.dry_run)
            result = applier.apply(self.adapter, self.profile)
        except Exception as e:  # noqa: BLE001
            result = ApplyResult(ok=False, message=f"应用配置时发生异常：{e}")
        self.finished.emit(result)
