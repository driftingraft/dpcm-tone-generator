#!/usr/bin/env python3
"""
複数音階のdPCMファイルを一括生成
ppmckで使えるサンプル定義も出力します
"""

import os
import sys
from dpcm_generator import (
    generate_waveform, encode_dpcm, resample_waveform, adjust_volume,
    freq_from_note, find_best_sample_rate, find_best_fit_params,
    parse_hex_waveform, parse_fds_waveform, load_wav_waveform,
    get_valid_dpcm_sample_counts, find_nearest_valid_sample_count,
    generate_preview, generate_raw_preview, apply_lowpass_filter,
    mix_sub_octave, generate_note_range,
    SAMPLE_RATES_NTSC,
    # バリデーション関数
    validate_note_name, validate_positive_int, validate_non_negative_int,
    validate_non_negative_float, validate_rate_index, validate_readable_file,
)

# 生成する音階の範囲（デフォルト）
NOTES = [
    # オクターブ2
    "C2", "C#2", "D2", "D#2", "E2", "F2", "F#2", "G2", "G#2", "A2", "A#2", "B2",
    # オクターブ3
    "C3", "C#3", "D3", "D#3", "E3", "F3", "F#3", "G3", "G#3", "A3", "A#3", "B3",
    # オクターブ4
    "C4", "C#4", "D4", "D#4", "E4", "F4",
]

