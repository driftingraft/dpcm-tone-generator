# NES dPCM Generator

ファミコン（NES）のdPCMサンプルを生成するPythonツールです。

任意の波形から、指定した音程のdPCMサンプル（.dmc）を生成できます。ループ再生を前提としたベースライン音源の作成に最適化されています。

## 特徴

- **複数の入力形式に対応**: 基本波形（saw/triangle/sine/square/pulse）、FDS波形、HEX文字列、WAVファイル
- **fitモード**: dPCMの有効サンプル長（8+128n）にぴったり収まるパラメータを自動探索し、パディングノイズを排除
- **3段階の品質設定**: サイズ優先 / レート下限指定（中間バランス） / 高品質優先から選択可能
- **音量調整**: 波形の振幅を調整可能
- **ループ最適化**: 開始値の自動設定、終端値の調整でシームレスなループを実現
- **バッチ生成**: 全音階（C2〜F4）を一括生成、ppmck用定義ファイルも出力
- **サンソフトベース方式**: 最小限のサンプル数で全音階をカバー、メモリ使用量を大幅削減

## 動作要件

- Python 3.8以上
- 標準ライブラリのみ使用（追加インストール不要）

## インストール

```bash
git clone https://github.com/driftingraft/dpcm-tone-generator.git
cd dpcm-tone-generator
```

## 使い方

### 基本的な使い方

```bash
# ノコギリ波でC3の音を生成
python dpcm_generator.py --wave saw --note C3 --output saw_c3.dmc

# 推奨設定：fitモード + auto-start
python dpcm_generator.py --wave saw --note C3 --fit --auto-start --output saw_c3.dmc
```

### FDS波形から生成

```bash
# FDS形式（スペース区切り10進数、0-63、64サンプル）
python dpcm_generator.py --fds "00 01 02 03 ... 63 63 00 00" --note C3 --fit --auto-start --output fds_c3.dmc

# ファイルから読み込み
python dpcm_generator.py --fds-file waveform.txt --note C3 --fit --auto-start --output fds_c3.dmc
```

### 高品質設定

```bash
# 高品質モード + 複数周期 + 音量調整
python dpcm_generator.py --wave saw --note C3 --fit --quality --cycles 16 --volume 0.5 --auto-start --output saw_c3.dmc
```

### バッチ生成（全音階）

```bash
# 30音階分を一括生成
python dpcm_batch.py --wave saw --fit --cycles 8 --auto-start --output-dir ./dpcm_samples

# ppmck定義ファイルも自動生成される
# → ./dpcm_samples/saw_defines.txt
```

### サンソフトベース方式

サンソフトベース（Sunsoft Bass）方式は、最小限のサンプル数で全音階をカバーする技術です。1つのサンプルを異なる再生レートで再利用することで、メモリ使用量を大幅に削減できます。

```bash
# まず分析のみ実行（どのサンプルが必要か確認）
python dpcm_sunsoft.py --analyze-only --start C2 --end F4

# サンプル生成
python dpcm_sunsoft.py --wave saw --start C2 --end F4 --fit --auto-start --output-dir ./sunsoft_samples

# 許容誤差を厳しくする（デフォルト25セント）
python dpcm_sunsoft.py --wave saw --start C2 --end F4 --max-error 15 --fit --output-dir ./sunsoft_samples
```

#### 音質優先モードとサイズ優先モード

デフォルトは**音質優先モード**です。対象音域の上端付近（C4〜E4など）を基本サンプルとして選択し、高い音は高いレート($F)で再生されるため、1周期あたりのサンプル数が多く高音質になります。

**サイズ優先モード**（`--size-priority`）は、対象音域より高い音（E6など）も基本サンプル候補に含めます。サンプル数を最小化できますが、低いレートでの再生が増え、音質は低下します。

```bash
# 音質優先（デフォルト）- C4〜E4付近が基本サンプルに
python dpcm_sunsoft.py --analyze-only --start C2 --end E4 --max-error 50
# → 基本サンプル: C4, C#4, D4, D#4, E4（5サンプル、平均誤差13.8セント）

# サイズ優先 - より少ないサンプル数
python dpcm_sunsoft.py --analyze-only --start C2 --end E4 --max-error 50 --size-priority
# → 基本サンプル: C5, C#5, D#6, E6（4サンプル、平均誤差22.2セント）
```

生成例（C2〜F4、30音階）：
- 従来方式: 30サンプル
- サンソフトベース方式（音質優先）: 5サンプル
- サンソフトベース方式（サイズ優先）: 4サンプル（約85%削減）

## オプション一覧

### dpcm_generator.py

