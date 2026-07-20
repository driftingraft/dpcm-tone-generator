#!/usr/bin/env python3
"""
サンソフトベース方式 dPCMサンプル生成ツール

最小限のサンプル数で全音階をカバーするdPCMセットを生成します。
各サンプルを異なる再生レートで再利用することで、メモリ効率を最大化します。
"""

import os
import sys
import math
import argparse
import wave
from dpcm_generator import (
    generate_waveform, encode_dpcm, resample_waveform, adjust_volume,
    freq_from_note, find_best_fit_params,
    parse_hex_waveform, parse_fds_waveform, load_wav_waveform,
    note_to_semitone, semitone_to_note, generate_note_range,
    generate_preview, generate_raw_preview, decode_dpcm, apply_lowpass_filter,
    prepare_cycle_waveform, mix_sub_octave,
    SAMPLE_RATES_NTSC,
    # バリデーション関数
    validate_note_name, validate_positive_int, validate_non_negative_int,
    validate_positive_float, validate_non_negative_float, validate_readable_file,
)


def calculate_rate_ratios() -> list[float]:
    """
    最高レート($F)を基準とした各レートのセント差を計算

    Returns:
        16要素のリスト。各要素は$Fからのセント差（負の値または0）
    """
    base_rate = SAMPLE_RATES_NTSC[15]  # $F = 33143.9 Hz
    ratios = []
    for rate in SAMPLE_RATES_NTSC:
        cents = 1200 * math.log2(rate / base_rate)
        ratios.append(cents)
    return ratios


def get_reachable_notes(
    base_note: str,
    target_notes: list[str],
    max_cents_error: float = 25.0,
    prefer_higher_rate: bool = False
) -> list[tuple[str, int, float]]:
    """
    指定した基本ノートから、各レートで到達可能なノートを計算

    サンプルを最高レート($F)で再生すると基本ノートの音程になる。
    より低いレートで再生すると、低い音程になる。
    サンプル数は整数に丸められるため、その誤差も考慮する。

    Args:
        base_note: 基本サンプルのノート名 (例: "C3")
        target_notes: カバー対象のノートリスト
        max_cents_error: 許容誤差（セント）
        prefer_higher_rate: Trueの場合、許容誤差内で最高レートを優先

    Returns:
        (到達ノート名, レートインデックス, 誤差セント) のリスト
    """
    base_freq = freq_from_note(base_note)
    highest_rate = SAMPLE_RATES_NTSC[15]  # $F

    # 最高レートでの1周期サンプル数（整数に丸める）
    samples_per_cycle = round(highest_rate / base_freq)
    if samples_per_cycle < 1:
        samples_per_cycle = 1

    # 実際の基本周波数（丸め誤差を含む）
    actual_base_freq = highest_rate / samples_per_cycle

    reachable = []

    for target_note in target_notes:
        target_freq = freq_from_note(target_note)

        # 各レートでの実際の周波数との差をチェック
        best_rate_idx = None
        best_error = float('inf')

        for rate_idx, sample_rate in enumerate(SAMPLE_RATES_NTSC):
            # このレートで再生したときの実際の周波数
            # サンプル数は固定で、レートだけが変わる
            actual_freq = actual_base_freq * (sample_rate / highest_rate)

            if actual_freq > 0 and target_freq > 0:
                error_cents = 1200 * math.log2(actual_freq / target_freq)
            else:
                error_cents = float('inf')

            if abs(error_cents) <= max_cents_error:
                if prefer_higher_rate:
                    # 高レート優先: 許容誤差内で最高レートを選択
                    if best_rate_idx is None or rate_idx > best_rate_idx:
                        best_error = error_cents
                        best_rate_idx = rate_idx
                else:
                    # 最小誤差優先（デフォルト）
                    if abs(error_cents) < abs(best_error):
                        best_error = error_cents
                        best_rate_idx = rate_idx

        if best_rate_idx is not None:
            reachable.append((target_note, best_rate_idx, best_error))

    return reachable


