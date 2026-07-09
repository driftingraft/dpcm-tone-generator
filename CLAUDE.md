# CLAUDE.md

このファイルはClaude Codeがこのリポジトリで作業する際のガイダンスを提供します。

## 言語設定

**このプロジェクトでは日本語でやり取りを行います。**

## プロジェクト概要

NES dPCM Generator - ファミコン（NES）のdPCMサンプルを生成するPythonツール

### 主要ファイル

- `dpcm_generator.py` - メインのdPCMジェネレーター（単一ファイル生成）
- `dpcm_batch.py` - バッチ処理用スクリプト（全音階一括生成）
- `dpcm_sunsoft.py` - サンソフトベース方式（最小サンプル数で全音階カバー）
- `dpcm_gui.py` - ブラウザGUI用ローカルWebサーバー（3スクリプト全機能をAPI経由で提供）
- `dpcm_gui.html` - GUIのフロントエンド（単一HTML、`dpcm_gui.py`が配信）
- `examples/` - サンプルファイル

### 技術スタック

- Python 3.8以上
- 標準ライブラリのみ使用（追加依存なし）

### 主な機能

- 複数の入力形式に対応（saw/triangle/sine/square/pulse、FDS波形、HEX、WAV）
- fitモード：dPCMの有効サンプル長（8+128n）に自動フィット
- 高品質モード：音質優先のサンプルレート選択
- ループ最適化：シームレスなループ再生のための調整機能
- バッチ生成：指定音域（デフォルト: C2〜F4、`--start`/`--end`で変更可）の全音階を一括生成、ppmck用定義ファイル出力

## 開発コマンド

```bash
# 単一ファイル生成（推奨設定）
python dpcm_generator.py --wave saw --note C3 --fit --auto-start --output output.dmc

# バッチ生成
python dpcm_batch.py --wave saw --fit --cycles 8 --auto-start --output-dir ./dpcm_samples

# サンプルレート情報表示
python dpcm_generator.py --info

# GUI起動（http://127.0.0.1:8765/）
python dpcm_gui.py --no-browser
```

## 開発時の注意点

### ファイル間の依存関係

`dpcm_batch.py`と`dpcm_sunsoft.py`は`dpcm_generator.py`から関数をインポートして使用している。
`dpcm_gui.py`はさらに3ファイル全てから関数をインポートしてWeb APIとして公開している（単一生成は`dpcm_generator.py`のmain()相当の処理を`handle_generate()`で再実装しているため、main()のロジック変更時は`dpcm_gui.py`側も追従が必要）。

```python
from dpcm_generator import (
    generate_waveform, encode_dpcm, resample_waveform, adjust_volume,
    freq_from_note, find_best_sample_rate, find_best_fit_params,
    ...
)
```

**重要**: `dpcm_generator.py`に以下の変更を加えた場合、`dpcm_batch.py`と`dpcm_sunsoft.py`も同様に更新が必要：

- コマンドライン引数の追加・変更（特にfitモード関連のオプション）
- `find_best_fit_params`等の共有関数のシグネチャ変更
- 新しいエンコード/デコードオプションの追加

### ppmck定義出力機能

3つのスクリプトはそれぞれppmck用の定義ファイルを出力する機能を持つ：

- `dpcm_generator.py`: 標準出力に参考例を表示
- `dpcm_batch.py`: `generate_ppmck_defines()`関数で定義ファイル生成
- `dpcm_sunsoft.py`: `generate_sunsoft_defines()`関数で定義ファイル生成

**重要**: ppmck定義の出力形式を変更する場合は、3つのファイル全てで同様の変更が必要：

- 定義フォーマットの変更（例: ループフラグの追加）
- 新しいオプションの追加（例: `--dpcm-start-index`, `--dpcm-path`）

※ `dpcm_sunsoft.py`の`--dpcm-start-index`は「音階部分（ノート別定義）」の開始番号を指定する（基本サンプル定義とは独立）

### 動作確認

変更後は全てのスクリプトで動作確認を行う：

```bash
# 単体生成の確認
python3 dpcm_generator.py --wave saw --note C3 --fit --output /tmp/test.dmc

# バッチ生成の確認
python3 dpcm_batch.py --wave saw --fit --output-dir /tmp/batch_test

# サンソフトベース方式の確認
python3 dpcm_sunsoft.py --wave saw --output-dir /tmp/sunsoft_test

# GUIの確認（起動してAPIを叩き、CLIと同一の.dmcが得られるか比較）
python3 dpcm_gui.py --no-browser --port 8791 &
curl -s -X POST http://127.0.0.1:8791/api/generate -H 'Content-Type: application/json' \
  -d '{"wave":"saw","note":"C3","fit":true}' | python3 -c \
  "import json,sys,base64;open('/tmp/gui_test.dmc','wb').write(base64.b64decode(json.load(sys.stdin)['dmc_base64']))"
cmp /tmp/test.dmc /tmp/gui_test.dmc
```
