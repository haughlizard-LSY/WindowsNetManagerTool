# 网卡管理器（NetManagerTool）

Windows 本地网卡配置管理工具（Python + PySide6 桌面 GUI）。

## 功能

1. **查看网卡**：列出本机所有网卡（有线/WLAN/虚拟）及其**当前生效配置**——
   连接状态、MAC（PowerShell 通道）、DHCP/静态、IPv4 地址、默认网关、DNS。
2. **多套配置档案**：每块网卡可保存多个命名档案（如"办公室-静态IP"、"家里-DHCP"），
   支持**静态 IP / DHCP 两种模式**，档案本地持久化（SQLite），与 Windows 系统配置分离。
3. **一键切换**：选中网卡 → 选档案 → 「应用选中档案」→ 自动写入系统并生效；
   应用前二次确认，应用失败自动回滚原配置。

## 界面布局

```
┌────────────────────────────────────────────────────────┐
│ 本机网卡            │  当前配置（只读）                     │
│ ┌──────────────┐   │  网卡名称 / 描述 / 连接状态 / MAC      │
│ │ 以太网 [已连接] │   │  DHCP状态 / IPv4 / 网关 / DNS        │
│ │ WLAN   [已连接] │   ├────────────────────────────────────┤
│ │ ...            │   │ 配置档案                             │
│ └──────────────┘   │  [新增档案][编辑][删除] [预览][▶应用][刷新]│
│                    │  ┌──────────────────────────────────┐ │
│                    │  │ 档案名称 | 配置 | 备注             │ │
│                    │  └──────────────────────────────────┘ │
└────────────────────────────────────────────────────────┘
```

## 运行

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 启动（首次会弹出 UAC 请求管理员权限；拒绝则以只读模式运行）
python main.py
```

> 测试用：`python main.py --no-elevate` 可跳过 UAC 提权，直接以当前权限运行。

### 权限说明
- **读操作**（查看网卡/当前配置）不需要管理员权限。
- **写操作**（应用档案）需要管理员权限 → 程序启动时自动请求 UAC 提权；
  若用户拒绝提权，则进入**只读模式**（可查看与编辑档案，但"应用"按钮不可用）。

## 技术实现

| 模块 | 说明 |
|---|---|
| `nicmanager/iputil.py` | IPv4/掩码/前缀校验转换 |
| `nicmanager/models.py` | `AdapterInfo`（网卡快照）、`Profile`（配置档案）模型与校验 |
| `nicmanager/storage.py` | SQLite 持久化（默认 `%APPDATA%\NetManagerTool\profiles.db`） |
| `nicmanager/system/reader.py` | 网卡枚举+当前配置读取。双通道：**PowerShell JSON**（信息全）→ 失败降级 **netsh 文本解析** |
| `nicmanager/system/applier.py` | 应用档案：快照 → 执行 → 校验 → 失败自动回滚；支持 dry-run 预览 |
| `nicmanager/system/elevation.py` | 管理员检测 + UAC 提权重启 |
| `nicmanager/gui/` | PySide6 主窗口、档案编辑对话框、后台线程（QThread） |

### 系统命令路径（Windows）
- 读取（主）：PowerShell `Get-NetAdapter` / `Get-NetIPAddress` / `Get-NetIPConfiguration` / `Get-DnsClientServerAddress`
- 读取（降级）：`netsh interface ipv4 show ...`
- 写入：PowerShell `Set-NetIPInterface -Dhcp`、`New/Remove-NetIPAddress`、`Set-DnsClientServerAddress`

## 测试

```bash
python tests/run.py          # 单元测试（iputil/解析器/存储/应用器）
python tests/smoke_gui.py    # GUI 无头冒烟（offscreen）
python tests/smoke_dialog.py # 档案对话框冒烟
```

## 打包为 exe（PyInstaller，单文件免安装）

**推荐方式：双击 `build_exe.bat`**（自动检查/安装依赖并打包），产物为
`dist\NetManagerTool.exe` —— 单个文件，内含 Python 与 PySide6，
**拷贝到未安装 Python 的 Windows 电脑双击即可运行**（无需安装）。

```bash
# 手动方式：
pip install pyinstaller
python -m PyInstaller --noconfirm --clean --onefile --windowed --uac-admin ^
    --name NetManagerTool --collect-all PySide6 main.py
```

关键参数说明：
- `--onefile`：单文件；首次启动需自解压，慢几秒属正常
- `--windowed`：无黑色控制台窗口
- `--uac-admin`：**双击 exe 直接弹 UAC 并以管理员运行**，保证「应用配置」始终可用
- `--collect-all PySide6`：完整打包 Qt 运行时，避免目标机缺插件

> 注：`--uac-admin` 使 exe 必须经 UAC 同意才能启动（查看也需要）。若希望保留
> "普通权限可只读查看"模式，去掉该参数再打包即可，此时非管理员只能查看/建档。
> 杀毒软件对 PyInstaller 产物偶有误报，添加信任即可。

## 已知限制

- 目标平台为 Windows（Win10/11 验证环境）；PowerShell 通道依赖系统模块 NetTCPIP。
- 档案以**网卡名称**为绑定键；Windows 重装/网卡改名后，可在后续版本提供"迁移到新网卡"入口。
- 当前仅管理 **IPv4**；IPv6 仅展示链路本地地址。
- 静态档案含多地址/多网关等高级场景不在 v0.1 覆盖范围。
- netsh 降级通道不提供 MAC/描述（PowerShell 通道提供）。
