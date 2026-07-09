@echo off
rem NES dPCM Generator - Windows 起動スクリプト
rem 同梱の埋め込みPythonでGUIサーバーを起動し、ブラウザを開きます。
chcp 65001 >nul
cd /d "%~dp0"

if not exist "python\python.exe" (
    echo.
    echo [エラー] 同梱のPythonが見つかりません。
    echo このフォルダを解凍し直してから、もう一度お試しください。
    echo.
    pause
    exit /b 1
)

echo ============================================
echo   NES dPCM Generator を起動します
echo ============================================
echo.
echo ブラウザが自動で開きます。
echo 開かない場合は http://127.0.0.1:8765/ にアクセスしてください。
echo.
echo 終了するときは、この画面を閉じるか Ctrl+C を押してください。
echo.

python\python.exe app\dpcm_gui.py

echo.
echo （終了しました。この画面は閉じて構いません）
pause
