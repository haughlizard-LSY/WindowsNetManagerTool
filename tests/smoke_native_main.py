"""真实桌面会话：完整主窗口 + 自动刷新，8 秒后退出。
捕获任何 Qt 槽/线程异常并打印（不依赖 crash 弹窗）。
"""
import os
import sys
import traceback

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 让 PySide6 槽内异常不要 abort：安装钩子
import nicmanager.gui.safe_slots as ss  # noqa: E402

LOG = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".tmp_db", "native_gui.log")
os.makedirs(os.path.dirname(LOG), exist_ok=True)


def log(msg):
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(msg + "\n")


from PySide6.QtWidgets import QApplication  # noqa: E402
from PySide6.QtCore import QTimer  # noqa: E402

from nicmanager.gui.main_window import MainWindow  # noqa: E402
from nicmanager.storage import ProfileStore  # noqa: E402

DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".tmp_db", "native_gui.db")


def main():
    os.makedirs(os.path.dirname(DB), exist_ok=True)
    if os.path.exists(LOG):
        os.unlink(LOG)
    print("native main window test...")
    app = QApplication(sys.argv)
    store = ProfileStore(DB)
    win = MainWindow(store)
    win.show()
    print("window shown, running 8s")
    ticks = {"n": 0}

    def check():
        ticks["n"] += 1
        if win._refresh_thread is None and win.adapters:
            log(f"refresh done: adapters={len(win.adapters)}")
            QTimer.singleShot(2000, app.quit)
            return
        if ticks["n"] > 100:
            log("timeout waiting refresh")
            app.quit()
            return
        QTimer.singleShot(200, check)

    QTimer.singleShot(300, check)
    QTimer.singleShot(12000, app.quit)  # 兜底
    rc = app.exec()
    print("app.exec returned", rc)
    log(f"final adapters={len(win.adapters)}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        with open(LOG, "a", encoding="utf-8") as f:
            f.write("\nTOP-LEVEL EXC:\n" + traceback.format_exc())
        raise
