# Her is gunu 08:00'de sabah raporu uret (+ e-posta, ayarliysa)
# Kurulum:
#   Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
#   .\kur_sabah_gorevi.ps1
# Simdi dene:
#   .\kur_sabah_gorevi.ps1 -RunNow
# Kaldir:
#   .\kur_sabah_gorevi.ps1 -Remove

param(
    [switch]$Remove,
    [switch]$WithEmail,
    [switch]$RunNow,
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

if ($RunNow) {
    Write-Host "Simdi calistiriliyor..."
    $argList = @($Script)
    if ($WithEmail) { $argList += "--email" }
    $argList += "--print"
    & $Python @argList
    exit $LASTEXITCODE
}

$argLine = "`"$Script`""
if ($WithEmail) {
    $argLine = "`"$Script`" --email"
}

$Action = New-ScheduledTaskAction -Execute $Python -Argument $argLine -WorkingDirectory $Root
$Trigger = New-ScheduledTaskTrigger -Daily -At $Time
$Settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $Action `
    -Trigger $Trigger `
    -Settings $Settings `
    -Description "Yanaliz sabah brifingi: 3 maddelik aksiyon + portfoy emirleri" `
    -Force | Out-Null

Write-Host "Gorev kuruldu: $TaskName her gun $Time"
Write-Host "Simdi dene: .\kur_sabah_gorevi.ps1 -RunNow"
if ($WithEmail) {
    Write-Host "E-posta acik - .streamlit\secrets.toml icinde [smtp] olmali."
} else {
    Write-Host "Sadece dosya: data\sabah_raporu_son.txt"
    Write-Host "E-posta icin: .\kur_sabah_gorevi.ps1 -WithEmail"
}
