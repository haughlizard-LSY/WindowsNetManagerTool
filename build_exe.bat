@echo off
rem ============================================================
rem  NetManagerTool - Windows one-file build script
rem  Double-click to run. Output: dist\NetManagerTool.exe
rem  The exe bundles Python + PySide6, runs on machines
rem  without Python installed.
rem ============================================================
setlocal

cd /d "%~dp0"

echo.
echo ============================================================
echo   Building NetManagerTool.exe
echo ============================================================
echo.

rem ---------- 1. locate python ----------
where python >nul 2>nul
if errorlevel 1 (
    echo [ERROR] python not found. Install Python 3.10+ and add it to PATH.
    pause
    exit /b 1
)

rem ---------- 2. ensure dependencies ----------
echo [1/4] Checking dependencies (PySide6, PyInstaller) ...
python -c "import PySide6" >nul 2>nul
if errorlevel 1 (
    echo   - installing PySide6...
    python -m pip install PySide6 -i https://pypi.tuna.tsinghua.edu.cn/simple
    if errorlevel 1 (
        echo [ERROR] PySide6 install failed. Check your network and retry.
        pause
        exit /b 1
    )
)
python -m PyInstaller --version >nul 2>nul
if errorlevel 1 (
    echo   - installing PyInstaller...
    python -m pip install pyinstaller -i https://pypi.tuna.tsinghua.edu.cn/simple
    if errorlevel 1 (
        echo [ERROR] PyInstaller install failed. Run manually:
        echo         python -m pip install pyinstaller
        pause
        exit /b 1
    )
)

rem ---------- 3. optional icon ----------
set "ICON="
if exist icon.ico set "ICON=--icon=icon.ico"

rem ---------- 4. run PyInstaller ----------
echo [2/4] PyInstaller building one-file exe (takes a few minutes)...
echo.
rem --uac-admin : exe asks UAC on launch and runs as ADMIN,
rem               so "Apply profile" always works.
rem --windowed  : no console window.
python -m PyInstaller ^
    --noconfirm ^
    --clean ^
    --onefile ^
    --windowed ^
    --uac-admin ^
    --name "NetManagerTool" ^
    --collect-all PySide6 ^
    %ICON% ^
    main.py
if errorlevel 1 (
    echo [ERROR] Build failed. See messages above.
    pause
    exit /b 1
)

rem ---------- 5. done ----------
echo.
echo [3/4] BUILD OK
echo   - exe: %cd%\dist\NetManagerTool.exe
echo   - Copy this single exe to any Windows PC and double-click it.
echo     Python is NOT required on the target machine.
echo.
echo [4/4] USAGE
echo   - Launching the exe triggers a UAC prompt. Click Yes to run as
echo     administrator (needed to apply network profiles).
echo   - First start extracts bundled files, may take a few seconds.
echo   - If antivirus flags it, add an exclusion.
echo.
pause
endlocal
