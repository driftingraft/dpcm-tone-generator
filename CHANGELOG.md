# 更新履歴 (Changelog)

このファイルはプロジェクトの主な変更点を記録します。
バージョニングは [セマンティック バージョニング](https://semver.org/lang/ja/) に準拠します。
(This changelog is written primarily in Japanese.)

## [未リリース]

### 追加
- GUIの「バッチ生成」タブにもスケールプレビューを追加（従来はサンソフト方式タブのみ）
- スケールプレビューに「ドレミファソラシ（♯を除く幹音のみ）」版を追加。全音階（半音刻み）版と合わせて2種類のWAVを再生・出力できる

### 変更
- ツール名称を「dPCM Tone Generator」に統一（旧称: NES dPCM Generator。README・GUI画面・配布パッケージ名 `dPCM-Tone-Generator-*` に反映）
- GUIのノート選択を「音名＋オクターブ」の2つのドロップダウンに分割（96項目の単一リストで上の音階が見つけにくかった問題を解消）
- GUIサーバーの再起動時、直近までGUIタブが開かれていた場合はブラウザの自動起動をスキップするように変更（タブが二重に開くのを防止。しばらく間が空いた起動では従来どおり自動で開く）

### 修正
- サンソフト方式でG#4・C5など一部の高音が「カバーできないノート」になっていた問題を修正（fit探索の周期数上限を64→128に拡大。既定の許容誤差25centsでC5までカバー可能に）
- 「カバーできないノート」エラーに対処方法のヒント（許容誤差の調整など）を追記
- ppmck用のMML使用例を修正。Eチャンネル（DPCM）では音名（`c`等）ではなく `n` コマンドで@DPCM番号を直接指定する正しい書式（`E n0` 形式）に変更（CLI出力・定義ファイル・GUI表示・ドキュメント）
- `dpcm_sunsoft.py` の定義ファイルにもEチャンネルの使用例を追加

## [1.0.0] - 2026-07-09

初版リリース。

### 追加
- **dPCMジェネレーター（CLI）**
  - `dpcm_generator.py` — 単一 `.dmc` 生成。saw/triangle/sine/square/pulse、FDS波形、HEX、WAV入力に対応
  - `dpcm_batch.py` — 指定音域（既定 C2〜F4）の全音階を一括生成、ppmck定義・ZIP出力
  - `dpcm_sunsoft.py` — サンソフトベース方式（最小サンプル数で全音階をカバー）
  - fitモード（dPCM有効長 8+128n に自動フィット）、高品質モード、auto-start / loop-match / warmup、サブオクターブ混合、WAV入力時の自動ローパスフィルタ など
- **ブラウザGUI**（`dpcm_gui.py` / `dpcm_gui.html`）
  - 3スクリプトの全機能をブラウザから操作（波形表示・音声プレビュー・ZIP一括ダウンロード・ppmck定義出力）
  - 日本語/英語の多言語対応（ブラウザ言語の自動判定＋右上ボタンで切替）
- **Python不要の配布パッケージ**（`packaging/`）
  - Windows: 埋め込みPython同梱、`Start.bat` をダブルクリックで起動
  - Mac: システムの `python3` を利用、`Start.command` をダブルクリックで起動
- ドキュメント: README（日本語／英語）、GUIマニュアル（`docs/gui_manual.md`）、配布ビルド手順（`packaging/README.md`）

### 備考
- 本プロジェクトは開発に生成AI（Claude Code）を利用しています。
