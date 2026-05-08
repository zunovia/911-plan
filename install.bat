@echo off
chcp 65001 >nul
echo ================================================
echo   紙芝居動画ジェネレーター セットアップ
echo ================================================
echo.

REM Pythonチェック
python --version >nul 2>&1
if errorlevel 1 (
    echo [エラー] Pythonが見つかりません。
    echo   以下からインストールしてください:
    echo   https://www.python.org/downloads/
    echo   ※ インストール時に「Add Python to PATH」にチェックを入れてください
    echo.
    pause
    exit /b 1
)
for /f "tokens=*" %%i in ('python --version') do echo [OK] %%i を検出しました

echo.

REM FFmpegチェック
ffmpeg -version >nul 2>&1
if errorlevel 1 (
    echo [警告] FFmpegが見つかりません。
    echo   動画生成にはFFmpegが必要です。以下のいずれかの方法でインストールしてください:
    echo.
    echo   方法1（推奨）: winget を使う場合
    echo     winget install FFmpeg
    echo.
    echo   方法2: 手動ダウンロード
    echo     https://ffmpeg.org/download.html
    echo     ダウンロード後、フォルダをPATHに追加してください
    echo.
    echo   FFmpegなしでもセットアップを続行します。
    echo   動画生成を行う前に必ずインストールしてください。
    echo.
) else (
    echo [OK] FFmpeg を検出しました
    echo.
)

REM 仮想環境の作成
if exist .venv (
    echo [スキップ] 仮想環境 .venv は既に存在します
) else (
    echo [実行中] 仮想環境を作成しています...
    python -m venv .venv
    if errorlevel 1 (
        echo [エラー] 仮想環境の作成に失敗しました。
        pause
        exit /b 1
    )
    echo [OK] 仮想環境を作成しました
)
echo.

REM 依存パッケージのインストール
echo [実行中] 必要なパッケージをインストールしています...
echo   （初回は数分かかる場合があります）
call .venv\Scripts\activate
pip install -r requirements.txt
if errorlevel 1 (
    echo [エラー] パッケージのインストールに失敗しました。
    echo   インターネット接続を確認してから再試行してください。
    pause
    exit /b 1
)
echo [OK] パッケージのインストールが完了しました
echo.

REM config.json のコピー
if exist config.json (
    echo [スキップ] config.json は既に存在します
) else (
    copy config.example.json config.json >nul
    echo [OK] config.json を作成しました
    echo   Google Cloud TTS を使用する場合は config.json を編集してください
)
echo.

REM input/images フォルダの作成
if exist input\images (
    echo [スキップ] input\images フォルダは既に存在します
) else (
    mkdir input\images
    echo [OK] input\images フォルダを作成しました
)
echo.

echo ================================================
echo   セットアップ完了！
echo ================================================
echo.
echo   start.bat をダブルクリックしてアプリを起動してください。
echo.
echo   使い方は README.md を参照してください。
echo.
pause
