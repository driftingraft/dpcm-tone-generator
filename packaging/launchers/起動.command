#!/bin/bash
# NES dPCM Generator - Mac 起動スクリプト
# システムの python3 でGUIサーバーを起動し、ブラウザを開きます。

cd "$(dirname "$0")" || exit 1

if ! command -v python3 >/dev/null 2>&1; then
    echo ""
    echo "Python3 が見つかりませんでした。"
    echo "このあと表示される案内に従って"
    echo "「コマンドラインデベロッパツール」をインストールしてください。"
    echo "（初回のみ。インストール後、もう一度この「起動.command」を実行してください）"
    echo ""
    xcode-select --install 2>/dev/null
    echo "何かキーを押すとこのウィンドウを閉じます..."
    read -n 1 -s -r
    exit 1
fi

echo "============================================"
echo "  NES dPCM Generator を起動します"
echo "============================================"
echo ""
echo "ブラウザが自動で開きます。"
echo "開かない場合は http://127.0.0.1:8765/ にアクセスしてください。"
echo ""
echo "終了するときは、このウィンドウを閉じるか Ctrl+C を押してください。"
echo ""

python3 app/dpcm_gui.py
