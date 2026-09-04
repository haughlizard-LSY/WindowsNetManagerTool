"""验证打包 exe 能真实启动：启动 NMTVerify.exe（无 UAC 版），
等待解压+窗口出现，检查进程存活与数据目录创建。"""
import os
import subprocess
import sys
import time

EXE = r"D:\NetManagerTool\dist\NMTVerify.exe"
DATA = r"D:\NetManagerTool\tests\.tmp_exe_data"

sys.stdout.reconfigure(encoding="utf-8")


def main():
    if not os.path.exists(EXE):
        print("EXE missing:", EXE)
        return 1
    os.makedirs(DATA, exist_ok=True)
    env = dict(os.environ)
    env["QT_QPA_PLATFORM"] = "offscreen"  # 无头验证：只要能进事件循环即证明打包可用

    print("starting exe (offscreen)...")
    proc = subprocess.Popen(
        [EXE, "--elevated", f"--data-dir={DATA}"],
        env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    time.sleep(12)  # onefile 首次解压较慢
    alive = proc.poll() is None
    db_created = os.path.exists(os.path.join(DATA, "profiles.db"))
    print(f"alive_after_12s={alive}  exit_code={proc.poll()}  db_created={db_created}")
    if alive:
        proc.terminate()
        try:
            proc.wait(5)
        except subprocess.TimeoutExpired:
            proc.kill()
    print("RESULT:", "PASS" if (alive and db_created) else "FAIL")
    return 0 if (alive and db_created) else 1


if __name__ == "__main__":
    sys.exit(main())
