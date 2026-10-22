# Run on a disposable Windows Actions runner after building the shipping NSIS installer.
$ErrorActionPreference = 'Stop'
if ($env:RUNNER_OS -ne 'Windows') { throw 'This gate requires a Windows Actions runner.' }
$repo = Split-Path -Parent $PSScriptRoot
$desktop = Join-Path $repo 'electron'
$installers = @(Get-ChildItem (Join-Path $desktop 'dist/*.exe') -File)
if ($installers.Count -ne 1) { throw "Expected one NSIS installer, found $($installers.Count)." }
$installer = $installers[0]
$installDir = Join-Path $env:RUNNER_TEMP ("stellaris-installed-" + [guid]::NewGuid())
$proof = Join-Path $desktop 'packaged-windows-proof'
New-Item -ItemType Directory -Force $proof | Out-Null
$install = Start-Process -FilePath $installer.FullName -ArgumentList @('/S', '/currentuser', "/D=$installDir") -Wait -PassThru
if ($install.ExitCode -ne 0) { throw "Installer failed with exit code $($install.ExitCode)." }
$executable = Join-Path $installDir 'Stellaris Companion.exe'
foreach ($file in @($executable, (Join-Path $installDir 'resources/app.asar'), (Join-Path $installDir 'resources/python-backend/stellaris-backend.exe'))) {
  if (!(Test-Path $file -PathType Leaf)) { throw "Installed resource missing: $file" }
}
@{ installer = $installer.Name; sha256 = (Get-FileHash $installer.FullName -Algorithm SHA256).Hash;
   executable = $executable; installedAt = (Get-Date).ToUniversalTime().ToString('o') } |
  ConvertTo-Json | Set-Content (Join-Path $proof 'installer.json')
$env:E2E_EXECUTABLE_PATH = $executable
$env:PLAYWRIGHT_JSON_OUTPUT_NAME = Join-Path $proof 'results.json'
Push-Location $desktop
try {
  & node node_modules/@playwright/test/cli.js test e2e/packaged-windows.spec.js e2e/response-completeness.spec.js e2e/feedback-capture.spec.js --reporter=list,json
  if ($LASTEXITCODE -ne 0) { throw "Installed Windows journeys failed with exit code $LASTEXITCODE." }
} finally {
  Pop-Location
  Remove-Item Env:E2E_EXECUTABLE_PATH -ErrorAction SilentlyContinue
}
