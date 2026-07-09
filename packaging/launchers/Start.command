#!/bin/bash
# NES dPCM Generator - launcher (Mac) / 起動スクリプト
# Starts the local GUI server with system python3 and opens the browser.

cd "$(dirname "$0")" || exit 1

if ! command -v python3 >/dev/null 2>&1; then
    echo ""
    echo "Python3 was not found. / Python3 が見つかりませんでした。"
    echo "Follow the prompt to install the Command Line Developer Tools."
    echo "(案内に従って「コマンドラインデベロッパツール」をインストールしてください)"
    echo "Then double-click this file again. / 完了後、もう一度このファイルを実行してください。"
    echo ""
    xcode-select --install 2>/dev/null
    echo "Press any key to close... / 何かキーを押すと閉じます"
    read -n 1 -s -r
    exit 1
fi

echo "============================================"
echo "  NES dPCM Generator"
echo "============================================"
echo ""
echo "Your browser will open automatically. / ブラウザが自動で開きます"
echo "If it does not, open http://127.0.0.1:8765/ manually."
echo "(開かない場合は http://127.0.0.1:8765/ へアクセス)"
echo ""
echo "To quit, close this window or press Ctrl+C. / 終了は Ctrl+C、または画面を閉じてください"
echo ""

python3 app/dpcm_gui.py
