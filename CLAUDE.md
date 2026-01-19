# CLAUDE.md

このファイルはClaude Codeがこのリポジトリで作業する際のガイダンスを提供します。

## 言語設定

**このプロジェクトでは日本語でやり取りを行います。**

## プロジェクト概要

NES dPCM Generator - ファミコン（NES）のdPCMサンプルを生成するPythonツール

### 主要ファイル

- `dpcm_generator.py` - メインのdPCMジェネレーター（単一ファイル生成）
- `dpcm_batch.py` - バッチ処理用スクリプト（全音階一括生成）
- `examples/` - サンプルファイル

### 技術スタック

- Python 3.8以上
- 標準ライブラリのみ使用（追加依存なし）

### 主な機能

- 複数の入力形式に対応（saw/triangle/sine/square/pulse、FDS波形、HEX、WAV）
- fitモード：dPCMの有効サンプル長（8+128n）に自動フィット
- 高品質モード：音質優先のサンプルレート選択
- ループ最適化：シームレスなループ再生のための調整機能
- バッチ生成：C2〜F4の全音階を一括生成、ppmck用定義ファイル出力

## 開発コマンド

```bash
# 単一ファイル生成（推奨設定）
python dpcm_generator.py --wave saw --note C3 --fit --auto-start --output output.dmc

# バッチ生成
python dpcm_batch.py --wave saw --fit --cycles 8 --auto-start --output-dir ./dpcm_samples

# サンプルレート情報表示
python dpcm_generator.py --info
```
