import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtCore import QCoreApplication, QTimer

from nicmanager.gui.workers import RefreshThread

LOG = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".tmp_db", "thread.log")
os.makedirs(os.path.dirname(LOG), exist_ok=True)


def log(msg):
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(msg + "\n")


def main():
    app = QCoreApplication(sys.argv)
    t = RefreshThread()
    t.finished_ok.connect(lambda ads, ch: (log(f"OK count={len(ads)} ch={ch}"), app.quit()))
    t.finished_err.connect(lambda m: (log("ERR " + m), app.quit()))
    t.start()
    QTimer.singleShot(20000, lambda: (log("TIMEOUT"), app.quit()))
    app.exec()
    log("DONE")
    print("thread test finished, see", LOG)
    return 0


if __name__ == "__main__":
    sys.exit(main())