| オプション | 短縮形 | 説明 |
|-----------|--------|------|
| `--wave` | `-w` | 波形タイプ: saw, triangle, sine, square, pulse25, pulse12 |
| `--note` | `-n` | 音程（例: C3, A4, F#2） |
| `--freq` | `-f` | 周波数を直接指定（Hz） |
| `--rate-index` | `-r` | サンプルレートインデックス（0-15）を直接指定 |
| `--output` | `-o` | 出力ファイル名 |
| `--fds` | | FDS波形（スペース区切り10進数） |
| `--fds-file` | | FDS波形ファイル |
| `--hex` | `-x` | HEX波形（16進数文字列） |
| `--hex-file` | | HEX波形ファイル |
| `--wav` | | WAVファイル |
| `--cycles` | `-c` | 周期数（デフォルト: 1） |
| `--volume` | `-v` | 音量係数（デフォルト: 1.0） |
| `--fit` | | 有効サンプル長に自動フィット |
| `--quality` | `-q` | fitモード時、高サンプルレート優先 |
| `--min-rate-index` | | fitモード時、サンプルレートの下限を指定（0-15） |
| `--auto-start` | `-a` | 開始値を波形に合わせる |
| `--loop-match` | `-l` | 終端値を開始値に戻す |
| `--show-wave` | | 波形をASCII表示 |
| `--info` | `-i` | サンプルレート情報を表示 |

### dpcm_batch.py

`dpcm_generator.py`と同様のオプションに加えて：

| オプション | 短縮形 | 説明 |
|-----------|--------|------|
| `--output-dir` | `-o` | 出力ディレクトリ |
| `--name` | `-n` | カスタム波形使用時のファイル名プレフィックス |

### dpcm_sunsoft.py

| オプション | 短縮形 | 説明 |
|-----------|--------|------|
| `--wave` | | 波形タイプ: saw, triangle, sine, square, pulse25, pulse12 |
| `--fds` | | FDS波形ファイル |
| `--hex` | | HEX波形データ |
| `--wav` | | WAVファイル |
| `--analyze-only` | | 分析のみ実行（サンプル生成なし） |
| `--start` | | 開始ノート（デフォルト: C2） |
| `--end` | | 終了ノート（デフォルト: F4） |
| `--max-error` | | 許容誤差（セント、デフォルト: 25.0） |
| `--output-dir` | `-o` | 出力ディレクトリ |
| `--prefix` | | ファイル名プレフィックス（デフォルト: sunsoft_） |
| `--fit` | | fitモード（dPCM有効サンプル数に合わせる） |
| `--cycles` | | 周期数（デフォルト: 8） |
| `--volume` | | 音量（0.0-1.0、デフォルト: 1.0） |
| `--auto-start` | | 開始値を波形に合わせる |
| `--loop-match` | | ループ時に開始値に戻るよう調整 |
| `--prefer-quality` | | レート選択で高レートを優先 |
| `--size-priority` | | サイズ優先モード（対象範囲外のサンプルも使用、デフォルトは音質優先） |

## 推奨設定

### 最高品質（サイズ大）

```bash
python dpcm_generator.py --wave saw --note C3 --fit --quality --cycles 16 --auto-start --output output.dmc
```

### バランス重視（推奨）

`--min-rate-index`でサンプルレートの下限を指定しつつ、サイズを抑える：

```bash
# レート$8以上で最小サイズを選択
python dpcm_generator.py --wave saw --note C3 --fit --min-rate-index 8 --auto-start --output output.dmc
```

### サイズ優先

```bash
python dpcm_generator.py --wave saw --note C3 --fit --auto-start --output output.dmc
```

### サイズ最小（fitなし）

```bash
python dpcm_generator.py --wave saw --note C3 --output output.dmc
```

## 技術的な詳細

### ファミコンdPCMの仕様

- 1ビット差分変調（+2または-2）
- サンプル値: 0〜127（7ビット）
- 有効サンプル長: 8 + 128n（n=0,1,2,...）
- 有効バイト長: 1 + 16n
- 16種類のサンプルレート（NTSC）

### fitモードの動作

1. 16種類のサンプルレートを全探索
2. 各レートで1〜64周期を試行
3. 合計サンプル数が(8+128n)で割り切れる組み合わせを検索
4. 誤差15セント以内の候補から最適なものを選択

### --auto-start の効果

dPCMは通常、開始値64（中央値）から始まります。波形が0から始まる場合、目標値に追いつくまでの「降下区間」がノイズの原因になります。`--auto-start`を使うと波形の最初の値から開始するため、この問題を回避できます。

## ppmckでの使用例

生成されるppmck定義ファイルの例：

```
; dPCMサンプル定義 (saw)
; 生成日時: 2025-01-16

@DPCM0 = { "saw_C2.dmc", 1 }    ; C2
@DPCM1 = { "saw_C_s2.dmc", 3 }  ; C#2
@DPCM2 = { "saw_D2.dmc", 2 }    ; D2
...
```

MMLでの使用：

```
E @DPCM0 | c   ; dPCMをトーンとして再生
```

## ライセンス

MIT License

## 参考資料

- [NESDev Wiki - APU DMC](https://www.nesdev.org/wiki/APU_DMC)
- [ppmck](https://github.com/ppmck/ppmck)