def generate_note_set(wave_type: str, output_dir: str, prefix: str = "", custom_waveform: list[float] = None, cycles: int = 1, volume: float = 1.0, auto_start: bool = False, loop_match: bool = False, fit: bool = False, prefer_quality: bool = False, min_rate_index: int = 0, preview: bool = False, preview_loops: int = 4, raw_preview: bool = False, raw_preview_loops: int = None, warmup: bool = False, lowpass_cutoff: float = None, lowpass_order: int = 63, wav_sample_rate: int = None, no_auto_lowpass: bool = False, sub_octave: float = 0.0, notes: list[str] = None):
    """
    指定波形で全音階を生成
    custom_waveform が指定されている場合はそれを使用
    notes を指定するとその音階リストを生成（省略時はNOTES＝C2〜F4）

    Returns:
        (成功リスト, 失敗リスト)
        成功リスト: 生成に成功したノートの情報
        失敗リスト: 失敗したノートと理由のタプル
    """
    target_notes = notes if notes is not None else NOTES
    try:
        os.makedirs(output_dir, exist_ok=True)
    except PermissionError:
        print(f"エラー: 出力ディレクトリの作成権限がありません: '{output_dir}'", file=sys.stderr)
        return [], [(None, f"出力ディレクトリの作成権限がありません: '{output_dir}'")]
    except OSError as e:
        print(f"エラー: 出力ディレクトリの作成に失敗しました: '{output_dir}' ({e})", file=sys.stderr)
        return [], [(None, f"出力ディレクトリの作成に失敗: {e}")]

    results = []
    failures = []

    for note in target_notes:
        try:
            target_freq = freq_from_note(note)

            if fit:
                # fitモード: 有効なdPCMサンプル数にぴったり合わせる
                # loop_matchが有効な場合、余地を確保
                loop_reserve = 64 if loop_match else 0
                # サブオクターブ混合時はループ境界整合のため偶数周期を要求
                require_even = sub_octave > 0
                result = find_best_fit_params(target_freq, min_cycles=cycles,
                                              max_cycles=max(cycles * 4, 64),
                                              prefer_quality=prefer_quality,
                                              min_rate_index=min_rate_index,
                                              loop_match_reserve=loop_reserve,
                                              require_even_cycles=require_even)
                if result is None and require_even:
                    # 偶数周期の解が見つからない場合は制約を外して再探索
                    print(f"  {note}: 偶数周期の解なし（サブオクターブがループ境界でずれる可能性）")
                    result = find_best_fit_params(target_freq, min_cycles=cycles,
                                                  max_cycles=max(cycles * 4, 64),
                                                  prefer_quality=prefer_quality,
                                                  min_rate_index=min_rate_index,
                                                  loop_match_reserve=loop_reserve)
                if result is None:
                    print(f"  {note}: スキップ（適切なパラメータなし）")
                    failures.append((note, "適切なパラメータが見つかりません"))
                    continue
                sample_rate, rate_index, num_samples, num_cycles, total_samples = result
            else:
                sample_rate, rate_index, num_samples = find_best_sample_rate(target_freq, min_samples=16)
                if sample_rate is None:
                    print(f"  {note}: スキップ（適切なサンプルレートなし）")
                    failures.append((note, "適切なサンプルレートが見つかりません"))
                    continue
                num_cycles = cycles
                # サブオクターブ混合時はループ境界整合のため偶数周期に揃える
                if sub_octave > 0 and num_cycles % 2 != 0:
                    num_cycles += 1
                total_samples = num_samples * num_cycles

            actual_freq = sample_rate / num_samples

            # ファイル名（#を_sに置換）
            safe_note = note.replace("#", "_s")
            filename = f"{prefix}{wave_type}_{safe_note}.dmc"
            filepath = os.path.join(output_dir, filename)

            # WAV入力時のローパスフィルタ処理
            filtered_waveform = custom_waveform
            if custom_waveform and wav_sample_rate and not no_auto_lowpass:
                if lowpass_cutoff:
                    # 明示的にカットオフ周波数が指定された場合
                    filtered_waveform = apply_lowpass_filter(
                        custom_waveform, wav_sample_rate,
                        lowpass_cutoff, lowpass_order
                    )
                else:
                    # 自動計算: 出力サンプルレートの0.4倍
                    auto_cutoff = sample_rate * 0.4
                    filtered_waveform = apply_lowpass_filter(
                        custom_waveform, wav_sample_rate,
                        auto_cutoff, lowpass_order
                    )

            # 波形生成（1周期分）
            if filtered_waveform:
                waveform_1cycle = resample_waveform(filtered_waveform, num_samples)
            elif custom_waveform:
                waveform_1cycle = resample_waveform(custom_waveform, num_samples)
            else:
                waveform_1cycle = generate_waveform(wave_type, num_samples)

            # 音量調整
            if volume != 1.0:
                waveform_1cycle = adjust_volume(waveform_1cycle, volume)

            # 複数周期に拡張（warmup有効時は助走用に波形の1周期分を先頭に追加。
            # サブオクターブ混合時は波形の周期が2倍になるため2周期分）
            warmup_cycles = (2 if sub_octave > 0 else 1) if warmup else 0
            waveform = waveform_1cycle * (num_cycles + warmup_cycles)

            # サブオクターブ混合
            if sub_octave > 0:
                waveform = mix_sub_octave(
                    waveform, num_samples,
                    wave_type, sub_octave,
                    custom_waveform=filtered_waveform or custom_waveform or None
                )

            # エンコード
            warmup_count = num_samples * warmup_cycles
            dpcm_data, actual_start = encode_dpcm(waveform, loop_match=loop_match, auto_start=auto_start, warmup_samples=warmup_count)

            try:
                with open(filepath, 'wb') as f:
                    f.write(dpcm_data)
            except PermissionError:
                print(f"  {note}: 失敗（書き込み権限なし）")
                failures.append((note, f"ファイル書き込み権限がありません: '{filepath}'"))
                continue
            except IOError as e:
                print(f"  {note}: 失敗（書き込みエラー）")
                failures.append((note, f"ファイル書き込みエラー: {e}"))
                continue

            # プレビュー生成
            if preview:
                preview_start = actual_start
                preview_path = os.path.splitext(filepath)[0] + ".wav"
                try:
                    generate_preview(dpcm_data, sample_rate, preview_path,
                                    loops=preview_loops, start_value=preview_start)
                except (PermissionError, IOError) as e:
                    print(f"  {note}: プレビュー生成失敗 ({e})")

            # エンコード前プレビュー生成
            if raw_preview:
                raw_preview_path = os.path.splitext(filepath)[0] + "_raw.wav"
                raw_loops = raw_preview_loops if raw_preview_loops else preview_loops
                try:
                    generate_raw_preview(waveform, sample_rate, raw_preview_path, loops=raw_loops)
                except (PermissionError, IOError) as e:
                    print(f"  {note}: エンコード前プレビュー生成失敗 ({e})")

            results.append({
                'note': note,
                'filename': filename,
                'rate_index': rate_index,
                'samples': num_samples,
                'size': len(dpcm_data),
                'actual_freq': actual_freq,
                'target_freq': target_freq,
            })

            print(f"  {note}: {filename} (rate=${rate_index:X}, {len(dpcm_data)}bytes)")

        except Exception as e:
            print(f"  {note}: 失敗（予期しないエラー）")
            failures.append((note, str(e)))
            continue

    return results, failures


