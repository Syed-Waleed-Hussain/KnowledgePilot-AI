# Focused offline acceptance checks; uses the existing venv and synthetic storage.
$ErrorActionPreference = 'Stop'
$demoRoot = Split-Path $PSScriptRoot -Parent
$oldStorage = $env:KNOWLEDGEPILOT_STORAGE_PATH
$oldRl = $env:RL_MODE
Push-Location $demoRoot
try {
    $env:KNOWLEDGEPILOT_STORAGE_PATH = Join-Path ([IO.Path]::GetTempPath()) ('kp-demo-' + [guid]::NewGuid().ToString('N'))
    $env:RL_MODE = 'off'
    & .\backend\.venv\Scripts\python.exe -m pytest tests/test_stabilization.py tests/test_phase76.py tests/test_phase7.py tests/test_phase6.py backend/tests/test_supabase_auth.py -q --tb=short
    if ($LASTEXITCODE -ne 0) { throw 'Backend checks failed.' }
    Set-Location frontend
    node test-phase7.mjs
    if ($LASTEXITCODE -ne 0) { throw 'Frontend checks failed.' }
    node --test test-auth.mjs
    if ($LASTEXITCODE -ne 0) { throw 'Auth check failed.' }
    npm run build
    if ($LASTEXITCODE -ne 0) { throw 'Production build failed.' }
    Write-Host 'Focused checks passed. Live login, PDF/provider and MCP transport acceptance remain manual.'
} finally {
    $env:KNOWLEDGEPILOT_STORAGE_PATH = $oldStorage
    $env:RL_MODE = $oldRl
    Pop-Location
}
