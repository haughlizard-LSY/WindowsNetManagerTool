"""管理员权限检测与 UAC 提权重启。"""
from __future__ import annotations

import ctypes
import os
import subprocess
import sys
from typing import List, Optional


def is_admin() -> bool:
    """当前进程是否具有管理员权限（Windows）。"""
    if sys.platform != "win32":
        return False
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:  # noqa: BLE001
        return False


def _gui_interpreter() -> str:
    """返回用于启动 GUI 的解释器：优先 pythonw.exe（无控制台窗口）。

    说明：用 python.exe 启动 GUI 会常驻一个黑色命令行窗口；pythonw.exe
    是同一解释器的 GUI 变体，不附带控制台，体验更好。
    """
    base = os.path.dirname(sys.executable)
    candidate = os.path.join(base, "pythonw.exe")
    if os.path.exists(candidate):
        return candidate
    return sys.executable  # 找不到 pythonw（少见）时退回 python.exe


def relaunch_elevated(script_args: Optional[List[str]] = None) -> bool:
    """通过 UAC 以管理员身份重启当前程序。

    正确用法：ShellExecuteW(lpFile=解释器, lpParameters=仅脚本与参数)。
    不要把解释器自身路径拼进 lpParameters——否则 python 会把它当脚本执行，
    导致新进程一闪而过、GUI 无法启动。

    返回 True 表示提权进程已成功拉起（调用方应退出）；
    返回 False 表示用户取消或失败（调用方可降级为只读模式继续）。
    """
    if sys.platform != "win32":
        return False
    extra = list(script_args or [])
    if getattr(sys, "frozen", False):
        # PyInstaller 单文件：exe 即程序本身
        exe = sys.executable
        params = subprocess.list2cmdline(extra)
    else:
        # 源码模式：解释器 + 脚本绝对路径（cwd 无关，避免提权后目录变化）
        exe = _gui_interpreter()
        params = subprocess.list2cmdline([os.path.abspath(sys.argv[0]), *extra])
    try:
        # runas => 触发 UAC 弹窗；SW_SHOWNORMAL=1
        ret = ctypes.windll.shell32.ShellExecuteW(
            None, "runas", exe, params, None, 1
        )
        # 返回值 > 32 表示成功启动
        return ret > 32
    except Exception:  # noqa: BLE001
        return False
