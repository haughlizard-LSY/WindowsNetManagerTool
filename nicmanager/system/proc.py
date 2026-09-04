"""子进程执行与文本解码工具。

注意：所有 subprocess 调用都带 CREATE_NO_WINDOW（Windows），
避免从 GUI 程序启动 powershell/netsh 时弹出黑色控制台窗口。
"""
from __future__ import annotations

import os
import subprocess
import tempfile
from typing import List, Tuple

# Windows：不创建新控制台窗口（从 windowed GUI 进程启动控制台程序时必要）
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def decode_output(data: bytes) -> str:
    """netsh 等原生命令输出编码自适应解码：优先 UTF-8，其次 GBK。"""
    for enc in ("utf-8", "gbk", "cp1252"):
        try:
            return data.decode(enc)
        except (UnicodeDecodeError, LookupError):
            continue
    return data.decode("utf-8", errors="replace")


def run_command(
    argv: List[str],
    timeout: float = 20.0,
) -> Tuple[int, str, str]:
    """运行命令并返回 (returncode, stdout, stderr)。编码自适应；不弹窗。"""
    proc = subprocess.run(
        argv,
        capture_output=True,
        timeout=timeout,
        creationflags=_NO_WINDOW,
    )
    return proc.returncode, decode_output(proc.stdout), decode_output(proc.stderr)


def run_netsh(args: List[str], timeout: float = 20.0) -> Tuple[int, str, str]:
    """运行 netsh <args>。"""
    return run_command(["netsh", *args], timeout=timeout)


def run_powershell_script(script: str, timeout: float = 30.0) -> Tuple[int, str, str]:
    """运行一段 PowerShell 脚本（-File 方式，UTF-8 BOM 兼容 PS 5.1）。

    约定：脚本开头应设置 `[Console]::OutputEncoding = [Text.Encoding]::UTF8`，
    调用方按 UTF-8 解码 stdout。子进程不弹出控制台窗口。
    """
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".ps1", delete=False, encoding="utf-8-sig", dir=tempfile.gettempdir()
        ) as f:
            f.write(script)
            tmp_path = f.name
        argv = [
            "powershell.exe", "-NoProfile", "-NonInteractive",
            "-ExecutionPolicy", "Bypass", "-File", tmp_path,
        ]
        proc = subprocess.run(
            argv, capture_output=True, timeout=timeout, creationflags=_NO_WINDOW
        )
        out = proc.stdout.decode("utf-8", errors="replace")
        err = proc.stderr.decode("utf-8", errors="replace")
        return proc.returncode, out, err
    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