def generate_ppmck_defines(results: list, wave_type: str,
                           start_index: int = 0, dpcm_path: str = "") -> str:
    """
    ppmck用のサンプル定義を生成

    Args:
        results: 生成結果のリスト
        wave_type: 波形タイプ名
        start_index: 連番の開始番号
        dpcm_path: ファイルパスのプレフィックス
    """
    lines = [f"; === {wave_type}波 dPCMサンプル定義 ==="]
    lines.append("; 注意: 各音階ごとにサンプルレートが異なります")
    lines.append("")

    for i, r in enumerate(results):
        note = r['note']
        index = start_index + i
        filepath = f"{dpcm_path}{r['filename']}"
        lines.append(f'@DPCM{index} = {{ "{filepath}", {r["rate_index"]}, 0, 0, 1 }}  ; {note}')

    lines.append("")
    lines.append("; 使用例（Eチャンネル）:")
    lines.append(f"; E @DPCM{start_index} | c4  ; ループ再生でトーン")

    return "\n".join(lines)


def main():
    import argparse

    parser = argparse.ArgumentParser(description='複数音階のdPCMを一括生成')
    parser.add_argument('--wave', '-w',
                        choices=['saw', 'triangle', 'sine', 'square', 'pulse25', 'pulse12'],
                        default='saw',
                        help='波形の種類')
    parser.add_argument('--hex', '-x',
                        type=str,
                        help='16進数文字列で波形を直接指定')
    parser.add_argument('--hex-file',
                        type=validate_readable_file,
                        help='16進数波形定義が書かれたファイルを読み込む')
    parser.add_argument('--fds',
                        type=str,
                        help='FDS形式（スペース区切り10進数0-63）で波形を直接指定')
    parser.add_argument('--fds-file',
                        type=validate_readable_file,
                        help='FDS形式波形定義が書かれたファイルを読み込む')
    parser.add_argument('--wav',
                        type=validate_readable_file,
                        help='WAVファイルから1周期分の波形を読み込む')
    parser.add_argument('--name', '-n',
                        type=str,
                        help='カスタム波形使用時のファイル名プレフィックス（デフォルト: custom）')
    parser.add_argument('--start',
                        type=validate_note_name,
                        default='C2',
                        help='生成する音階の開始ノート（デフォルト: C2）')
    parser.add_argument('--end',
                        type=validate_note_name,
                        default='F4',
                        help='生成する音階の終了ノート（デフォルト: F4）')
    parser.add_argument('--cycles', '-c',
                        type=validate_positive_int,
                        default=1,
                        help='含める波形の周期数（デフォルト: 1）')
    parser.add_argument('--volume', '-v',
                        type=validate_non_negative_float,
                        default=1.0,
                        help='音量（振幅）係数（デフォルト: 1.0、0.5=半分、2.0=2倍）')
    parser.add_argument('--auto-start', '-a',
                        action='store_true',
                        help='開始値を波形の最初の値に自動設定（デフォルト: 64から開始）')
    parser.add_argument('--loop-match', '-l',
                        action='store_true',
                        help='ループ終端のDC値を開始値に合わせる')
    parser.add_argument('--warmup',
                        action='store_true',
                        help='ウォームアップにより開始値を定常状態へ収束させ、安定した波形のみを出力')
    parser.add_argument('--fit',
                        action='store_true',
                        help='サンプル数をdPCM有効長(8+128n)にぴったり合わせる')
    parser.add_argument('--quality', '-q',
                        action='store_true',
                        help='fitモード時、サイズより高サンプルレートを優先（高音質）')
    parser.add_argument('--min-rate-index',
                        type=validate_rate_index,
                        help='fitモード時、サンプルレートの下限インデックス（0-15）を指定')
    parser.add_argument('--output-dir', '-o',
                        default='./dpcm_samples',
                        help='出力ディレクトリ')
    parser.add_argument('--dpcm-start-index',
                        type=validate_non_negative_int,
                        default=0,
                        help='ppmck定義の連番開始番号（デフォルト: 0）')
    parser.add_argument('--dpcm-path',
                        type=str,
                        default='',
                        help='ppmck定義でのdmcファイルパス（例: "D:\\myFolder\\"）')
    parser.add_argument('--preview', '-p',
                        action='store_true',
                        help='プレビューWAVを生成（各dmcと同名の.wav）')
    parser.add_argument('--preview-loops',
                        type=validate_positive_int,
                        default=4,
                        help='プレビューのループ回数（デフォルト: 4）')
    parser.add_argument('--raw-preview',
                        action='store_true',
                        help='エンコード前のWAVプレビューを生成（各dmcと同名の_raw.wav）')
    parser.add_argument('--raw-preview-loops',
                        type=validate_positive_int,
                        help='エンコード前プレビューのループ回数（デフォルト: --preview-loopsと同値）')
    parser.add_argument('--lowpass',
                        type=float,
                        help='ローパスフィルタのカットオフ周波数（Hz）（WAV入力時のみ有効）')
    parser.add_argument('--lowpass-order',
                        type=validate_positive_int,
                        default=63,
                        help='ローパスフィルタの次数（デフォルト: 63）')
    parser.add_argument('--no-auto-lowpass',
                        action='store_true',
                        help='自動ローパスフィルタを無効化（WAV入力時のみ有効）')
    parser.add_argument('--sub-octave',
                        type=validate_non_negative_float,
                        default=0.0,
                        help='1オクターブ下のサブハーモニックを混合する量（0.0=なし、0.3=基音の30%%）')

    args = parser.parse_args()

    # 生成する音階リストを決定
    notes = generate_note_range(args.start, args.end)
    if not notes:
        parser.error(f"開始ノート（{args.start}）は終了ノート（{args.end}）以下にしてください")

    # カスタム波形の読み込み
    custom_waveform = None
    wave_type = args.wave
    wav_sample_rate = None

    try:
        if args.hex:
            custom_waveform = parse_hex_waveform(args.hex)
            wave_type = args.name if args.name else "custom"
            print(f"=== カスタム波形 dPCMサンプル一括生成 ===")
            print(f"元波形サンプル数: {len(custom_waveform)}")
        elif args.hex_file:
            try:
                with open(args.hex_file, 'r') as f:
                    hex_data = f.read()
            except IOError as e:
                print(f"エラー: ファイルの読み込みに失敗しました: '{args.hex_file}' ({e})", file=sys.stderr)
                sys.exit(1)
            custom_waveform = parse_hex_waveform(hex_data)
            wave_type = args.name if args.name else os.path.splitext(os.path.basename(args.hex_file))[0]
            print(f"=== カスタム波形 dPCMサンプル一括生成 ===")
            print(f"ファイル: {args.hex_file}")
            print(f"元波形サンプル数: {len(custom_waveform)}")
        elif args.fds:
            custom_waveform = parse_fds_waveform(args.fds)
            wave_type = args.name if args.name else "fds"
            print(f"=== FDS波形 dPCMサンプル一括生成 ===")
            print(f"元波形サンプル数: {len(custom_waveform)}")
        elif args.fds_file:
            try:
                with open(args.fds_file, 'r') as f:
                    fds_data = f.read()
            except IOError as e:
                print(f"エラー: ファイルの読み込みに失敗しました: '{args.fds_file}' ({e})", file=sys.stderr)
                sys.exit(1)
            custom_waveform = parse_fds_waveform(fds_data)
            wave_type = args.name if args.name else os.path.splitext(os.path.basename(args.fds_file))[0]
            print(f"=== FDS波形 dPCMサンプル一括生成 ===")
            print(f"ファイル: {args.fds_file}")
            print(f"元波形サンプル数: {len(custom_waveform)}")
        elif args.wav:
            custom_waveform, wav_sample_rate = load_wav_waveform(args.wav)
            wave_type = args.name if args.name else os.path.splitext(os.path.basename(args.wav))[0]
            print(f"=== WAV波形 dPCMサンプル一括生成 ===")
            print(f"ファイル: {args.wav}")
            print(f"元波形: {len(custom_waveform)}サンプル, {wav_sample_rate}Hz")
        else:
            print(f"=== {args.wave}波 dPCMサンプル一括生成 ===")
    except ValueError as e:
        print(f"エラー: {e}", file=sys.stderr)
        sys.exit(1)
    except FileNotFoundError as e:
        print(f"エラー: {e}", file=sys.stderr)
        sys.exit(1)

    print(f"対象音域: {args.start} 〜 {args.end} ({len(notes)}音階)")
    print(f"出力先: {args.output_dir}")
    if args.cycles > 1:
        print(f"周期数: {args.cycles}")
    if args.volume != 1.0:
        if args.volume > 1.0:
            print(f"音量: {args.volume:.0%}（クリッピングの可能性あり）")
        else:
            print(f"音量: {args.volume:.0%}")
    if args.fit:
        if args.min_rate_index:
            quality_str = f"レート下限${args.min_rate_index:X}"
        elif args.quality:
            quality_str = "高品質優先"
        else:
            quality_str = "サイズ優先"
        print(f"fitモード: 有効 ({quality_str})")
    if args.auto_start:
        print(f"開始値自動設定: 有効")
    if args.loop_match:
        print(f"ループマッチ: 有効")
    if args.warmup:
        print(f"ウォームアップ: 有効（開始値を定常状態へ収束）")
    if args.wav and not args.no_auto_lowpass:
        if args.lowpass:
            print(f"ローパスフィルタ: {args.lowpass:.0f}Hz (次数: {args.lowpass_order})")
        else:
            print(f"ローパスフィルタ: 自動 (次数: {args.lowpass_order})")
    if args.sub_octave > 0:
        print(f"サブオクターブ: {args.sub_octave:.2f}（1オクターブ下を混合）")
    print()

    results, failures = generate_note_set(wave_type, args.output_dir, custom_waveform=custom_waveform,
                                 cycles=args.cycles, volume=args.volume, auto_start=args.auto_start,
                                 loop_match=args.loop_match, fit=args.fit, prefer_quality=args.quality,
                                 min_rate_index=args.min_rate_index or 0,
                                 preview=args.preview, preview_loops=args.preview_loops,
                                 raw_preview=args.raw_preview, raw_preview_loops=args.raw_preview_loops,
                                 warmup=args.warmup,
                                 lowpass_cutoff=args.lowpass, lowpass_order=args.lowpass_order,
                                 wav_sample_rate=wav_sample_rate, no_auto_lowpass=args.no_auto_lowpass,
                                 sub_octave=args.sub_octave, notes=notes)

    # 失敗レポート
    if failures:
        print()
        print(f"=== 失敗したノート ({len(failures)}件) ===")
        for note, reason in failures:
            if note:
                print(f"  {note}: {reason}")
            else:
                print(f"  {reason}")

    # 結果がない場合はppmck定義ファイルを出力しない
    if not results:
        print()
        print("生成されたファイルがありません。", file=sys.stderr)
        sys.exit(1)

    # ppmck定義ファイル出力
    defines = generate_ppmck_defines(results, wave_type,
                                      start_index=args.dpcm_start_index,
                                      dpcm_path=args.dpcm_path)
    defines_path = os.path.join(args.output_dir, f"{wave_type}_defines.txt")
    try:
        with open(defines_path, 'w') as f:
            f.write(defines)
    except PermissionError:
        print(f"エラー: 定義ファイルへの書き込み権限がありません: '{defines_path}'", file=sys.stderr)
        sys.exit(1)
    except IOError as e:
        print(f"エラー: 定義ファイルの書き込みに失敗しました: '{defines_path}' ({e})", file=sys.stderr)
        sys.exit(1)

    print()
    print(f"生成完了: {len(results)}ファイル")
    if failures:
        print(f"失敗: {len(failures)}件")
    print(f"ppmck定義: {defines_path}")
    print()

    # 合計サイズ
    total_size = sum(r['size'] for r in results)
    print(f"合計サイズ: {total_size} バイト ({total_size / 1024:.1f} KB)")


if __name__ == "__main__":
    main()
