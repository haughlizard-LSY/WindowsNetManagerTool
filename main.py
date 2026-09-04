"""网卡管理器入口。

启动流程：
1. 若为 Windows 且非管理员 → 通过 UAC 自动请求提权后重启自身；
2. 用户拒绝提权 → 以只读模式（可查看/编辑档案，不能应用）继续；
3. 启动 PySide6 主窗口。

任何未捕获异常都会写入崩溃日志（%APPDATA%\\NetManagerTool\\crash.log）
并弹出提示框，避免"窗口一闪而过"无从排查。
"""
from __future__ import annotations

import os
import sys
import traceback
from typing import Optional


def _log_dir() -> str:
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    d = os.path.join(base, "NetManagerTool")
    os.makedirs(d, exist_ok=True)
    return d


def install_crash_reporting() -> None:
    """安装全局异常钩子：写 crash.log + 弹窗提示（GUI 可用时）。"""
    log_path = os.path.join(_log_dir(), "crash.log")

    def excepthook(exc_type, exc, tb):
        text = "".join(traceback.format_exception(exc_type, exc, tb))
        try:
            with open(log_path, "a", encoding="utf-8") as f:
                f.write("\n===== crash @ %s =====\n%s\n" % (__import__("datetime").datetime.now(), text))
        except Exception:  # noqa: BLE001
            pass
        # GUI 已就绪时弹窗；stderr 可用时也打印（pythonw 下 stderr 为 None 则跳过）
        try:
            from PySide6.QtWidgets import QApplication, QMessageBox

            if QApplication.instance() is not None:
                QMessageBox.critical(
                    None, "程序出错",
                    f"发生未处理异常，程序即将退出。\n\n{text[-2000:]}\n\n详情已写入：\n{log_path}",
                )
        except Exception:  # noqa: BLE001
            pass
        try:
            if sys.stderr is not None:
                sys.__excepthook__(exc_type, exc, tb)
        except Exception:  # noqa: BLE001
            pass

    sys.excepthook = excepthook
    # Qt 槽内的 Python 异常（abort 前）也记录
    os.environ.setdefault("PYTHONFAULTHANDLER", "1")


# 保证以项目根目录运行时能 import nicmanager
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from nicmanager import APP_NAME  # noqa: E402
from nicmanager.gui.main_window import MainWindow  # noqa: E402
from nicmanager.storage import ProfileStore  # noqa: E402
from nicmanager.system.elevation import is_admin, relaunch_elevated  # noqa: E402

# 调试开关
_NO_ELEVATE = "--no-elevate" in sys.argv      # 跳过 UAC 提权
_ELEVATED = "--elevated" in sys.argv          # 提权后的子实例


def _parse_data_dir() -> Optional[str]:
    """解析 --data-dir=...，用于把数据库放到指定目录（测试/便携用）。"""
    for arg in sys.argv[1:]:
        if arg.startswith("--data-dir="):
            return arg.split("=", 1)[1]
    return None


def main() -> int:
    install_crash_reporting()
    data_dir = _parse_data_dir()

    # ---- 权限处理：自动请求提权（仅一次，用 --elevated 标记防循环）----
    if not _NO_ELEVATE and not _ELEVATED and not is_admin():
        relaunch_args = ["--elevated"]
        if data_dir:
            relaunch_args.append(f"--data-dir={data_dir}")
        launched = relaunch_elevated(relaunch_args)
        if launched:
            # 提权实例已启动，本实例退出（避免两个实例）
            return 0
        # 用户拒绝提权 → 降级只读模式继续（有 GUI 提示）

    from PySide6.QtWidgets import QApplication, QMessageBox

    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setOrganizationName("NetManagerTool")

    try:
        # 数据目录可覆盖（--data-dir）；默认 %APPDATA%/NetManagerTool
        db_path = os.path.join(data_dir, "profiles.db") if data_dir else None
        store = ProfileStore(db_path)
        win = MainWindow(store)
    except Exception:
        # 启动期异常：写日志并弹窗，而不是无声退出
        log_path = os.path.join(_log_dir(), "crash.log")
        text = traceback.format_exc()
        try:
            with open(log_path, "a", encoding="utf-8") as f:
                f.write("\n===== startup crash =====\n%s\n" % text)
        except Exception:  # noqa: BLE001
            pass
        QMessageBox.critical(
            None, "启动失败",
            f"程序初始化失败，无法启动窗口。\n\n{text[-1500:]}\n\n详情已写入：\n{log_path}",
        )
        return 1

    win.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())