def find_minimum_sample_set(
    start_note: str,
    end_note: str,
    max_cents_error: float = 25.0,
    prefer_higher_rate: bool = False,
    prefer_quality_samples: bool = True,
    cycles: int = 8
) -> tuple[list[str], dict[str, tuple[str, int, float]]]:
    """
    指定音域をカバーする最小限の基本サンプルセットを計算（貪欲法）

    Args:
        start_note: 開始ノート (例: "C2")
        end_note: 終了ノート (例: "F4")
        max_cents_error: 許容誤差（セント）
        prefer_higher_rate: Trueの場合、許容誤差内で最高レートを優先
        prefer_quality_samples: Trueの場合、対象範囲内のサンプルを優先（音質優先）
                                Falseの場合、上に拡張した範囲も含める（サイズ優先）
        cycles: 波形の周期数（find_best_fit_paramsのmin_cyclesに使用）

    Returns:
        (基本サンプルノートのリスト, ノートマッピング辞書)
        マッピング辞書: {ノート名: (使用サンプルノート, レートインデックス, 誤差)}
    """
    # 対象ノートのリスト
    target_notes = generate_note_range(start_note, end_note)
    uncovered = set(target_notes)

    # 候補基本ノートの範囲を決定
    if prefer_quality_samples:
        # 音質優先：対象範囲内のみを候補とする
        # 高い音は高いレート($F)で再生、低い音は低いレートで再生となり、
        # 1周期あたりのサンプル数が多くなり音質が向上する
        candidate_bases = generate_note_range(start_note, end_note)
    else:
        # サイズ優先：対象範囲より上に拡張
        # 高いノートのサンプルは低いレートで低い音を出せるため、
        # より少ないサンプル数で全音域をカバーできる
        extended_end_semitone = note_to_semitone(end_note) + 24  # 2オクターブ上まで
        candidate_bases = generate_note_range(start_note, semitone_to_note(extended_end_semitone))

    # 許容誤差内のパラメータが存在しないノートを候補から除外
    def has_valid_params(note: str) -> bool:
        """指定ノートで許容誤差内のdPCMパラメータが存在するかチェック"""
        freq = freq_from_note(note)
        result = find_best_fit_params(
            freq,
            min_cycles=cycles,
            max_cycles=max(cycles * 4, 128),
            prefer_quality=not prefer_quality_samples,
            min_rate_index=15,  # サンソフトベース方式は最高レート
            max_cents_error=max_cents_error
        )
        if result is None:
            return False
        # 実際の誤差をチェック（find_best_fit_paramsは許容誤差外でも誤差最小を返す）
        rate, rate_idx, spc, num_cycles, wave_samples = result
        actual_freq = rate / spc
        cents = 1200 * math.log2(actual_freq / freq)
        return abs(cents) <= max_cents_error

    valid_candidates = [n for n in candidate_bases if has_valid_params(n)]

    if not valid_candidates:
        raise ValueError(f"許容誤差{max_cents_error}cents内で生成可能な基本サンプル候補がありません")

    candidate_bases = valid_candidates

    base_samples = []
    note_mapping = {}

    # 貪欲法で集合被覆
    while uncovered:
        best_base = None
        best_coverage = []

        for candidate in candidate_bases:
            # このサンプルでカバーできるノートを計算
            reachable = get_reachable_notes(candidate, list(uncovered), max_cents_error, prefer_higher_rate)

            if len(reachable) > len(best_coverage):
                best_base = candidate
                best_coverage = reachable
            elif len(reachable) == len(best_coverage) and len(reachable) > 0:
                if prefer_quality_samples:
                    # 音質優先：より低いノートを優先
                    # 低いノートは高いレート($F)で再生され、1周期のサンプル数が多くなる
                    if note_to_semitone(candidate) < note_to_semitone(best_base):
                        best_base = candidate
                        best_coverage = reachable
                else:
                    # サイズ優先：より高いノートを優先
                    # 高いノートは多くの低い音をカバーでき、サンプル数を減らせる
                    if note_to_semitone(candidate) > note_to_semitone(best_base):
                        best_base = candidate
                        best_coverage = reachable

        if not best_base or len(best_coverage) == 0:
            # カバー不可能なノートが存在
            remaining = sorted(uncovered, key=note_to_semitone)
            raise ValueError(
                f"カバーできないノート: {remaining}"
                "（許容誤差を大きくするか、対象音域を調整してください）")

        base_samples.append(best_base)

        for note, rate_idx, error in best_coverage:
            # 既にマッピングがある場合は誤差が小さい方を採用
            if note not in note_mapping or abs(error) < abs(note_mapping[note][2]):
                note_mapping[note] = (best_base, rate_idx, error)
            uncovered.discard(note)

    return base_samples, note_mapping


