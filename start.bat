@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ================================================
echo   紙芝居動画ジェネレーター 起動中...
echo ================================================
echo.

REM 仮想環境の存在確認
if not exist .venv (
    echo [エラー] 仮想環境が見つかりません。
    echo   先に install.bat を実行してください。
    echo.
    pause
    exit /b 1
)

REM Google Cloud TTS認証（サービスアカウントキーがある場合）
if exist gcp-key.json (
    set GOOGLE_APPLICATION_CREDENTIALS=%~dp0gcp-key.json
    echo [OK] Google Cloud認証キーを検出しました
)

REM アプリを起動
echo [OK] 仮想環境を検出しました
echo.
echo   ブラウザが自動で開きます。
echo   開かない場合は http://localhost:8501 にアクセスしてください。
echo.
echo   終了するには このウィンドウを閉じるか Ctrl+C を押してください。
echo.
.venv\Scripts\python.exe -m streamlit run app.py
pause


