$ErrorActionPreference = "Stop"

Write-Host "Building Job Matcher desktop executable..."

$python = ".\.venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    $python = "python"
}

$pythonBase = (& $python -c "import sys; print(sys.base_prefix)").Trim()
$pythonLib = Join-Path $pythonBase "Lib"
$pythonDlls = Join-Path $pythonBase "DLLs"
$pythonTcl = Join-Path $pythonBase "tcl"
$env:TCL_LIBRARY = Join-Path $pythonTcl "tcl8.6"
$env:TK_LIBRARY = Join-Path $pythonTcl "tk8.6"

& $python -m PyInstaller `
    --noconfirm `
    --clean `
    --windowed `
    --name "JobMatcherApp" `
    --icon "assets\jobmatcher.ico" `
    --collect-data "customtkinter" `
    --hidden-import "darkdetect" `
    --hidden-import "tkinter" `
    --hidden-import "_tkinter" `
    --add-binary "$pythonDlls\_tkinter.pyd;." `
    --add-binary "$pythonDlls\tcl86t.dll;." `
    --add-binary "$pythonDlls\tk86t.dll;." `
    --add-data "$pythonLib\tkinter;tkinter" `
    --add-data "$pythonTcl\tcl8.6;_tcl_data" `
    --add-data "$pythonTcl\tk8.6;_tk_data" `
    --add-data "config;config" `
    --add-data "core;core" `
    --add-data "scrapers;scrapers" `
    --add-data "notifier;notifier" `
    --add-data "assets\jobmatcher-icon.png;assets" `
    --add-data "assets\jobmatcher.ico;assets" `
    app_desktop.py

Write-Host ""
Write-Host "Done. Executable:"
Write-Host "dist\JobMatcherApp\JobMatcherApp.exe"
