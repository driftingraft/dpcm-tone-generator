# 配布パッケージのビルド手順（メンテナ向け）

一般ユーザー（Pythonを持っていない人）向けに、**インストール不要で起動できる配布パッケージ**を作成します。

- **Windows版**: Windows公式の「埋め込みPython」を同梱。`起動.bat` をダブルクリックするだけで動く（Python導入不要）
- **Mac版**: システムの `python3` を利用。`起動.command` をダブルクリックで動く（python3 未導入時はインストール案内を表示）

いずれも中身は既存の GUI（`dpcm_gui.py` / `dpcm_gui.html` ＋ 依存する `dpcm_*.py`）そのままで、起動スクリプトを添えただけの構成です。

## ディレクトリ構成

```
packaging/
├── build_package.py     … 組み立てスクリプト（標準ライブラリのみ）
├── launchers/
│   ├── 起動.bat          … Windows用ランチャー
│   ├── 起動.command      … Mac用ランチャー
│   └── お読みください.txt … 利用者向け説明（両OS共通）
└── README.md            … このファイル
```

生成される配布物（`dist/` 以下、gitignore対象）:

```
dist/
├── NES-dPCM-Generator-Windows/   （+ .zip）
│   ├── 起動.bat
│   ├── お読みください.txt
│   ├── app/                       … GUI本体一式
│   └── python/                    … 埋め込みPython（同梱）
└── NES-dPCM-Generator-Mac/       （+ .zip）
    ├── 起動.command
    ├── お読みください.txt
    └── app/                       … GUI本体一式
```

## ビルド方法

ビルドはどのOS（Windows/Mac/Linux）でも実行できます（埋め込みPythonのダウンロードのみネット接続が必要）。

```bash
# Windows版・Mac版の両方をフォルダで作成
python3 packaging/build_package.py

# zip も同時に作成（配布用）
python3 packaging/build_package.py --zip

# 対象を絞る
python3 packaging/build_package.py --target windows --zip
python3 packaging/build_package.py --target mac --zip

# 埋め込みPythonのバージョン/アーキテクチャを指定
python3 packaging/build_package.py --python-version 3.12.8 --arch amd64

# 構成だけ確認したい（埋め込みPythonをDLしない）
python3 packaging/build_package.py --no-python
```

## 重要な設計上の注意

- **埋め込みPythonは 3.12 系を既定**にしています。3.13 以降は `audioop` など一部の標準モジュールが削除されているためです。本ツールは標準ライブラリのみ使用（`wave` / `struct` / `http.server` / `webbrowser` / `zipfile` 等）で、いずれも埋め込みパッケージに含まれます。新しい依存を追加する際は、埋め込みPythonに含まれるモジュールかを確認してください。
- **`._pth` への `..\app` 追記**: 埋め込みPythonは `._pth` で `sys.path` が固定されるため、`app\dpcm_gui.py` から兄弟モジュール（`dpcm_generator` 等）を import できるよう、ビルド時に `python\*._pth` へ `..\app` を追記しています（`build_package.py` の `patch_pth_for_app`）。
- **`app/` に置くファイル**は `build_package.py` の `APP_FILES` で定義。GUIが依存するファイルを増やした場合はここに追加してください。
- **`.command` の実行権限**は zip 化時に保持しています（`external_attr`）。Mac でダブルクリック起動するために必要です。

## リリース時のチェック

配布zipを更新したら、最低限これらを確認します。

1. **Windows実機**: zipを解凍 → `起動.bat` をダブルクリック → ブラウザが開き、`.dmc` が生成・ダウンロードできる
2. **Mac実機**: zipを解凍 → `起動.command` を右クリック→開く → 同上
3. GUIの機能・デフォルト値を変えた場合は `docs/gui_manual.md` も追従（CLAUDE.md 参照）

> 注: Windows版は SmartScreen、Mac版は Gatekeeper により初回起動時に警告が出ます（未署名のため）。利用者向けの回避手順は `お読みください.txt` に記載済みです。コード署名を行う場合は別途証明書が必要です。
