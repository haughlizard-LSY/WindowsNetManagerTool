"""GUI 冒烟测试：offscreen 模式创建主窗口并触发一次刷新，验证不崩溃。"""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtWidgets import QApplication  # noqa: E402

from nicmanager.gui.main_window import MainWindow  # noqa: E402
from nicmanager.storage import ProfileStore  # noqa: E402

DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".tmp_db", "gui_smoke.db")
LOG = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".tmp_db", "gui_smoke.log")


def log(msg):
    os.makedirs(os.path.dirname(LOG), exist_ok=True)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(msg + "\n")


def main() -> int:
    os.makedirs(os.path.dirname(DB), exist_ok=True)
    if os.path.exists(DB):
        os.unlink(DB)
    if os.path.exists(LOG):
        os.unlink(LOG)
    app = QApplication(sys.argv)
    store = ProfileStore(DB)
    # 预置档案：验证界面能加载并渲染档案列表
    from nicmanager.models import Profile

    store.add(Profile(adapter_name="以太网", name="办公室-静态", mode="static",
                      ip="10.0.0.5", prefix=24, gateway="10.0.0.1", dns1="114.114.114.114", note="smoke"))
    store.add(Profile(adapter_name="以太网", name="家里-DHCP", mode="dhcp", note="smoke"))
    store.add(Profile(adapter_name="WLAN", name="会议室-静态", mode="static",
                      ip="192.168.10.9", prefix=24, gateway="192.168.10.1"))
    win = MainWindow(store)
    log("window created")

    win.show()
    log("window shown")

    from PySide6.QtCore import QTimer

    ticks = {"n": 0}

    def check_and_quit():
        ticks["n"] += 1
        try:
            if win._refresh_thread is not None:  # 回调处理完成会置 None
                if ticks["n"] % 5 == 0:
                    log(f"tick={ticks['n']} refresh still pending")
                QTimer.singleShot(200, check_and_quit)
                return
            log(f"tick={ticks['n']} adapters={len(win.adapters)} profiles0={len(win.profiles)} table_rows={win.table_profiles.rowCount()}")
            # 选中“以太网”所在行，验证其 2 个档案被加载
            target = next((i for i, a in enumerate(win.adapters) if a.name == "以太网"), -1)
            if target >= 0:
                win.list_adapters.setCurrentRow(target)
                log(f"selected 以太网 row={target} profiles={len(win.profiles)} rows={win.table_profiles.rowCount()} "
                    f"names={[win.profiles[i].name for i in range(len(win.profiles))]}")
            app.quit()
        except Exception as e:  # noqa: BLE001
            log(f"exception: {e!r}")
            app.quit()

    QTimer.singleShot(100, check_and_quit)
    QTimer.singleShot(30000, app.quit)  # 兜底
    app.exec()
    print("SMOKE_DONE")
    return 0


if __name__ == "__main__":
    sys.exit(main())
