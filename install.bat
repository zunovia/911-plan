@echo off
chcp 65001 >nul
cd /d "%~dp0"
title Kamishibai Studio - インストーラー

echo.
echo  ╔══════════════════════════════════════════════════╗
echo  ║                                                  ║
echo  ║        Kamishibai Studio  セットアップ           ║
echo  ║        紙芝居動画ジェネレーター                  ║
echo  ║                                                  ║
echo  ╚══════════════════════════════════════════════════╝
echo.
echo  このスクリプトは以下をセットアップします:
echo    - Python仮想環境の作成
echo    - 必要なパッケージのインストール
echo    - Playwrightブラウザエンジン
echo    - 設定ファイルの初期化
echo.
echo  ─────────────────────────────────────────────────
echo   [Step 1/7] 前提条件チェック
echo  ─────────────────────────────────────────────────
echo.

set ERROR_COUNT=0

REM === Python チェック ===
python --version >nul 2>&1
if errorlevel 1 (
    echo   [NG] Python が見つかりません
    echo        https://www.python.org/downloads/ からインストールしてください
    echo        ※「Add Python to PATH」にチェックを入れること
    set /a ERROR_COUNT+=1
) else (
    for /f "tokens=*" %%i in ('python --version') do echo   [OK] %%i
)

REM === pip チェック ===
python -m pip --version >nul 2>&1
if errorlevel 1 (
    echo   [NG] pip が見つかりません
    set /a ERROR_COUNT+=1
) else (
    echo   [OK] pip
)

REM === FFmpeg チェック ===
ffmpeg -version >nul 2>&1
if errorlevel 1 (
    echo   [!!] FFmpeg が見つかりません（動画生成に必須）
    echo.
    echo        インストール方法:
    echo          winget install FFmpeg
    echo        または https://ffmpeg.org/download.html
    echo.
    set FFMPEG_MISSING=1
) else (
    for /f "tokens=1-3" %%a in ('ffmpeg -version 2^>^&1') do (
        if "%%a"=="ffmpeg" echo   [OK] FFmpeg %%c
        goto :ffmpeg_done
    )
    :ffmpeg_done
)

if %ERROR_COUNT% gtr 0 (
    echo.
    echo   [エラー] 前提条件を満たしていません。上記を解決してから再実行してください。
    echo.
    pause
    exit /b 1
)

echo.
echo  ─────────────────────────────────────────────────
echo   [Step 2/7] Python仮想環境の作成
echo  ─────────────────────────────────────────────────
echo.

if exist .venv (
    echo   [スキップ] .venv は既に存在します
) else (
    echo   [実行中] 仮想環境を作成しています...
    python -m venv .venv
    if errorlevel 1 (
        echo   [エラー] 仮想環境の作成に失敗しました
        pause
        exit /b 1
    )
    echo   [OK] 仮想環境を作成しました
)

echo.
echo  ─────────────────────────────────────────────────
echo   [Step 3/7] pip のアップグレード
echo  ─────────────────────────────────────────────────
echo.

echo   [実行中] pip を最新バージョンに更新しています...
.venv\Scripts\python.exe -m pip install --upgrade pip >nul 2>&1
if errorlevel 1 (
    echo   [警告] pip の更新に失敗しましたが、続行します
) else (
    echo   [OK] pip を更新しました
)

echo.
echo  ─────────────────────────────────────────────────
echo   [Step 4/7] 依存パッケージのインストール
echo  ─────────────────────────────────────────────────
echo.

echo   [実行中] パッケージをインストールしています...
echo            （初回は数分かかる場合があります）
echo.
.venv\Scripts\pip.exe install -r requirements.txt
if errorlevel 1 (
    echo.
    echo   [エラー] パッケージのインストールに失敗しました
    echo          インターネット接続を確認してから再試行してください
    pause
    exit /b 1
)
echo.
echo   [OK] パッケージのインストールが完了しました

echo.
echo  ─────────────────────────────────────────────────
echo   [Step 5/7] Playwright ブラウザエンジン
echo  ─────────────────────────────────────────────────
echo.

echo   [実行中] Chromium をインストールしています...
.venv\Scripts\python.exe -m playwright install chromium
if errorlevel 1 (
    echo   [警告] ブラウザエンジンのインストールに失敗しました
    echo          HTML録画機能を使う場合は手動で実行してください:
    echo          .venv\Scripts\python.exe -m playwright install chromium
) else (
    echo   [OK] Chromium のインストールが完了しました
)

echo.
echo  ─────────────────────────────────────────────────
echo   [Step 6/7] 設定ファイルの初期化
echo  ─────────────────────────────────────────────────
echo.

REM config.json
if exist config.json (
    echo   [スキップ] config.json は既に存在します
) else (
    copy config.example.json config.json >nul
    echo   [OK] config.json を作成しました
)

REM input フォルダ
if not exist input\images (
    mkdir input\images 2>nul
    echo   [OK] input\images フォルダを作成しました
) else (
    echo   [スキップ] input\images は既に存在します
)

REM output フォルダ
if not exist output (
    mkdir output 2>nul
    echo   [OK] output フォルダを作成しました
) else (
    echo   [スキップ] output は既に存在します
)

echo.
echo  ─────────────────────────────────────────────────
echo   [Step 7/7] インストール検証
echo  ─────────────────────────────────────────────────
echo.

set VERIFY_OK=1

REM Streamlit 動作確認
.venv\Scripts\python.exe -c "import streamlit; print(f'  [OK] Streamlit {streamlit.__version__}')" 2>nul
if errorlevel 1 (
    echo   [NG] Streamlit のインポートに失敗
    set VERIFY_OK=0
)

REM generate_video モジュール確認
.venv\Scripts\python.exe -c "import generate_video; print('  [OK] generate_video モジュール')" 2>nul
if errorlevel 1 (
    echo   [NG] generate_video のインポートに失敗
    set VERIFY_OK=0
)

REM Playwright 確認
.venv\Scripts\python.exe -c "from playwright.sync_api import sync_playwright; print('  [OK] Playwright')" 2>nul
if errorlevel 1 (
    echo   [警告] Playwright のインポートに失敗（HTML録画は使用不可）
)

REM FFmpeg 確認（再チェック）
ffmpeg -version >nul 2>&1
if errorlevel 1 (
    echo   [警告] FFmpeg が見つかりません（動画生成前にインストールしてください）
) else (
    echo   [OK] FFmpeg
)

echo.
echo  ══════════════════════════════════════════════════
if "%VERIFY_OK%"=="1" (
    echo.
    echo   セットアップ完了！
    echo.
    echo   ┌──────────────────────────────────────────┐
    echo   │  start.bat をダブルクリックで起動！       │
    echo   └──────────────────────────────────────────┘
    echo.
    echo   ■ 使い方:
    echo     1. start.bat をダブルクリック
    echo     2. ブラウザで http://localhost:8501 が開きます
    echo     3. 台本ファイル (.md) を読み込み
    echo     4. TTS設定で音声プロバイダーを選択
    echo     5.「動画生成」をクリック
    echo.
    echo   ■ TTS プロバイダー:
    echo     - Google Cloud TTS : APIキーが必要（UI上で設定可）
    echo     - VOICEVOX         : 無料・ローカル動作
    echo       https://voicevox.hiroshiba.jp/ からダウンロード
    echo.
) else (
    echo.
    echo   [警告] 一部のコンポーネントで問題が検出されました
    echo          上記のエラーを確認してください
    echo.
)

if defined FFMPEG_MISSING (
    echo   ※ FFmpeg が未インストールです。動画生成前に以下を実行:
    echo     winget install FFmpeg
    echo.
)

pause
