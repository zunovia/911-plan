@echo off
chcp 65001 >nul
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

REM 仮想環境を有効化してアプリを起動
call .venv\Scripts\activate
echo [OK] 仮想環境を有効化しました
echo.
echo   ブラウザが自動で開きます。
echo   開かない場合は http://localhost:8501 にアクセスしてください。
echo.
echo   終了するには このウィンドウを閉じるか Ctrl+C を押してください。
echo.
streamlit run app.py
