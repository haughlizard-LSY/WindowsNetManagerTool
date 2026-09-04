"""elevation 模块单元测试：验证 relaunch_elevated 的参数构造正确性。

不真正触发 UAC；通过 monkeypatch ShellExecuteW 捕获 (lpFile, lpParameters)。
"""
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from nicmanager.system import elevation  # noqa: E402


class TestElevation(unittest.TestCase):
    def test_params_exclude_interpreter_path(self):
        """核心修复点：lpParameters 只含脚本+参数，不能包含解释器自身路径。"""
        called = {}

        with mock.patch.object(
            elevation.ctypes.windll.shell32, "ShellExecuteW",
            side_effect=lambda *a, **k: called.update(args=a) or 42,  # >32 成功
        ):
            with mock.patch.object(elevation, "_gui_interpreter", return_value=r"C:\py\pythonw.exe"):
                with mock.patch.object(elevation.os.path, "abspath", return_value=r"D:\proj\main.py"):
                    with mock.patch.object(elevation.subprocess, "list2cmdline", side_effect=lambda parts: " ".join(f'"{p}"' for p in parts)):
                        with mock.patch.object(elevation.sys, "argv", ["main.py"]):
                            ok = elevation.relaunch_elevated(["--elevated"])

        self.assertTrue(ok)
        # args = (hwnd, op, lpFile, lpParameters, lpDirectory, nShowCmd)
        lp_file, lp_params = called["args"][2], called["args"][3]
        self.assertEqual(lp_file, r"C:\py\pythonw.exe")
        # 关键断言：参数里绝不能以 pythonw.exe 开头（否则 python 会把它当脚本）
        self.assertNotIn("pythonw.exe", lp_params)
        self.assertIn("main.py", lp_params)
        self.assertIn("--elevated", lp_params)
        # lpParameters 恰好 = "脚本" + args
        self.assertEqual(lp_params, '"D:\\proj\\main.py" "--elevated"')

    def test_frozen_uses_exe_only_in_file(self):
        called = {}
        with mock.patch.object(elevation.ctypes.windll.shell32, "ShellExecuteW",
                               side_effect=lambda *a, **k: called.update(args=a) or 42):
            with mock.patch.object(elevation, "_gui_interpreter", return_value=r"C:\bin\MyApp.exe"):
                with mock.patch.object(elevation.subprocess, "list2cmdline",
                                       side_effect=lambda parts: " ".join(f'"{p}"' for p in parts)):
                    with mock.patch.object(elevation.sys, "frozen", True, create=True):
                        with mock.patch.object(elevation.sys, "executable", r"C:\bin\MyApp.exe"):
                            ok = elevation.relaunch_elevated(["--elevated"])
        self.assertTrue(ok)
        lp_file, lp_params = called["args"][2], called["args"][3]
        self.assertEqual(lp_file, r"C:\bin\MyApp.exe")
        self.assertEqual(lp_params, '"--elevated"')

    def test_gui_interpreter_prefers_pythonw(self):
        with mock.patch.object(elevation.os.path, "exists", return_value=True):
            with mock.patch.object(elevation.sys, "executable", r"C:\py\python.exe"):
                self.assertEqual(elevation._gui_interpreter(), r"C:\py\pythonw.exe")

    def test_gui_interpreter_fallback(self):
        with mock.patch.object(elevation.os.path, "exists", return_value=False):
            with mock.patch.object(elevation.sys, "executable", r"C:\py\python.exe"):
                self.assertEqual(elevation._gui_interpreter(), r"C:\py\python.exe")

    def test_failed_launch_returns_false(self):
        with mock.patch.object(elevation.ctypes.windll.shell32, "ShellExecuteW", return_value=0):  # ≤32 失败
            with mock.patch.object(elevation.sys, "frozen", True, create=True):
                with mock.patch.object(elevation.sys, "executable", r"C:\bin\MyApp.exe"):
                    self.assertFalse(elevation.relaunch_elevated())


if __name__ == "__main__":
    unittest.main()
