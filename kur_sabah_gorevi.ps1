# Her iş günü 08:00'de sabah raporu üret (+ e-posta, ayarlıysa)
# Kurulum (PowerShell, yönetici gerekmez):
#   Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
#   .\kur_sabah_gorevi.ps1
# Kaldır:
#   .\kur_sabah_gorevi.ps1 -Remove

param(
    [switch]$Remove,
    [switch]$WithEmail,
    [string]$Time = "08:00"
)

$TaskName = "YanalizSabahRaporu"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Python = Join-Path $Root ".venv\Scripts\python.exe"
$Script = Join-Path $Root "sabah_raporu.py"

if ($Remove) {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
    Write-Host "Gorev kaldirildi: $TaskName"
    exit 0
}

if (-not (Test-Path $Python)) {
    Write-Host "Once calistir.bat ile .venv kur."
    exit 1
}

$args = "`"$Script`""
if ($WithEmail) {
    $args = "`"$Script`" --email"
}

$Action = New-ScheduledTaskAction -Execute $Python -Argument $args -WorkingDirectory $Root
$Trigger = New-ScheduledTaskTrigger -Daily -At $Time
# Hafta ici: Pazartesi-Cuma (1=Pazar ... 6=Cuma 7=Cumartesi) — Daily yeterli; tatil filtre yok
$Settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $Action `
    -Trigger $Trigger `
    -Settings $Settings `
    -Description "Yanaliz sabah brifingi ve portfoy emirleri" `
    -Force | Out-Null

Write-Host "Gorev kuruldu: $TaskName her gun $Time"
Write-Host "Test: $Python $Script"
if ($WithEmail) {
    Write-Host "E-posta acik — .streamlit\secrets.toml icinde [smtp] olmali."
} else {
    Write-Host "Sadece dosya: data\sabah_raporu_son.txt"
    Write-Host "E-posta icin: .\kur_sabah_gorevi.ps1 -WithEmail"
}
