# ESAM - Installation du serveur de derushage (Windows 11)
# Clic droit sur ce fichier > "Executer avec PowerShell".
# Verifie Python et ffmpeg, cree la tache de demarrage automatique, lance le serveur.

$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
Write-Host "Installation du derushage ESAM depuis $here" -ForegroundColor Cyan

# 1. Python
$py = Get-Command pythonw -ErrorAction SilentlyContinue
if (-not $py) {
    Write-Host "Python absent : installation via winget..." -ForegroundColor Yellow
    winget install --id Python.Python.3.12 -e --accept-package-agreements --accept-source-agreements
    $env:Path = [Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [Environment]::GetEnvironmentVariable("Path","User")
    $py = Get-Command pythonw -ErrorAction SilentlyContinue
    if (-not $py) { Write-Host "Fermez cette fenetre et relancez l'installation (Python vient d'etre installe)." -ForegroundColor Red; Read-Host "Entree pour fermer"; exit 1 }
}
Write-Host "Python : $($py.Source)"

# 2. ffmpeg
if (-not (Get-Command ffmpeg -ErrorAction SilentlyContinue)) {
    Write-Host "ffmpeg absent : installation via winget..." -ForegroundColor Yellow
    winget install --id Gyan.FFmpeg -e --accept-package-agreements --accept-source-agreements
    Write-Host "ffmpeg installe. Fermez cette fenetre et relancez l'installation pour qu'il soit pris en compte." -ForegroundColor Yellow
    Read-Host "Entree pour fermer"; exit 0
}
Write-Host "ffmpeg : $((Get-Command ffmpeg).Source)"

# 3. Dossier des rushs
if (-not (Test-Path "$here\config.json")) { Copy-Item "$here\config.exemple.json" "$here\config.json" }
$cfg = Get-Content "$here\config.json" -Raw | ConvertFrom-Json
if (-not (Test-Path $cfg.dossier_rushs)) {
    Write-Host "Dossier des rushs introuvable : $($cfg.dossier_rushs)" -ForegroundColor Red
    Write-Host "Ouvrez config.json, corrigez 'dossier_rushs' (barres obliques /), enregistrez, puis relancez."
    Read-Host "Entree pour fermer"; exit 1
}

# 4. Tache planifiee a l'ouverture de session
$action   = New-ScheduledTaskAction -Execute $py.Source -Argument "`"$here\server.py`"" -WorkingDirectory $here
$trigger  = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit ([TimeSpan]::Zero) -RestartCount 5 -RestartInterval (New-TimeSpan -Minutes 1)
Register-ScheduledTask -TaskName "ESAM Derushage" -Action $action -Trigger $trigger -Settings $settings -Force | Out-Null
Stop-ScheduledTask -TaskName "ESAM Derushage" -ErrorAction SilentlyContinue
Start-ScheduledTask -TaskName "ESAM Derushage"
Start-Sleep -Seconds 3

try {
    $s = Invoke-RestMethod "http://127.0.0.1:$($cfg.port)/api/status"
    Write-Host "Serveur en marche. Encodage NVIDIA : $($s.gpu)" -ForegroundColor Green
} catch {
    Write-Host "Le serveur ne repond pas. Consultez derushage.log dans $here" -ForegroundColor Red
}

# 5. Tailscale
if (Get-Command tailscale -ErrorAction SilentlyContinue) {
    Write-Host "Publication HTTPS sur votre reseau Tailscale..."
    tailscale serve --bg $cfg.port
    tailscale serve status
} else {
    Write-Host "Tailscale non installe : voir l'etape 4 du guide." -ForegroundColor Yellow
}
Read-Host "Termine. Entree pour fermer"
