"""预览工具图标设计稿（256px PNG），用于人工确认美观度。"""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtCore import QBuffer, QIODevice  # noqa: E402
from PySide6.QtGui import QGuiApplication, QImage  # noqa: E402

from tools.make_icon import draw_icon  # noqa: E402


def main():
    app = QGuiApplication(sys.argv)
    png = draw_icon(256)
    img = QImage()
    img.loadFromData(png, "PNG")
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_icon_preview_256.png")
    img.save(out, "PNG")
    print("saved", out, img.size())


if __name__ == "__main__":
    main()
