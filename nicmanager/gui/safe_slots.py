"""Qt 回调异常护栏。

PySide6 中 Qt 槽/事件回调内的 Python 未捕获异常会直接 abort 进程，
导致"窗口一闪而过"。本模块提供包装器，把异常转为日志 + 弹窗，阻止崩溃。
"""
from __future__ import annotations

import datetime
import functools
import os
import traceback
from typing import Callable


def crash_log_path() -> str:
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    d = os.path.join(base, "NetManagerTool")
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, "crash.log")


def report_exception(context: str = "") -> None:
    """把当前异常写入 crash.log，并（GUI 可用时）弹窗。"""
    text = traceback.format_exc()
    stamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        with open(crash_log_path(), "a", encoding="utf-8") as f:
            f.write(f"\n===== {stamp} [{context}] =====\n{text}\n")
    except Exception:  # noqa: BLE001
        pass
    try:
        from PySide6.QtWidgets import QApplication, QMessageBox

        if QApplication.instance() is not None:
            QMessageBox.critical(
                None, "程序出错",
                f"操作「{context or '未知'}」发生异常：\n\n{text[-1500:]}\n\n"
                f"详情已写入：\n{crash_log_path()}",
            )
    except Exception:  # noqa: BLE001
        pass


def guard_slot(context: str = ""):
    """装饰器：包装 Qt 槽/回调，异常时记录+弹窗，避免 PySide6 abort。"""

    def deco(fn: Callable) -> Callable:
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            try:
                return fn(*args, **kwargs)
            except Exception:  # noqa: BLE001
                report_exception(context or fn.__name__)
                return None

        return wrapper

    return deco
