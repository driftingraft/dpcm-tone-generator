@echo off
rem NES dPCM Generator - launcher (Windows) / 起動スクリプト
rem Starts the local GUI server with the bundled Python and opens the browser.
chcp 65001 >nul
cd /d "%~dp0"

if not exist "python\python.exe" (
    echo.
    echo [Error] Bundled Python not found. / 同梱Pythonが見つかりません。
    echo Please re-extract this folder and try again. / 解凍し直してからお試しください。
    echo.
    pause
    exit /b 1
)

echo ============================================
echo   NES dPCM Generator
echo ============================================
echo.
echo Your browser will open automatically.
echo (ブラウザが自動で開きます)
echo If it does not, open http://127.0.0.1:8765/ manually.
echo (開かない場合は http://127.0.0.1:8765/ へアクセス)
echo.
echo To quit, close this window or press Ctrl+C.
echo (終了するにはこの画面を閉じるか Ctrl+C を押してください)
echo.

python\python.exe app\dpcm_gui.py

echo.
echo (Stopped. You can close this window. / 終了しました。閉じて構いません)
pause
