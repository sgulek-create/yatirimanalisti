@echo off
setlocal
cd /d "%~dp0"

netstat -ano | findstr ":8502" | findstr "LISTENING" >nul
if %errorlevel%==0 (
    echo Uygulama zaten acik: http://localhost:8502
    start "" "http://localhost:8502"
    exit /b 0
)

if not exist ".venv\Scripts\python.exe" (
    echo Sanal ortam olusturuluyor...
    python -m venv .venv
    if errorlevel 1 (
        echo Python bulunamadi. python.org adresinden Python 3.11+ kur.
        pause
        exit /b 1
    )
)

echo Bagimliliklar kontrol ediliyor...
".venv\Scripts\python.exe" -m pip install -q --upgrade pip
".venv\Scripts\python.exe" -m pip install -q -r requirements.txt
if errorlevel 1 (
    echo Paket kurulumu basarisiz.
    pause
    exit /b 1
)

echo Streamlit aciliyor: http://localhost:8502
".venv\Scripts\python.exe" -m streamlit run streamlit_app.py
endlocal
