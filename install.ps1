param([switch]$Check, [switch]$PrepareOnly, [switch]$NoStart, [switch]$NoService,
      [string]$InstallRoot = "$env:LOCALAPPDATA\YandexStationTelegramBot", [string]$Answers = '')
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [Text.UTF8Encoding]::new()
$env:PYTHONUTF8 = '1'
if (-not (Test-Path -LiteralPath (Join-Path $PSScriptRoot 'bundle.json'))) { throw 'Download and extract the installer ZIP from GitHub Releases. The source checkout does not contain binary payloads.' }
function Refresh-Tools {
    $env:Path = [Environment]::GetEnvironmentVariable('Path','Machine') + ';' + [Environment]::GetEnvironmentVariable('Path','User')
    $extra = @("$env:LOCALAPPDATA\Microsoft\WindowsApps", "$env:LOCALAPPDATA\Microsoft\WinGet\Links", "$env:ProgramFiles\eSpeak NG")
    if (Test-Path -LiteralPath "$env:ProgramFiles\eSpeak NG") {
        $extra += Get-ChildItem -LiteralPath "$env:ProgramFiles\eSpeak NG" -Filter espeak-ng.exe -File -Recurse | ForEach-Object DirectoryName
    }
    $packages = "$env:LOCALAPPDATA\Microsoft\WinGet\Packages"
    if (Test-Path -LiteralPath $packages) {
        $extra += Get-ChildItem -LiteralPath $packages -Directory | Where-Object Name -Like 'Google.PlatformTools_*' | ForEach-Object { Join-Path $_.FullName 'platform-tools' }
        $extra += Get-ChildItem -LiteralPath $packages -Directory | Where-Object Name -Like 'Gyan.FFmpeg_*' | ForEach-Object { Get-ChildItem -LiteralPath $_.FullName -Directory | ForEach-Object { Join-Path $_.FullName 'bin' } }
    }
    $env:Path = ($extra + $env:Path) -join ';'
}
function Install-Dependency($Command, $Package) {
    if (-not (Get-Command $Command -ErrorAction SilentlyContinue)) {
        if ($Check) { throw "Missing dependency: $Command" }
        if (-not (Get-Command winget -ErrorAction SilentlyContinue)) { throw 'Install Microsoft App Installer (winget), then run install.cmd again.' }
        & winget install --id $Package --exact --source winget --silent --accept-package-agreements --accept-source-agreements --no-upgrade
        if ($LASTEXITCODE -ne 0 -and $LASTEXITCODE -ne -1978335189) { throw "Dependency installation failed: $Package" }
        Refresh-Tools
        if (-not (Get-Command $Command -ErrorAction SilentlyContinue)) { throw "Package installed but executable not found: $Command" }
    }
}
Refresh-Tools
$python = "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe"
if (-not (Test-Path -LiteralPath $python)) {
    if ($Check) { $python = (Get-Command python -ErrorAction Stop).Source }
    else {
        & winget install --id Python.Python.3.12 --exact --source winget --scope user --silent --accept-package-agreements --accept-source-agreements --no-upgrade
        if ($LASTEXITCODE -ne 0 -and $LASTEXITCODE -ne -1978335189) { throw 'Python installation failed' }
        if (-not (Test-Path -LiteralPath $python)) { throw 'Python 3.12 executable not found' }
    }
}
Install-Dependency adb Google.PlatformTools
Install-Dependency ffmpeg Gyan.FFmpeg
Install-Dependency espeak-ng eSpeak-NG.eSpeak-NG
$options = @('--root', $InstallRoot, '--bundle', $PSScriptRoot)
if ($Check) { $options += '--check' }
if ($PrepareOnly) { $options += '--prepare-only' }
if ($NoStart) { $options += '--no-start' }
if ($NoService) { $options += '--no-service' }
if ($Answers) { $options += @('--answers', $Answers) }
& $python (Join-Path $PSScriptRoot 'deploy\bootstrap.py') @options
exit $LASTEXITCODE
