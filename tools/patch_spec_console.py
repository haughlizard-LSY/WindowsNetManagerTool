"""Patch slim dir spec: console diag build SlimDirDiag."""
import pathlib

spec = pathlib.Path(__file__).resolve().parent.parent / "nicmanager_slim_dir.spec"
t = spec.read_text(encoding="utf-8")
t = t.replace("name='NetManagerToolSlimDir'", "name='SlimDirDiag'")
t = t.replace("console=False", "console=True")
spec.write_text(t, encoding="utf-8")
print("patched to SlimDirDiag console build")
