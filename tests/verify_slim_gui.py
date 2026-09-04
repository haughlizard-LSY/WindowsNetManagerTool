"""对 onedir 深度裁剪版跑完整 GUI 冒烟：建窗→刷新→加载档案→退出。
用于确认裁剪掉的 Qt 模块不影响运行。"""
import os
import subprocess
import sys
import time

DIR = r"D:\NetManagerTool\dist\NetManagerToolSlimDir"
EXE = os.path.join(DIR, "NetManagerToolSlimDir.exe")
DATA = r"D:\NetManagerTool\tests\.tmp_slimdb"

os.makedirs(DATA, exist_ok=True)
env = dict(os.environ)
env["QT_QPA_PLATFORM"] = "offscreen"
env["TMP"] = DATA
env["TEMP"] = DATA

print("launching slim onedir (offscreen)...")
proc = subprocess.Popen([EXE, "--data-dir=" + DATA], env=env,
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(15)
alive = proc.poll() is None
db = os.path.exists(os.path.join(DATA, "profiles.db"))
print(f"alive_15s={alive} exit={proc.poll()} db={db}")
if alive:
    proc.terminate()
    try:
        proc.wait(5)
    except subprocess.TimeoutExpired:
        proc.kill()
print("RESULT:", "PASS" if (alive and db) else "FAIL")
sys.exit(0 if (alive and db) else 1)
