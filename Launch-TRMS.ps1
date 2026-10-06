param([int]$Port = 8765)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$trmsPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
$trmsWorkingPython = $false
if (Test-Path -LiteralPath $trmsPython) {
    & $trmsPython -c 'import django' 2>$null
    $trmsWorkingPython = ($LASTEXITCODE -eq 0)
}
if (-not $trmsWorkingPython) {
    $trmsPython = Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
    $trmsPackages = Join-Path $PSScriptRoot '.venv\Lib\site-packages'
    if (-not (Test-Path -LiteralPath $trmsPython)) { throw 'Python is unavailable. Create a Python environment and install requirements.txt.' }
    if (-not (Test-Path -LiteralPath (Join-Path $trmsPackages 'django'))) {
        $trmsPackages = Join-Path $env:USERPROFILE 'Desktop\TRMS APP\TRMS\.venv\Lib\site-packages'
    }
    if (-not (Test-Path -LiteralPath (Join-Path $trmsPackages 'django'))) { throw 'Django is unavailable. Install requirements.txt in a Python environment.' }
    $env:PYTHONPATH = $trmsPackages
}
& $trmsPython manage.py check
if ($LASTEXITCODE -ne 0) { throw 'TRMS system checks failed.' }
Write-Host "Open http://127.0.0.1:$Port/ in your browser. Press Ctrl+C to stop TRMS."
& $trmsPython manage.py runserver "127.0.0.1:$Port" --noreload
