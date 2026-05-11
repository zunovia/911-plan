@echo off
chcp 65001 >nul
cd /d "%~dp0"
title Kamishibai Studio - アンインストール

echo.
echo  ╔══════════════════════════════════════════════════╗
echo  ║                                                  ║
echo  ║    Kamishibai Studio  アンインストール           ║
echo  ║                                                  ║
echo  ╚══════════════════════════════════════════════════╝
echo.
echo   以下を削除します:
echo     - .venv  (Python仮想環境)
echo     - output (生成済み動画・音声)
echo     - __pycache__
echo.
echo   ※ 以下は保持されます:
echo     - input/ (台本・画像)
echo     - config.json (設定)
echo     - .api_key (APIキー)
echo     - ソースコード
echo.

set /p CONFIRM="本当に削除しますか？ (y/N): "
if /i not "%CONFIRM%"=="y" (
    echo   キャンセルしました。
    pause
    exit /b 0
)

echo.

if exist .venv (
    echo   [削除中] .venv ...
    rmdir /s /q .venv
    echo   [OK] .venv を削除しました
) else (
    echo   [スキップ] .venv は存在しません
)

if exist output (
    set /p DEL_OUTPUT="  output フォルダも削除しますか？ (y/N): "
    if /i "!DEL_OUTPUT!"=="y" (
        rmdir /s /q output
        echo   [OK] output を削除しました
    ) else (
        echo   [スキップ] output を保持します
    )
)

if exist __pycache__ (
    rmdir /s /q __pycache__
    echo   [OK] __pycache__ を削除しました
)

echo.
echo   アンインストール完了。
echo   再インストールするには install.bat を実行してください。
echo.
pause
