"""真实桌面平台最小 GUI 测试：建窗 3 秒后自动退出。
用于排查“窗口一闪而过”是否平台/初始化问题。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QLabel


def main():
    print("creating QApplication...")
    app = QApplication(sys.argv)
    lbl = QLabel("冒烟窗口 - 3 秒后自动关闭")
    lbl.resize(300, 100)
    lbl.show()
    print("window shown")
    QTimer.singleShot(3000, app.quit)
    rc = app.exec()
    print("app.exec returned", rc)
    return rc


if __name__ == "__main__":
    sys.exit(main())
