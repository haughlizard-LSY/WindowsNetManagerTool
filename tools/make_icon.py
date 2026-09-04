"""生成应用图标 icon.ico（纯 Python + PySide6，无额外依赖）。

画一个简洁的"网卡/网络"图标：圆角方块 + 网口(RJ45)轮廓 + 信号点。
输出多尺寸 ICO（16/24/32/48/64/128/256），供 PyInstaller --icon 使用。
"""
from __future__ import annotations

import os
import struct
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPointF, QRectF, Qt  # noqa: E402
from PySide6.QtGui import QColor, QGuiApplication, QImage, QPainter, QPen  # noqa: E402

SIZES = [16, 24, 32, 48, 64, 128, 256]


def draw_icon(size: int) -> bytes:
    img = QImage(size, size, QImage.Format_ARGB32)
    img.fill(Qt.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing, True)

    s = size
    # ---- 背景：圆角深蓝色方块
    bg = QColor("#1a6dff")
    p.setBrush(bg)
    p.setPen(Qt.NoPen)
    r = s * 0.22
    p.drawRoundedRect(QRectF(0, 0, s, s), r, r)

    # ---- 三个白色 Wi-Fi 信号弧线（简化"网络"语义）
    pen = QPen(QColor("white"))
    pen.setWidthF(max(1.2, s * 0.075))
    pen.setCapStyle(Qt.RoundCap)
    p.setPen(pen)
    p.setBrush(Qt.NoBrush)

    cx, cy = s * 0.5, s * 0.55
    radii = [s * 0.18, s * 0.33, s * 0.48]
    for rad in radii:
        p.drawArc(
            QRectF(cx - rad, cy - rad, rad * 2, rad * 2),
            -45 * 16,   # 从 -45 度开始
            -100 * 16,  # 扫 100 度（开口向上扇形）
        )
    # ---- 中心圆点
    p.setPen(Qt.NoPen)
    p.setBrush(QColor("white"))
    dot = s * 0.10
    p.drawEllipse(QPointF(cx, cy - dot), dot, dot)

    p.end()
    # 转 PNG 字节
    from PySide6.QtCore import QBuffer, QIODevice

    buf = QBuffer()
    buf.open(QIODevice.ReadWrite)
    img.save(buf, "PNG")
    return bytes(buf.data())


def make_ico(path: str) -> None:
    # ICO 头 + 目录
    header = struct.pack("<HHH", 0, 1, len(SIZES))
    entries = b""
    blobs = []
    offset = 6 + 16 * len(SIZES)
    for size in SIZES:
        png = draw_icon(size)
        blobs.append(png)
        # 字节 0 为宽/高，>=256 时写 0
        w = size if size < 256 else 0
        entries += struct.pack("<BBBBHHII", w, w, 0, 0, 1, 32, len(png), offset)
        offset += len(png)
    with open(path, "wb") as f:
        f.write(header + entries + b"".join(blobs))
    print(f"icon written: {path}  ({offset} bytes, sizes={SIZES})")


if __name__ == "__main__":
    # 需要 QGuiApplication 供 QImage/QPainter 使用
    app = QGuiApplication(sys.argv)
    out = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "icon.ico")
    make_ico(out)
