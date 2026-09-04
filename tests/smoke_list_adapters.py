import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout.reconfigure(encoding="utf-8")
from nicmanager.system.reader import read_adapters

ads, ch = read_adapters()
print("channel:", ch, "count:", len(ads))
for a in ads:
    print(f"{a.index:>3} {a.name:<28} {a.status:<14} dhcp={str(a.dhcp_enabled):<5} ipv4={a.ipv4_label}")
