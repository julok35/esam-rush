# ESAM - Mise a jour du serveur de derushage depuis GitHub
# Clic droit sur ce fichier > "Executer avec PowerShell".
# Attention : un calcul en cours (preparation, video) est interrompu.

$here = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $here
Write-Host "Recuperation de la derniere version..." -ForegroundColor Cyan
git pull --ff-only
if ($LASTEXITCODE -ne 0) {
    Write-Host "Mise a jour impossible : un fichier du programme a ete modifie sur ce PC." -ForegroundColor Red
    Write-Host "Tapez 'git status' dans ce dossier pour voir lequel (config.json n'est pas concerne)."
    Read-Host "Entree pour fermer"; exit 1
}
Stop-ScheduledTask -TaskName "ESAM Derushage" -ErrorAction SilentlyContinue
Start-Sleep -Seconds 2
Start-ScheduledTask -TaskName "ESAM Derushage"
Start-Sleep -Seconds 3
$cfg = Get-Content "$here\config.json" -Raw | ConvertFrom-Json
try {
    $s = Invoke-RestMethod "http://127.0.0.1:$($cfg.port)/api/status"
    Write-Host "Serveur redemarre, version $($s.version)." -ForegroundColor Green
} catch {
    Write-Host "Le serveur ne repond pas. Consultez derushage.log dans $here" -ForegroundColor Red
}
Read-Host "Termine. Entree pour fermer"
