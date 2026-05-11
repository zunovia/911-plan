@echo off
chcp 65001 >nul
cd /d "%~dp0"
title Kamishibai Studio

echo.
echo  ╔══════════════════════════════════════════════════╗
echo  ║                                                  ║
echo  ║          Kamishibai Studio                       ║
echo  ║          紙芝居動画ジェネレーター                ║
echo  ║                                                  ║
echo  ╚══════════════════════════════════════════════════╝
echo.

REM 仮想環境の存在確認
if not exist .venv (
    echo   [エラー] 仮想環境が見つかりません
    echo           先に install.bat を実行してください
    echo.
    pause
    exit /b 1
)

REM FFmpeg確認
ffmpeg -version >nul 2>&1
if errorlevel 1 (
    echo   [警告] FFmpeg が見つかりません。動画生成に必要です。
    echo          winget install FFmpeg でインストールしてください。
    echo.
)

REM Google Cloud TTS認証（サービスアカウントキーがある場合）
if exist gcp-key.json (
    set GOOGLE_APPLICATION_CREDENTIALS=%~dp0gcp-key.json
    echo   [OK] Google Cloud認証キー (gcp-key.json)
)

REM APIキーファイルの確認
if exist .api_key (
    echo   [OK] Google Cloud APIキー (.api_key)
)

echo   [OK] 仮想環境を検出しました
echo.
echo  ─────────────────────────────────────────────────
echo   ブラウザが自動で開きます
echo   開かない場合: http://localhost:8501
echo.
echo   終了: このウィンドウを閉じるか Ctrl+C
echo  ─────────────────────────────────────────────────
echo.

.venv\Scripts\python.exe -m streamlit run app.py --server.headless=false
pause
