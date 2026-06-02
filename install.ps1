# ╔═══════════════════════════════════════════╗
# ║   Runit - One-Click Installer            ║
# ║   Windows (PowerShell)                   ║
# ╚═══════════════════════════════════════════╝

Write-Host ""
Write-Host "  ╔══════════════════════════════════════╗" -ForegroundColor Cyan
Write-Host "  ║       ⚡ Runit Installer             ║" -ForegroundColor Cyan
Write-Host "  ║  AI-Powered Repo Execution Agent     ║" -ForegroundColor Cyan
Write-Host "  ╚══════════════════════════════════════╝" -ForegroundColor Cyan
Write-Host ""

# ── Check Python ──
$python = $null
foreach ($cmd in @("python3", "python")) {
    try {
        $ver = & $cmd --version 2>&1
        if ($ver -match "(\d+)\.\d+") {
            if ([int]$Matches[1] -ge 3) {
                $python = $cmd
                break
            }
        }
    } catch {}
}

if (-not $python) {
    Write-Host "  ✗ Python 3 not found." -ForegroundColor Red
    Write-Host "  Install it: https://python.org/downloads/"
    exit 1
}
Write-Host "  $([char]0x2705) Python: $(& $python --version)"

# ── Check pip ──
try {
    & $python -m pip --version 2>&1 | Out-Null
} catch {
    Write-Host "  ⚠ pip not found, installing..." -ForegroundColor Yellow
    try {
        & $python -c "import urllib.request; exec(urllib.request.urlopen('https://bootstrap.pypa.io/get-pip.py').read())"
    } catch {
        Write-Host "  ✗ Failed to install pip. Install Python with pip from https://python.org/downloads/" -ForegroundColor Red
        exit 1
    }
}
Write-Host "  $([char]0x2705) pip ready"

# ── Install ──
Write-Host ""
Write-Host "  Installing Runit..." -ForegroundColor White
& $python -m pip install rich requests -q

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
& $python -m pip install "$scriptDir" -q

Write-Host "  $([char]0x2705) Runit installed!"

# ── Verify ──
try {
    & runit --version 2>&1 | Out-Null
    Write-Host "  $([char]0x2705) runit command available"
} catch {
    $userSite = & $python -c "import site; print(site.USER_BASE)"
    $userScripts = Join-Path $userSite "Scripts"
    $localScripts = Join-Path $env:LOCALAPPDATA "Programs\Python\Python*\Scripts"
    Write-Host "  ℹ Add to PATH: $userScripts" -ForegroundColor Yellow
    $env:Path += ";$userScripts"
}

Write-Host ""
Write-Host "  ✔ Installation complete!" -ForegroundColor Green
Write-Host ""
Write-Host "  Quick Start:" -ForegroundColor White
Write-Host "    runit --setup              # Configure your API key" -ForegroundColor Yellow
Write-Host "    runit --skills             # View agent skills" -ForegroundColor Yellow
Write-Host "    runit <repo-url>           # Run a GitHub repo" -ForegroundColor Yellow
Write-Host "    runit .                    # Run current folder" -ForegroundColor Yellow
Write-Host ""

$choice = Read-Host "  🔑 Configure AI provider now? (Y/n)"
if ($choice -eq "" -or $choice -eq "y" -or $choice -eq "Y") {
    & runit --setup
}
