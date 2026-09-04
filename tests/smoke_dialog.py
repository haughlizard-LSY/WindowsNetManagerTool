"""对话框冒烟测试：offscreen 构造档案编辑对话框并做静态校验。"""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtWidgets import QApplication  # noqa: E402

from nicmanager.gui.profile_dialog import ProfileDialog  # noqa: E402
from nicmanager.models import Profile  # noqa: E402

LOG = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".tmp_db", "dialog_smoke.log")
os.makedirs(os.path.dirname(LOG), exist_ok=True)


def log(msg):
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(msg + "\n")


def main():
    app = QApplication(sys.argv)
    # 新建静态
    dlg = ProfileDialog(adapter_name="以太网", existing_names=["已有"])
    assert dlg.rb_static.isChecked()
    assert dlg.edt_ip.isEnabled()
    dlg.edt_name.setText("测试档案")
    dlg.edt_ip.setText("192.168.1.50")
    dlg.edt_gateway.setText("192.168.1.1")
    dlg.edt_dns1.setText("223.5.5.5")
    dlg._on_accept()  # noqa: SLF001
    p = dlg.result_profile()
    assert p is not None and p.mode == "static" and p.ip == "192.168.1.50"
    log(f"static dialog ok: {p.summary()}")

    # 新建 DHCP
    dlg2 = ProfileDialog(adapter_name="WLAN", existing_names=[])
    dlg2.rb_dhcp.setChecked(True)
    dlg2.edt_name.setText("DHCP档案")
    dlg2.edt_ip.setText("bad-ip")  # DHCP 下应忽略
    dlg2._on_accept()  # noqa: SLF001
    p2 = dlg2.result_profile()
    assert p2 is not None and p2.mode == "dhcp"
    log(f"dhcp dialog ok: {p2.summary()}")

    # 编辑已有
    src = Profile(adapter_name="以太网", name="旧", mode="static", ip="10.0.0.9", prefix=16,
                  gateway="10.0.0.1", dns1="114.114.114.114")
    dlg3 = ProfileDialog(profile=src, adapter_name="以太网", existing_names=["其它"])
    assert dlg3.edt_name.text() == "旧"
    assert dlg3.edt_ip.text() == "10.0.0.9"
    assert dlg3.cmb_prefix.currentData() == 16
    log("edit dialog prefill ok")

    # 名称重复校验（应弹出 QMessageBox——offscreen 下用 monkeypatch 跳过）
    from PySide6.QtWidgets import QMessageBox
    orig = QMessageBox.warning
    QMessageBox.warning = staticmethod(lambda *a, **k: QMessageBox.Ok)
    dlg4 = ProfileDialog(adapter_name="以太网", existing_names=["重复名"])
    dlg4.edt_name.setText("重复名")
    dlg4.edt_ip.setText("1.1.1.1")
    dlg4._on_accept()  # noqa: SLF001
    assert dlg4.result_profile() is None
    QMessageBox.warning = orig
    log("duplicate name rejected ok")

    print("DIALOG_SMOKE_DONE")
    return 0


if __name__ == "__main__":
    sys.exit(main())