def generate_sunsoft_samples(
    base_notes: list[str],
    wave_type: str,
    output_dir: str,
    prefix: str = "sunsoft_",
    custom_waveform: list[float] = None,
    cycles: int = 8,
    volume: float = 1.0,
    auto_start: bool = False,
    loop_match: bool = False,
    fit: bool = True,
    prefer_quality: bool = False,
    preview: bool = False,
    preview_loops: int = 4,
    raw_preview: bool = False,
    raw_preview_loops: int = None,
    warmup: bool = False,
    max_cents_error: float = 15.0,
    lowpass_cutoff: float = None,
    lowpass_order: int = 63,
    wav_sample_rate: int = None,
    no_auto_lowpass: bool = False,
    sub_octave: float = 0.0
) -> tuple[list[dict], list[tuple[str, str]]]:
    """
    基本サンプルファイル群を生成

    各サンプルは最高レート($F)で基本ノートを再生することを想定して生成

    Returns:
        (成功リスト, 失敗リスト)
        成功リスト: 生成されたサンプル情報のリスト
        失敗リスト: 失敗したノートと理由のタプル
    """
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

    for base_note in base_notes:
        try:
            target_freq = freq_from_note(base_note)

            # fitモードで最適パラメータを探索（最高レート$F=15を想定）
            # loop_matchが有効な場合、余地を確保
            loop_reserve = 64 if loop_match else 0
            if fit:
                # サブオクターブ混合時はループ境界整合のため偶数周期を要求
                require_even = sub_octave > 0
                result = find_best_fit_params(
                    target_freq,
                    min_cycles=cycles,
                    max_cycles=max(cycles * 4, 128),
                    prefer_quality=prefer_quality,
                    min_rate_index=15,  # 最高レートを使用
                    loop_match_reserve=loop_reserve,
                    max_cents_error=max_cents_error,
                    require_even_cycles=require_even
                )
                if result is None:
                    # フォールバック: min_rate_indexを緩和
                    result = find_best_fit_params(
                        target_freq,
                        min_cycles=cycles,
                        max_cycles=max(cycles * 4, 128),
                        prefer_quality=prefer_quality,
                        min_rate_index=12,
                        loop_match_reserve=loop_reserve,
                        max_cents_error=max_cents_error,
                        require_even_cycles=require_even
                    )
                if result is None and require_even:
                    # 偶数周期の解が見つからない場合は制約を外して再探索
                    print(f"  {base_note}: 偶数周期の解なし（サブオクターブがループ境界でずれる可能性）")
                    result = find_best_fit_params(
                        target_freq,
                        min_cycles=cycles,
                        max_cycles=max(cycles * 4, 128),
                        prefer_quality=prefer_quality,
                        min_rate_index=12,
                        loop_match_reserve=loop_reserve,
                        max_cents_error=max_cents_error
                    )
                if result is None:
                    print(f"  {base_note}: スキップ（適切なパラメータなし）")
                    failures.append((base_note, "適切なパラメータが見つかりません"))
                    continue
                sample_rate, rate_index, num_samples, num_cycles, total_samples = result
            else:
                # fitなしの場合は最高レートで固定計算
                sample_rate = SAMPLE_RATES_NTSC[15]
                num_samples = round(sample_rate / target_freq)
                rate_index = 15
                num_cycles = cycles
                # サブオクターブ混合時はループ境界整合のため偶数周期に揃える
                if sub_octave > 0 and num_cycles % 2 != 0:
                    num_cycles += 1
                total_samples = num_samples * num_cycles

            actual_freq = sample_rate / num_samples

            # ファイル名（#を_sに置換）
            safe_note = base_note.replace("#", "_s")
            filename = f"{prefix}{wave_type}_{safe_note}.dmc"
            filepath = os.path.join(output_dir, filename)

            # ローパスフィルタ処理
            filtered_waveform = custom_waveform
            if custom_waveform and wav_sample_rate and not no_auto_lowpass:
                # WAV入力: 読み込み時のサンプルレートを使って処理
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
            elif custom_waveform and not wav_sample_rate:
                # FDS/HEX入力: 明示指定のローパス、または縮小時の自動アンチエイリアス
                filtered_waveform, _ = prepare_cycle_waveform(
                    custom_waveform, num_samples, target_freq,
                    lowpass_cutoff=lowpass_cutoff, lowpass_order=lowpass_order,
                    no_auto_lowpass=no_auto_lowpass
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
                print(f"  {base_note}: 失敗（書き込み権限なし）")
                failures.append((base_note, f"ファイル書き込み権限がありません: '{filepath}'"))
                continue
            except IOError as e:
                print(f"  {base_note}: 失敗（書き込みエラー）")
                failures.append((base_note, f"ファイル書き込みエラー: {e}"))
                continue

            # プレビュー生成
            if preview:
                preview_start = actual_start
                preview_path = os.path.splitext(filepath)[0] + ".wav"
                try:
                    generate_preview(dpcm_data, sample_rate, preview_path,
                                    loops=preview_loops, start_value=preview_start)
                except (PermissionError, IOError) as e:
                    print(f"  {base_note}: プレビュー生成失敗 ({e})")

            # エンコード前プレビュー生成
            if raw_preview:
                raw_preview_path = os.path.splitext(filepath)[0] + "_raw.wav"
                raw_loops = raw_preview_loops if raw_preview_loops else preview_loops
                try:
                    generate_raw_preview(waveform, sample_rate, raw_preview_path, loops=raw_loops)
                except (PermissionError, IOError) as e:
                    print(f"  {base_note}: エンコード前プレビュー生成失敗 ({e})")

            results.append({
                'note': base_note,
                'filename': filename,
                'rate_index': rate_index,
                'samples_per_cycle': num_samples,
                'cycles': num_cycles,
                'size': len(dpcm_data),
                'actual_freq': actual_freq,
                'target_freq': target_freq,
                'start_value': actual_start,
            })

            print(f"  基本サンプル {base_note}: {filename} (rate=${rate_index:X}, {len(dpcm_data)}bytes)")

        except Exception as e:
            print(f"  {base_note}: 失敗（予期しないエラー）")
            failures.append((base_note, str(e)))
            continue

    return results, failures


def generate_sunsoft_defines(
    base_samples: list[dict],
    note_mapping: dict[str, tuple[str, int, float]],
    target_notes: list[str],
    wave_type: str,
    start_note: str,
    end_note: str,
    max_cents_error: float,
    start_index: int = 0,
    dpcm_path: str = "",
    lang: str = "ja"
) -> str:
    """
    ppmck形式の定義ファイルを生成

    Args:
        start_index: 連番の開始番号
        dpcm_path: ファイルパスのプレフィックス
        lang: コメントの言語（'ja'|'en'、既定 'ja'）。GUIの英語表示用。
    """
    en = (lang == "en")
    lines = []

    # ヘッダー
    if en:
        lines.append(f"; === {wave_type} dPCM sample definitions (Sunsoft-base method) ===")
        lines.append(f"; Range: {start_note}-{end_note} ({len(target_notes)} notes)")
        lines.append(f"; Base samples: {len(base_samples)}")
        lines.append(f"; Tolerance: {max_cents_error} cents")
    else:
        lines.append(f"; === {wave_type} dPCMサンプル定義（サンソフトベース方式） ===")
        lines.append(f"; 対象音域: {start_note}〜{end_note} ({len(target_notes)}音階)")
        lines.append(f"; 基本サンプル数: {len(base_samples)}")
        lines.append(f"; 許容誤差: {max_cents_error} cents")
    lines.append("")

    # 基本サンプル情報（参考用、番号は0から）
    lines.append("; --- Base sample info (reference) ---" if en
                 else "; --- 基本サンプル情報（参考） ---")
    base_note_to_idx = {}
    for idx, sample in enumerate(base_samples):
        base_note_to_idx[sample['note']] = idx
        filepath = f"{dpcm_path}{sample['filename']}"
        lines.append(f"; #{idx}: {filepath} ({sample['note']}, {sample['size']}bytes)")
    lines.append("")

    # ノートマッピング表（コメント）
    if en:
        lines.append("; --- Note mapping table ---")
        lines.append("; To play each note, play the given sample at the given rate")
        lines.append(";")
        lines.append("; Note     | Sample   | Rate   | Error(cents)")
    else:
        lines.append("; --- ノートマッピング表 ---")
        lines.append("; 各ノートを再生するには、指定サンプルを指定レートで再生します")
        lines.append(";")
        lines.append("; ノート   | サンプル | レート | 誤差(cents)")
    lines.append("; ---------|----------|--------|------------")

    uncoverable = "(not coverable)" if en else "(カバー不可)"
    for note in target_notes:
        if note in note_mapping:
            base_note, rate_idx, error = note_mapping[note]
            sample_idx = base_note_to_idx[base_note]
            error_str = f"{error:+.1f}"
            lines.append(f"; {note:8s} | @DPCM{sample_idx}  | ${rate_idx:X}     | {error_str}")
        else:
            lines.append(f"; {note:8s} | {uncoverable}")
    lines.append("")

    # ノート別の定義（各ノートに直接@DPCM番号を割り当て）
    if en:
        lines.append("; --- Per-note sample definitions ---")
        lines.append(f"; Definitions for each note (@DPCM numbers from {start_index})")
    else:
        lines.append("; --- ノート別サンプル定義 ---")
        lines.append(f"; 各ノートに対応する定義（@DPCM番号{start_index}以降）")
    lines.append("")

    err_label = "error" if en else "誤差"
    dpcm_num = start_index
    first_covered = None
    for note in target_notes:
        if note in note_mapping:
            base_note, rate_idx, error = note_mapping[note]
            # 基本サンプルのファイル名を取得
            sample_info = next((s for s in base_samples if s['note'] == base_note), None)
            if sample_info:
                filepath = f"{dpcm_path}{sample_info['filename']}"
                lines.append(f"@DPCM{dpcm_num} = {{ \"{filepath}\", {rate_idx}, 0, 0, 1 }}  ; {note} ({err_label}: {error:+.1f}cents)")
                if first_covered is None:
                    first_covered = note
                dpcm_num += 1

    if first_covered is not None:
        lines.append("")
        if en:
            lines.append("; Example (E channel): use the n command (n<num> plays @DPCM<num>)")
            lines.append(f"; E n{start_index}  ; {first_covered} as a tone via loop playback")
        else:
            lines.append("; 使用例（Eチャンネル）: nコマンドで指定（n<番号> で @DPCM<番号> を発音）")
            lines.append(f"; E n{start_index}  ; {first_covered} をループ再生でトーン")

    return "\n".join(lines)


def generate_scale_preview(
    target_notes: list[str],
    note_mapping: dict[str, tuple[str, int, float]],
    base_samples: list[dict],
    output_dir: str,
    output_filename: str = "scale_preview.wav",
    duration: float = 0.5,
    auto_start: bool = False
) -> str:
    """
    音階を順番に鳴らすスケールプレビューWAVを生成

    各ノートを指定した持続時間ずつ鳴らし、1つのWAVファイルとして出力する。

    Args:
        target_notes: 鳴らすノートのリスト（音階順）
        note_mapping: {ノート名: (基本サンプルノート, レートインデックス, 誤差)}
        base_samples: 生成された基本サンプル情報のリスト
        output_dir: 出力ディレクトリ
        output_filename: 出力ファイル名
        duration: 各音の持続時間（秒）
        auto_start: 開始値を自動設定するかどうか

    Returns:
        出力ファイルパス
    """
    # 出力サンプルレート（最高レートを使用）
    output_sample_rate = int(round(SAMPLE_RATES_NTSC[15]))  # 33144 Hz

    # 基本サンプルノートからファイル情報へのマッピング
    base_note_to_info = {s['note']: s for s in base_samples}

    all_samples = []

    for note in target_notes:
        if note not in note_mapping:
            continue

        base_note, rate_idx, _ = note_mapping[note]

        if base_note not in base_note_to_info:
            continue

        sample_info = base_note_to_info[base_note]
        filepath = os.path.join(output_dir, sample_info['filename'])

        # dPCMファイルを読み込む
        try:
            with open(filepath, 'rb') as f:
                dpcm_data = f.read()
        except (IOError, FileNotFoundError):
            continue

        # このノート用のサンプルレート
        note_sample_rate = SAMPLE_RATES_NTSC[rate_idx]

        # dPCMをデコード
        # auto_startの場合、エンコード時に使用した開始値を使う
        if auto_start and 'start_value' in sample_info:
            start_value = sample_info['start_value']
        else:
            start_value = 64
        decoded = decode_dpcm(dpcm_data, start_value)

        # 持続時間分のサンプル数（このレートで）
        samples_needed = int(note_sample_rate * duration)

        # ループして必要なサンプル数を確保
        if len(decoded) > 0:
            note_samples = []
            while len(note_samples) < samples_needed:
                note_samples.extend(decoded)
            note_samples = note_samples[:samples_needed]
        else:
            continue

        # 出力サンプルレートにリサンプリング
        output_samples_count = int(output_sample_rate * duration)
        if len(note_samples) != output_samples_count:
            # 線形補間でリサンプリング
            resampled = []
            for i in range(output_samples_count):
                pos = i * len(note_samples) / output_samples_count
                idx_low = int(pos)
                idx_high = min(idx_low + 1, len(note_samples) - 1)
                frac = pos - idx_low
                value = note_samples[idx_low] * (1 - frac) + note_samples[idx_high] * frac
                resampled.append(int(value))
            note_samples = resampled

        all_samples.extend(note_samples)

    if not all_samples:
        raise ValueError("スケールプレビューに含めるサンプルがありません")

    # WAVファイルとして出力
    output_path = os.path.join(output_dir, output_filename)

    # 0-127を0-255（8bit unsigned）にスケーリング
    wav_samples = bytes([min(255, s * 2) for s in all_samples])

    with wave.open(output_path, 'wb') as wf:
        wf.setnchannels(1)
        wf.setsampwidth(1)  # 8bit
        wf.setframerate(output_sample_rate)
        wf.writeframes(wav_samples)

    return output_path


def analyze_coverage(
    start_note: str,
    end_note: str,
    max_cents_error: float = 25.0,
    prefer_higher_rate: bool = False,
    prefer_quality_samples: bool = True,
    cycles: int = 8
) -> None:
    """
    分析のみ実行（ファイル生成なし）
    """
    print(f"\n=== サンソフトベース方式 分析 ===")
    print(f"対象音域: {start_note} 〜 {end_note}")
    print(f"許容誤差: {max_cents_error} cents")
    if prefer_quality_samples:
        print(f"モード: 音質優先（対象範囲内のサンプルを使用）")
    else:
        print(f"モード: サイズ優先（拡張範囲のサンプルも使用）")
    if prefer_higher_rate:
        print(f"レート選択: 高レート優先")
    print()

    # 16種類のレートとセント差を表示
    print("dPCMサンプルレート（$F基準のセント差）:")
    rate_ratios = calculate_rate_ratios()
    for idx, (rate, cents) in enumerate(zip(SAMPLE_RATES_NTSC, rate_ratios)):
        print(f"  ${idx:X}: {rate:8.2f} Hz ({cents:+7.1f} cents)")
    print()

    # 最小サンプルセットを計算
    try:
        base_samples, note_mapping = find_minimum_sample_set(
            start_note, end_note, max_cents_error, prefer_higher_rate, prefer_quality_samples,
            cycles=cycles
        )
    except ValueError as e:
        print(f"エラー: {e}")
        return

    print(f"必要な基本サンプル数: {len(base_samples)}")
    print(f"基本サンプルノート: {', '.join(base_samples)}")
    print()

    # マッピング詳細
    target_notes = generate_note_range(start_note, end_note)
    print("ノートマッピング:")
    print(f"{'ノート':8s} | {'基本サンプル':10s} | {'レート':6s} | 誤差")
    print("-" * 50)

    for note in target_notes:
        if note in note_mapping:
            base_note, rate_idx, error = note_mapping[note]
            print(f"{note:8s} | {base_note:10s} | ${rate_idx:X}     | {error:+.1f} cents")

    # 統計
    errors = [abs(note_mapping[n][2]) for n in target_notes if n in note_mapping]
    if errors:
        print()
        print(f"誤差統計:")
        print(f"  最大誤差: {max(errors):.1f} cents")
        print(f"  平均誤差: {sum(errors)/len(errors):.1f} cents")
        print(f"  カバー率: {len(errors)}/{len(target_notes)} ({100*len(errors)/len(target_notes):.1f}%)")


def main():
    parser = argparse.ArgumentParser(
        description='サンソフトベース方式 dPCMサンプル生成ツール',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
例:
  # 分析のみ実行（波形指定不要）
  python dpcm_sunsoft.py --analyze-only --start C2 --end F4

  # サンプル生成
  python dpcm_sunsoft.py --wave saw --start C2 --end F4 --fit --output-dir ./sunsoft_samples
"""
    )

    # 波形オプション
    wave_group = parser.add_mutually_exclusive_group(required=True)
    wave_group.add_argument('--wave', choices=['saw', 'triangle', 'sine', 'square', 'pulse25', 'pulse12'],
                           help='波形タイプ')
    wave_group.add_argument('--fds', metavar='FILE', type=validate_readable_file,
                           help='FDS波形ファイル')
    wave_group.add_argument('--hex', metavar='STRING', help='16進数波形データ')
    wave_group.add_argument('--wav', metavar='FILE', type=validate_readable_file,
                           help='WAVファイル')
    wave_group.add_argument('--analyze-only', action='store_true',
                           help='分析のみ実行（サンプル生成なし）')

    # 音域オプション
    parser.add_argument('--start', type=validate_note_name, default='C2',
                       help='開始ノート (デフォルト: C2)')
    parser.add_argument('--end', type=validate_note_name, default='F4',
                       help='終了ノート (デフォルト: F4)')

    # 誤差オプション
    parser.add_argument('--max-error', type=validate_positive_float, default=25.0,
                       help='許容誤差（セント）(デフォルト: 25.0)')

    # 出力オプション
    parser.add_argument('--output-dir', '-o', default='./sunsoft_dpcm',
                       help='出力ディレクトリ (デフォルト: ./sunsoft_dpcm)')
    parser.add_argument('--prefix', default='sunsoft_',
                       help='ファイル名プレフィックス (デフォルト: sunsoft_)')

    # サンプル生成オプション
    parser.add_argument('--fit', action='store_true',
                       help='fitモード（dPCM有効サンプル数に合わせる）')
    parser.add_argument('--cycles', type=validate_positive_int, default=8,
                       help='周期数 (デフォルト: 8)')
    parser.add_argument('--volume', '-v', type=validate_non_negative_float, default=1.0,
                       help='音量 (0.0-1.0, デフォルト: 1.0)')
    parser.add_argument('--auto-start', action='store_true',
                       help='開始値を波形に合わせる')
    parser.add_argument('--loop-match', action='store_true',
                       help='ループ時に開始値に戻るよう調整')
    parser.add_argument('--warmup', action='store_true',
                       help='ウォームアップにより開始値を定常状態へ収束させ、安定した波形のみを出力')
    parser.add_argument('--prefer-quality', action='store_true',
                       help='音質優先モード（高サンプルレート優先、レート選択でも高レートを優先）')
    parser.add_argument('--size-priority', action='store_true',
                       help='サイズ優先モード（サンプル数を最小化、対象範囲外のサンプルも使用）')
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
    parser.add_argument('--scale-preview',
                       action='store_true',
                       help='音階プレビューWAVを生成（全ノートを順番に再生）')
    parser.add_argument('--scale-duration',
                       type=validate_positive_float,
                       default=0.5,
                       help='音階プレビューの各音の持続時間（秒）（デフォルト: 0.5）')
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

    # 分析のみモード
    # prefer_quality_samplesはデフォルトTrue、--size-priority指定時にFalse
    prefer_quality_samples = not args.size_priority
    if args.analyze_only:
        analyze_coverage(args.start, args.end, args.max_error, args.prefer_quality, prefer_quality_samples,
                        cycles=args.cycles)
        return

    # 波形タイプの決定
    wav_sample_rate = None
    try:
        if args.wave:
            wave_type = args.wave
            custom_waveform = None
        elif args.fds:
            wave_type = os.path.splitext(os.path.basename(args.fds))[0]
            try:
                with open(args.fds, 'r') as f:
                    custom_waveform = parse_fds_waveform(f.read())
            except IOError as e:
                print(f"エラー: ファイルの読み込みに失敗しました: '{args.fds}' ({e})", file=sys.stderr)
                sys.exit(1)
        elif args.hex:
            wave_type = "hex"
            custom_waveform = parse_hex_waveform(args.hex)
        elif args.wav:
            wave_type = os.path.splitext(os.path.basename(args.wav))[0]
            custom_waveform, wav_sample_rate = load_wav_waveform(args.wav)
        else:
            parser.error('波形タイプを指定してください')
            return
    except ValueError as e:
        print(f"エラー: {e}", file=sys.stderr)
        sys.exit(1)
    except FileNotFoundError as e:
        print(f"エラー: {e}", file=sys.stderr)
        sys.exit(1)

    print(f"=== サンソフトベース方式 dPCMサンプル生成 ===")
    print(f"波形: {wave_type}")
    print(f"対象音域: {args.start} 〜 {args.end}")
    print(f"許容誤差: {args.max_error} cents")
    if args.volume != 1.0:
        if args.volume > 1.0:
            print(f"音量: {args.volume:.0%}（クリッピングの可能性あり）")
        else:
            print(f"音量: {args.volume:.0%}")
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

    # 最小サンプルセットを計算
    try:
        base_sample_notes, note_mapping = find_minimum_sample_set(
            args.start, args.end, args.max_error, args.prefer_quality, prefer_quality_samples,
            cycles=args.cycles
        )
    except ValueError as e:
        print(f"エラー: {e}")
        return

    target_notes = generate_note_range(args.start, args.end)

    print(f"必要な基本サンプル数: {len(base_sample_notes)}")
    print(f"基本サンプルノート: {', '.join(base_sample_notes)}")
    print()

    # サンプル生成
    print("サンプル生成中...")
    base_samples, failures = generate_sunsoft_samples(
        base_sample_notes,
        wave_type,
        args.output_dir,
        prefix=args.prefix,
        custom_waveform=custom_waveform,
        cycles=args.cycles,
        volume=args.volume,
        auto_start=args.auto_start,
        loop_match=args.loop_match,
        fit=args.fit,
        prefer_quality=args.prefer_quality,
        preview=args.preview,
        preview_loops=args.preview_loops,
        raw_preview=args.raw_preview,
        raw_preview_loops=args.raw_preview_loops,
        warmup=args.warmup,
        max_cents_error=args.max_error,
        lowpass_cutoff=args.lowpass,
        lowpass_order=args.lowpass_order,
        wav_sample_rate=wav_sample_rate,
        no_auto_lowpass=args.no_auto_lowpass,
        sub_octave=args.sub_octave
    )
    print()

    # 失敗レポート
    if failures:
        print(f"=== 失敗したサンプル ({len(failures)}件) ===")
        for note, reason in failures:
            if note:
                print(f"  {note}: {reason}")
            else:
                print(f"  {reason}")
        print()

    # 結果がない場合はエラー
    if not base_samples:
        print("生成されたサンプルがありません。", file=sys.stderr)
        sys.exit(1)

    # 定義ファイル生成
    defines = generate_sunsoft_defines(
        base_samples,
        note_mapping,
        target_notes,
        wave_type,
        args.start,
        args.end,
        args.max_error,
        start_index=args.dpcm_start_index,
        dpcm_path=args.dpcm_path
    )

    defines_file = os.path.join(args.output_dir, f"{args.prefix}{wave_type}_defines.txt")
    try:
        with open(defines_file, 'w', encoding='utf-8') as f:
            f.write(defines)
    except PermissionError:
        print(f"エラー: 定義ファイルへの書き込み権限がありません: '{defines_file}'", file=sys.stderr)
        sys.exit(1)
    except IOError as e:
        print(f"エラー: 定義ファイルの書き込みに失敗しました: '{defines_file}' ({e})", file=sys.stderr)
        sys.exit(1)

    print(f"定義ファイル: {defines_file}")

    # スケールプレビュー生成
    if args.scale_preview:
        try:
            scale_preview_path = generate_scale_preview(
                target_notes,
                note_mapping,
                base_samples,
                args.output_dir,
                output_filename=f"{args.prefix}{wave_type}_scale.wav",
                duration=args.scale_duration,
                auto_start=args.auto_start
            )
            total_duration = len(target_notes) * args.scale_duration
            print(f"スケールプレビュー: {scale_preview_path} ({total_duration:.1f}秒)")
        except ValueError as e:
            print(f"スケールプレビュー生成失敗: {e}", file=sys.stderr)
        except (PermissionError, IOError) as e:
            print(f"スケールプレビュー書き込み失敗: {e}", file=sys.stderr)

    # サマリー
    total_size = sum(s['size'] for s in base_samples)
    print()
    print(f"=== 生成完了 ===")
    print(f"基本サンプル数: {len(base_samples)}")
    if failures:
        print(f"失敗: {len(failures)}件")
    print(f"合計サイズ: {total_size} bytes")
    print(f"カバー音階数: {len(target_notes)}")

    # 従来方式との比較（概算）
    if len(base_samples) > 0:
        traditional_size = len(target_notes) * (total_size // len(base_samples))
        print(f"（参考）従来方式推定サイズ: {traditional_size} bytes")
        if traditional_size > 0:
            print(f"削減率: {100 * (1 - total_size / traditional_size):.1f}%")


if __name__ == '__main__':
    main()
