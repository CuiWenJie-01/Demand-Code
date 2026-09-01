[CmdletBinding()]
param(
    [string]$Python = (Join-Path $PSScriptRoot "..\..\.venv-ocr\Scripts\python.exe")
)

$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$sidecarName = "pdf2word-worker-x86_64-pc-windows-msvc"

if (-not (Test-Path -LiteralPath $Python)) {
    throw "找不到 OCR 虚拟环境 Python：$Python"
}

Push-Location $projectRoot
try {
    & $Python -m PyInstaller `
        --noconfirm `
        --clean `
        --onefile `
        --name $sidecarName `
        --paths src `
        --distpath desktop\src-tauri\binaries `
        --workpath tmp\pyinstaller-build `
        --specpath tmp\pyinstaller-spec `
        src\pdf2word_worker.py
    if ($LASTEXITCODE -ne 0) {
        throw "sidecar 打包失败，退出码：$LASTEXITCODE"
    }
}
finally {
    Pop-Location
}
