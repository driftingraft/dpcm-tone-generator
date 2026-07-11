#!/usr/bin/env python3
"""
NES dPCM (DMC) 波形ジェネレーター
トーン用の1周期波形をdPCM形式で出力します
"""

import math
import struct
import argparse
import wave
import sys
import os
import re

# NTSCのdPCMサンプルレート（16種類）
SAMPLE_RATES_NTSC = [
    4181.71, 4709.93, 5264.04, 5593.04,
    6257.95, 7046.35, 7919.35, 8363.42,
    9419.86, 11186.1, 12604.0, 13982.6,
    16884.6, 21306.8, 24858.0, 33143.9
]

# 音名の正規表現パターン
NOTE_PATTERN = re.compile(r'^[A-Ga-g][#b]?[0-9]$')


# =============================================================================
# バリデーション関数（argparse type用）
# =============================================================================

def validate_note_name(value: str) -> str:
    """
    音名形式をチェック（C4, A#3, Bb2など）
    argparseのtype引数用
    """
    if not NOTE_PATTERN.match(value):
        raise argparse.ArgumentTypeError(
            f"無効な音名形式です: '{value}' (例: C4, A#3, Bb2)"
        )
    return value


def validate_positive_float(value: str) -> float:
    """
    正の浮動小数点数をチェック（周波数など）
    argparseのtype引数用
    """
    try:
        fval = float(value)
    except ValueError:
        raise argparse.ArgumentTypeError(
            f"数値を指定してください: '{value}'"
        )
    if fval <= 0:
        raise argparse.ArgumentTypeError(
            f"正の数値を指定してください: {value}"
        )
    return fval


def validate_non_negative_float(value: str) -> float:
    """
    0以上の浮動小数点数をチェック（音量など）
    argparseのtype引数用
    """
    try:
        fval = float(value)
    except ValueError:
        raise argparse.ArgumentTypeError(
            f"数値を指定してください: '{value}'"
        )
    if fval < 0:
        raise argparse.ArgumentTypeError(
            f"0以上の数値を指定してください: {value}"
        )
    return fval


def validate_positive_int(value: str) -> int:
    """
    正の整数をチェック（cycles）
    argparseのtype引数用
    """
    try:
        ival = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError(
            f"整数を指定してください: '{value}'"
        )
    if ival <= 0:
        raise argparse.ArgumentTypeError(
            f"正の整数を指定してください: {value}"
        )
    return ival


def validate_non_negative_int(value: str) -> int:
    """
    0以上の整数をチェック（dpcm-start-indexなど）
    argparseのtype引数用
    """
    try:
        ival = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError(
            f"整数を指定してください: '{value}'"
        )
    if ival < 0:
        raise argparse.ArgumentTypeError(
            f"0以上の整数を指定してください: {value}"
        )
    return ival


def validate_rate_index(value: str) -> int:
    """
    サンプルレートインデックス（0-15）をチェック
    argparseのtype引数用
    """
    try:
        ival = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError(
            f"整数を指定してください: '{value}'"
        )
    if ival < 0 or ival > 15:
        raise argparse.ArgumentTypeError(
            f"レートインデックスは0-15の範囲で指定してください: {value}"
        )
    return ival


def validate_readable_file(value: str) -> str:
    """
    読み取り可能なファイルパスをチェック
    argparseのtype引数用
    """
    if not os.path.exists(value):
        raise argparse.ArgumentTypeError(
            f"ファイルが見つかりません: '{value}'"
        )
    if not os.path.isfile(value):
        raise argparse.ArgumentTypeError(
            f"ファイルではありません: '{value}'"
        )
    if not os.access(value, os.R_OK):
        raise argparse.ArgumentTypeError(
            f"ファイルを読み取る権限がありません: '{value}'"
        )
    return value


# =============================================================================
# 波形処理関数
# =============================================================================

def apply_lowpass_filter(samples: list[float], sample_rate: int,
                          cutoff_freq: float, order: int = 63) -> list[float]:
    """
    窓関数法によるFIRローパスフィルタを適用

    Args:
        samples: 0.0〜1.0の波形サンプル列
        sample_rate: 入力サンプルレート（Hz）
        cutoff_freq: カットオフ周波数（Hz）
        order: フィルタ次数（奇数推奨、デフォルト: 63）

    Returns:
        フィルタ適用後の波形（0.0〜1.0にクリップ）

    Raises:
        ValueError: cutoff_freqまたはorderが不正な場合
    """
    if cutoff_freq <= 0:
        raise ValueError(f"カットオフ周波数は正の値を指定してください: {cutoff_freq}")
    if order < 1:
        raise ValueError(f"フィルタ次数は1以上を指定してください: {order}")
    if cutoff_freq >= sample_rate / 2:
        # ナイキスト周波数以上の場合はフィルタ不要
        return samples

    if not samples:
        return samples

    # 正規化カットオフ周波数（0〜1、1がナイキスト周波数）
    normalized_cutoff = cutoff_freq / (sample_rate / 2)

    # フィルタ係数を生成（sinc関数 + ハミング窓）
    half_order = order // 2
    coefficients = []

    for n in range(-half_order, half_order + 1):
        if n == 0:
            # sinc(0) = 1
            h = normalized_cutoff
        else:
            # sinc関数: sin(πx) / (πx)
            h = math.sin(math.pi * normalized_cutoff * n) / (math.pi * n)

        # ハミング窓を適用
        window = 0.54 - 0.46 * math.cos(2 * math.pi * (n + half_order) / order)
        coefficients.append(h * window)

    # 係数を正規化（合計が1になるように）
    coef_sum = sum(coefficients)
    if coef_sum != 0:
        coefficients = [c / coef_sum for c in coefficients]

    # 畳み込みによるフィルタ適用
    result = []
    num_samples = len(samples)

    for i in range(num_samples):
        acc = 0.0
        for j, coef in enumerate(coefficients):
            # 境界処理：ミラーリング
            idx = i - half_order + j
            if idx < 0:
                idx = -idx
            elif idx >= num_samples:
                idx = 2 * num_samples - idx - 2
            # インデックスが範囲外の場合は端の値を使用
            if idx < 0:
                idx = 0
            elif idx >= num_samples:
                idx = num_samples - 1
            acc += samples[idx] * coef
        # クリッピング
        result.append(max(0.0, min(1.0, acc)))

    return result


def load_wav_waveform(filepath: str) -> tuple[list[float], int]:
    """
    WAVファイルから波形データを読み込む

    Returns:
        (samples, sample_rate): 0.0〜1.0に正規化されたサンプル列とサンプルレート

    Raises:
        FileNotFoundError: ファイルが存在しない場合
        ValueError: WAVファイルの形式に問題がある場合
    """
    if not os.path.exists(filepath):
        raise FileNotFoundError(f"WAVファイルが見つかりません: '{filepath}'")

    try:
        wf = wave.open(filepath, 'rb')
    except wave.Error as e:
        raise ValueError(f"WAVファイルを開けません: '{filepath}' ({e})")

    try:
        n_channels = wf.getnchannels()
        sample_width = wf.getsampwidth()
        sample_rate = wf.getframerate()
        n_frames = wf.getnframes()

        if n_frames == 0:
            raise ValueError(f"WAVファイルにサンプルが含まれていません: '{filepath}'")

        raw_data = wf.readframes(n_frames)
    finally:
        wf.close()

    # サンプル幅に応じてフォーマットを決定
    if sample_width == 1:
        # 8bit unsigned
        fmt = f'{n_frames * n_channels}B'
        samples_raw = struct.unpack(fmt, raw_data)
        # 0-255 → -1.0〜1.0
        samples_raw = [(s - 128) / 128.0 for s in samples_raw]
    elif sample_width == 2:
        # 16bit signed
        fmt = f'<{n_frames * n_channels}h'
        samples_raw = struct.unpack(fmt, raw_data)
        # -32768〜32767 → -1.0〜1.0
        samples_raw = [s / 32768.0 for s in samples_raw]
    elif sample_width == 3:
        # 24bit signed
        samples_raw = []
        for i in range(0, len(raw_data), 3 * n_channels):
            for ch in range(n_channels):
                offset = i + ch * 3
                # リトルエンディアン24bit
                b = raw_data[offset:offset+3]
                value = b[0] | (b[1] << 8) | (b[2] << 16)
                if value >= 0x800000:
                    value -= 0x1000000
                samples_raw.append(value / 8388608.0)
    else:
        raise ValueError(f"未対応のサンプル幅: {sample_width}バイト（'{filepath}'）")

    # ステレオの場合はモノラルに変換（チャンネルを平均）
    if n_channels > 1:
        samples_mono = []
        for i in range(0, len(samples_raw), n_channels):
            avg = sum(samples_raw[i:i+n_channels]) / n_channels
            samples_mono.append(avg)
        samples_raw = samples_mono

    # -1.0〜1.0 を 0.0〜1.0 に変換
    samples_normalized = [(s + 1.0) / 2.0 for s in samples_raw]

    # クリッピング
    samples_normalized = [max(0.0, min(1.0, s)) for s in samples_normalized]

    return samples_normalized, sample_rate

def parse_hex_waveform(hex_string: str) -> list[float]:
    """
    16進数文字列から波形データをパース
    2文字ずつ符号付き8bit整数として解釈し、0.0〜1.0に正規化

    例: "010102050b..." -> [0.5, 0.5, 0.508, ...]

    Raises:
        ValueError: 入力が空または不正な16進文字を含む場合
    """
    # 空白や改行を除去
    hex_string = hex_string.strip().replace(" ", "").replace("\n", "").replace("\r", "")

    if not hex_string:
        raise ValueError("16進数文字列が空です")

    if len(hex_string) % 2 != 0:
        raise ValueError("16進数文字列の長さが奇数です")

    # 不正な16進文字をチェック
    if not re.match(r'^[0-9A-Fa-f]+$', hex_string):
        invalid_chars = set(re.findall(r'[^0-9A-Fa-f]', hex_string))
        raise ValueError(f"不正な16進文字が含まれています: {invalid_chars}")

    samples = []
    for i in range(0, len(hex_string), 2):
        byte_str = hex_string[i:i+2]
        value = int(byte_str, 16)
        
        # 符号付き8bit整数として解釈（0x80以上は負の値）
        if value >= 128:
            value = value - 256
        
        # -128〜127 を 0.0〜1.0 に正規化
        normalized = (value + 128) / 255.0
        samples.append(normalized)
    
    return samples


def parse_fds_waveform(fds_string: str) -> list[float]:
    """
    FDS波形フォーマット（スペース区切り10進数）から波形データをパース
    各値は0〜63の範囲、64サンプル

    例: "00 00 63 63 00 00 ..." -> [0.0, 0.0, 1.0, 1.0, ...]

    Raises:
        ValueError: 入力が空、数値でない、または範囲外の値がある場合
    """
    # 空白・改行・タブで分割
    parts = fds_string.strip().split()

    if not parts:
        raise ValueError("FDS波形データが空です")

    samples = []
    for i, part in enumerate(parts):
        try:
            value = int(part)
        except ValueError:
            raise ValueError(f"FDS波形データに不正な値があります（位置{i+1}）: '{part}'")

        if value < 0 or value > 63:
            raise ValueError(f"FDS波形の値は0-63の範囲で指定してください（位置{i+1}）: {value}")

        # 0〜63 を 0.0〜1.0 に正規化
        normalized = value / 63.0
        samples.append(normalized)

    return samples


def resample_waveform(waveform: list[float], target_length: int) -> list[float]:
    """
    波形を指定サンプル数にリサンプリング（線形補間）

    Raises:
        ValueError: 波形が空または target_length が正でない場合
    """
    if not waveform:
        raise ValueError("リサンプリング対象の波形が空です")
    if target_length <= 0:
        raise ValueError(f"リサンプリング後のサンプル数は正の整数で指定してください: {target_length}")

    if len(waveform) == target_length:
        return waveform
    
    result = []
    for i in range(target_length):
        # 元の波形上の位置（0.0〜1.0を1周期としてループ）
        pos = (i / target_length) * len(waveform)
        
        # 線形補間
        idx_low = int(pos) % len(waveform)
        idx_high = (idx_low + 1) % len(waveform)
        frac = pos - int(pos)
        
        value = waveform[idx_low] * (1 - frac) + waveform[idx_high] * frac
        result.append(value)
    
    return result


def adjust_volume(waveform: list[float], volume: float) -> list[float]:
    """
    波形の音量（振幅）を調整する

    Args:
        waveform: 0.0〜1.0の波形データ
        volume: 音量係数（1.0=等倍、0.5=半分、2.0=2倍）

    Returns:
        音量調整後の波形（0.0〜1.0にクリップ）

    Raises:
        ValueError: volumeが負の場合
    """
    if volume < 0:
        raise ValueError(f"音量は0以上で指定してください: {volume}")

    # 中心値（0.5）を基準にスケーリング
    center = 0.5
    result = []
    
    for sample in waveform:
        # 中心からの偏差を計算
        deviation = sample - center
        # 音量係数を適用
        new_deviation = deviation * volume
        # 中心に戻す
        new_sample = center + new_deviation
        # クリッピング
        new_sample = max(0.0, min(1.0, new_sample))
        result.append(new_sample)
    
    return result


def mix_sub_octave(waveform: list[float], num_samples_per_cycle: int,
                   wave_type: str, amount: float,
                   custom_waveform: list[float] = None) -> list[float]:
    """
    1オクターブ下のサブハーモニックを波形に混合する

    1オクターブ下は周波数が1/2（周期が2倍）の波形。
    サブオクターブの偏差（0.5からの距離）をamount倍してベース波形に加算する。
    ループの整合性を保つには num_samples_per_cycle * 周期数 が偶数である必要がある。

    Args:
        waveform: 基音の波形（複数周期分、0.0〜1.0）
        num_samples_per_cycle: 基音の1周期サンプル数
        wave_type: 波形タイプ（基音と同じ波形を使用）
        amount: 混合量（0.0=なし、1.0=基音と同音量）
        custom_waveform: カスタム波形（指定時はwave_typeの代わりに使用）

    Returns:
        混合後の波形（0.0〜1.0にクリップ）
    """
    if amount <= 0:
        return waveform

    total_samples = len(waveform)
    sub_period = num_samples_per_cycle * 2  # 1オクターブ下 = 2倍の周期

    # サブオクターブの1周期波形を生成
    if custom_waveform:
        sub_1cycle = resample_waveform(custom_waveform, sub_period)
    else:
        sub_1cycle = generate_waveform(wave_type, sub_period)

    # サブオクターブ波形をtotal_samples分展開して加算
    result = []
    for i in range(total_samples):
        base = waveform[i]
        sub = sub_1cycle[i % sub_period]
        sub_dev = sub - 0.5
        mixed = base + sub_dev * amount
        result.append(max(0.0, min(1.0, mixed)))

    return result


def visualize_waveform(waveform: list[float], width: int = 64, height: int = 16) -> str:
    """
    波形をASCIIアートで可視化
    """
    # 波形を指定幅にリサンプリング
    if len(waveform) != width:
        display_wave = resample_waveform(waveform, width)
    else:
        display_wave = waveform
    
    lines = []
    for row in range(height):
        threshold = 1.0 - (row / (height - 1))
        line = ""
        for val in display_wave:
            if abs(val - threshold) < (0.5 / height):
                line += "█"
            elif val >= threshold:
                line += "│"
            else:
                line += " "
        lines.append(f"│{line}│")
    
    border = "─" * width
    return f"┌{border}┐\n" + "\n".join(lines) + f"\n└{border}┘"


def generate_waveform(wave_type: str, num_samples: int) -> list[float]:
    """
    指定された波形を生成（0.0〜1.0の範囲）
    """
    samples = []
    for i in range(num_samples):
        t = i / num_samples  # 0.0 〜 1.0（1周期）
        
        if wave_type == "saw":
            # ノコギリ波
            value = t
        elif wave_type == "triangle":
            # 三角波
            value = 2 * t if t < 0.5 else 2 * (1 - t)
        elif wave_type == "sine":
            # サイン波
            value = (math.sin(2 * math.pi * t) + 1) / 2
        elif wave_type == "square":
            # 矩形波（デューティ50%）
            value = 1.0 if t < 0.5 else 0.0
        elif wave_type == "pulse25":
            # パルス波（デューティ25%）
            value = 1.0 if t < 0.25 else 0.0
        elif wave_type == "pulse12":
            # パルス波（デューティ12.5%）
            value = 1.0 if t < 0.125 else 0.0
        else:
            raise ValueError(f"Unknown wave type: {wave_type}")
        
        samples.append(value)
    
    return samples


def get_valid_dpcm_sample_counts(max_bytes: int = 4081) -> list[int]:
    """
    ファミコンdPCMで有効なサンプル数のリストを返す
    サンプル長は (1 + 16*n) バイト = (8 + 128*n) サンプル
    """
    counts = []
    n = 0
    while True:
        byte_count = 1 + 16 * n
        if byte_count > max_bytes:
            break
        sample_count = byte_count * 8
        counts.append(sample_count)
        n += 1
    return counts


def find_nearest_valid_sample_count(target: int) -> tuple[int, int]:
    """
    目標サンプル数以上で最小の有効なdPCMサンプル数を見つける
    
    Returns:
        (sample_count, byte_count)
    """
    valid_counts = get_valid_dpcm_sample_counts()
    
    for count in valid_counts:
        if count >= target:
            byte_count = count // 8
            return count, byte_count
    
    # 見つからない場合は最大値を返す
    count = valid_counts[-1]
    return count, count // 8


def encode_dpcm(samples: list[float], start_value: int = 64, loop_match: bool = False, auto_start: bool = False, warmup_samples: int = 0) -> tuple[bytes, int]:
    """
    サンプル列をdPCMにエンコード

    dPCMの仕様:
    - 現在値は0〜127の範囲
    - 各ビットは+2（ビット1）または-2（ビット0）の変化を表す
    - LSBファースト
    - サンプル長は (1 + 16*n) バイト = (8 + 128*n) サンプル

    Args:
        samples: 0.0〜1.0の波形サンプル列
        start_value: 開始時のDC値（0〜127）
        loop_match: Trueの場合、終端値が開始値に戻るよう調整
        auto_start: Trueの場合、波形の最初の値を開始値として使用
        warmup_samples: ウォームアップ用サンプル数（先頭のこの区間を助走として繰り返し
                        シミュレートし、状態が定常化した値を開始値に採用。区間自体は出力しない）

    Returns:
        (dpcm_data, actual_start_value): エンコードされたデータと実際に使用した開始値

    Raises:
        ValueError: start_valueが0-127の範囲外の場合
    """
    if not auto_start and (start_value < 0 or start_value > 127):
        raise ValueError(f"開始値は0-127の範囲で指定してください: {start_value}")

    # 0.0-1.0 を偶数値（0, 2, 4, ..., 126）にスケーリング
    # dPCMは±2ステップで変化するため、偶数のみに統一することでパリティ不一致を防ぐ
    target_values = [round(s * 63) * 2 for s in samples]

    # ウォームアップ処理: 最初のwarmup_samplesを助走として使い、定常化した状態を開始値にする
    if warmup_samples > 0 and len(target_values) > warmup_samples:
        warmup_targets = target_values[:warmup_samples]
        current = start_value
        # auto_startの場合、ウォームアップ開始値も波形に合わせる
        if auto_start and warmup_targets:
            first_target = warmup_targets[0]
            current = min(126, first_target + 2)
        # ウォームアップ区間を繰り返しシミュレートし、区間境界での状態が
        # 定常状態（固定点または周期解）に収束するまで回す。
        # 状態は0〜127の128通りしかないため、必ず有限回で収束する
        seen_states = set()
        while current not in seen_states:
            seen_states.add(current)
            for target in warmup_targets:
                if target > current:
                    current = min(127, current + 2)
                else:
                    current = max(0, current - 2)
        # 定常状態に達した値を開始値として使用
        start_value = current
        # ウォームアップ部分を除去
        target_values = target_values[warmup_samples:]
    elif auto_start and target_values:
        # ウォームアップなしの場合の従来の自動開始値設定
        # デコード時に最初のサンプルがfirst_targetになるよう+2補正
        # dPCMでは最初のサンプルが start_value ± 2 になるため
        first_target = target_values[0]
        start_value = min(126, first_target + 2)  # 上限126（偶数維持）

    current = start_value
    bits = []
    
    for target in target_values:
        if target > current:
            bits.append(1)
            current = min(127, current + 2)
        else:
            bits.append(0)
            current = max(0, current - 2)
    
    # ループ用：終端を開始値に戻す
    if loop_match:
        # パリティチェック：currentとstart_valueの偶奇が異なる場合、到達不可能
        # その場合は最も近い到達可能な値を目標にする
        target_end = start_value
        if (current % 2) != (start_value % 2):
            if current < start_value:
                target_end = max(0, start_value - 1)
            else:
                target_end = min(127, start_value + 1)

        # 無限ループ防止（理論上最大64ステップで到達可能）
        max_iterations = 128
        iterations = 0
        while current != target_end and iterations < max_iterations:
            if current < target_end:
                bits.append(1)
                current = min(127, current + 2)
            else:
                bits.append(0)
                current = max(0, current - 2)
            iterations += 1
    
    # ファミコンdPCMは (8 + 128*n) サンプル単位
    # つまり (1 + 16*n) バイト単位
    current_samples = len(bits)
    target_samples, _ = find_nearest_valid_sample_count(current_samples)
    
    # パディングが必要な場合
    while len(bits) < target_samples:
        # 最後の値を維持するようなビットを追加（交互に）
        bits.append(1 if bits[-1] == 0 else 0)
    
    # 8ビットごとにバイトにまとめる（LSBファースト）
    output = bytearray()
    for i in range(0, len(bits), 8):
        byte = 0
        for j in range(8):
            if bits[i + j]:
                byte |= (1 << j)
        output.append(byte)
    
    return bytes(output), start_value


def decode_dpcm(dpcm_data: bytes, start_value: int = 64) -> list[int]:
    """
    dPCMデータを7bit PCMサンプル列にデコード

    Args:
        dpcm_data: dPCMエンコードされたバイト列
        start_value: 開始時のDC値（0〜127）

    Returns:
        0〜127の範囲のPCMサンプル列
    """
    current = start_value
    samples = []

    for byte in dpcm_data:
        for bit in range(8):
            if byte & (1 << bit):
                current = min(127, current + 2)
            else:
                current = max(0, current - 2)
            samples.append(current)

    return samples


def samples_to_wav(samples: list[int], sample_rate: int, output_path: str, loops: int = 1) -> None:
    """
    サンプル列をWAVファイルとして出力（8bit/モノラル）

    Args:
        samples: 0〜127の範囲のPCMサンプル列
        sample_rate: サンプルレート（Hz）
        output_path: 出力ファイルパス
        loops: ループ回数
    """
    # ループ分拡張
    all_samples = samples * loops

    # 0-127を0-255（8bit unsigned）にスケーリング
    wav_samples = bytes([min(255, s * 2) for s in all_samples])

    with wave.open(output_path, 'wb') as wf:
        wf.setnchannels(1)
        wf.setsampwidth(1)  # 8bit
        wf.setframerate(sample_rate)
        wf.writeframes(wav_samples)


def generate_preview(dpcm_data: bytes, sample_rate: float, output_path: str,
                    loops: int = 1, start_value: int = 64) -> None:
    """
    dPCMデータからWAVプレビューを生成

    Args:
        dpcm_data: dPCMエンコードされたバイト列
        sample_rate: サンプルレート（Hz）
        output_path: 出力WAVファイルパス
        loops: ループ回数
        start_value: デコード開始値
    """
    samples = decode_dpcm(dpcm_data, start_value)
    samples_to_wav(samples, int(round(sample_rate)), output_path, loops)


def generate_raw_preview(waveform: list[float], sample_rate: float, output_path: str,
                         loops: int = 1, bit_depth: int = 16) -> None:
    """
    エンコード前の浮動小数点波形をWAVファイルとして出力

    Args:
        waveform: 0.0〜1.0の波形サンプル列
        sample_rate: サンプルレート（Hz）
        output_path: 出力WAVファイルパス
        loops: ループ回数
        bit_depth: ビット深度（8または16、デフォルト16）

    Raises:
        ValueError: bit_depthが8または16でない場合
    """
    if bit_depth not in (8, 16):
        raise ValueError(f"ビット深度は8または16を指定してください: {bit_depth}")

    # ループ分拡張
    all_samples = waveform * loops

    with wave.open(output_path, 'wb') as wf:
        wf.setnchannels(1)
        wf.setframerate(int(round(sample_rate)))

        if bit_depth == 16:
            wf.setsampwidth(2)
            # 0.0〜1.0 を -32768〜32767 にスケーリング
            wav_data = b''.join(
                struct.pack('<h', max(-32768, min(32767, int((s - 0.5) * 65535))))
                for s in all_samples
            )
        else:  # 8bit
            wf.setsampwidth(1)
            # 0.0〜1.0 を 0〜255 にスケーリング
            wav_data = bytes(max(0, min(255, int(s * 255))) for s in all_samples)

        wf.writeframes(wav_data)


def calculate_samples_for_note(note_freq: float, sample_rate: float) -> int:
    """
    指定周波数の音を出すために必要なサンプル数を計算
    """
    return round(sample_rate / note_freq)


def freq_from_note(note_name: str) -> float:
    """
    音名から周波数を取得（A4 = 440Hz基準）
    例: "C4", "A4", "G#3"

    Raises:
        ValueError: 無効な音名形式の場合
    """
    note_names = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']

    # 音名形式の基本チェック
    if not note_name or len(note_name) < 2:
        raise ValueError(f"無効な音名形式です: '{note_name}' (例: C4, A#3, Bb2)")

    try:
        # 音名をパース
        if '#' in note_name or 'b' in note_name:
            if '#' in note_name:
                base_note = note_name[:2]
                octave = int(note_name[2:])
            else:  # flat
                base_idx = note_names.index(note_name[0].upper())
                base_note = note_names[base_idx - 1]
                octave = int(note_name[2:])
        else:
            base_note = note_name[0].upper()
            octave = int(note_name[1:])

        semitone = note_names.index(base_note)
    except (ValueError, IndexError) as e:
        raise ValueError(f"無効な音名形式です: '{note_name}' (例: C4, A#3, Bb2)")

    # A4からの半音数
    semitones_from_a4 = (octave - 4) * 12 + (semitone - 9)

    return 440.0 * (2 ** (semitones_from_a4 / 12))


def note_to_semitone(note_name: str) -> int:
    """
    ノート名をC0基準の半音番号に変換
    例: "C0" -> 0, "C4" -> 48, "A4" -> 57
    """
    note_names = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']

    if '#' in note_name:
        base_note = note_name[:2]
        octave = int(note_name[2:])
    elif 'b' in note_name:
        base_idx = note_names.index(note_name[0])
        base_note = note_names[base_idx - 1]
        octave = int(note_name[2:])
    else:
        base_note = note_name[0]
        octave = int(note_name[1:])

    semitone = note_names.index(base_note)
    return octave * 12 + semitone


def semitone_to_note(semitone: int) -> str:
    """
    半音番号をノート名に変換
    例: 0 -> "C0", 48 -> "C4", 57 -> "A4"
    """
    note_names = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
    octave = semitone // 12
    note_idx = semitone % 12
    return f"{note_names[note_idx]}{octave}"


def generate_note_range(start_note: str, end_note: str) -> list[str]:
    """
    指定範囲のノートリストを生成
    例: ("C2", "E2") -> ["C2", "C#2", "D2", "D#2", "E2"]
    """
    start_semitone = note_to_semitone(start_note)
    end_semitone = note_to_semitone(end_note)
    return [semitone_to_note(s) for s in range(start_semitone, end_semitone + 1)]


def find_best_sample_rate(target_freq: float, min_samples: int = 32) -> tuple[float, int, int]:
    """
    目標周波数に対して最適なサンプルレートを見つける
    
    Returns:
        (sample_rate, rate_index, num_samples)
    """
    best_rate = None
    best_index = 0
    best_samples = 0
    best_error = float('inf')
    
    for idx, rate in enumerate(SAMPLE_RATES_NTSC):
        samples = round(rate / target_freq)
        if samples < min_samples:
            continue
        
        actual_freq = rate / samples
        error = abs(actual_freq - target_freq) / target_freq
        
        if error < best_error:
            best_error = error
            best_rate = rate
            best_index = idx
            best_samples = samples
    
    return best_rate, best_index, best_samples


def find_best_fit_params(target_freq: float, min_cycles: int = 1, max_cycles: int = 64, max_cents_error: float = 15.0, prefer_quality: bool = False, min_rate_index: int = 0, loop_match_reserve: int = 0, require_even_cycles: bool = False) -> tuple[float, int, int, int, int]:
    """
    目標周波数に対して、有効なdPCMサンプル数(8+128n)にぴったり収まる
    最適なサンプルレート・周期数の組み合わせを見つける

    min_cycles以上の周期数で、誤差が小さく、条件に合うものを探す

    Args:
        target_freq: 目標周波数
        min_cycles: 最小周期数
        max_cycles: 最大周期数
        max_cents_error: 許容する最大誤差（セント）
        prefer_quality: Trueの場合、サイズよりサンプルレートを優先（高音質）
        min_rate_index: サンプルレートの下限インデックス（0-15）
        loop_match_reserve: ループマッチ用に確保するサンプル数（0-64）
        require_even_cycles: Trueの場合、周期数が偶数の候補のみを対象とする
                             （サブオクターブ混合時のループ境界整合のため）

    Returns:
        (sample_rate, rate_index, samples_per_cycle, num_cycles, wave_samples)
        wave_samples: 波形用サンプル数（有効サンプル数 - loop_match_reserve）
    """
    valid_counts = get_valid_dpcm_sample_counts()

    candidates = []

    for rate_idx, rate in enumerate(SAMPLE_RATES_NTSC):
        # 指定された下限レート未満はスキップ
        if rate_idx < min_rate_index:
            continue

        # このレートでの理想的な1周期サンプル数
        ideal_samples_per_cycle = rate / target_freq

        if ideal_samples_per_cycle < 8:  # 最小サンプル数未満
            continue
        
        for num_cycles in range(min_cycles, max_cycles + 1):
            # サブオクターブ混合時は偶数周期のみ（ループ境界整合のため）
            if require_even_cycles and num_cycles % 2 != 0:
                continue

            # 理想的な合計サンプル数
            ideal_total = ideal_samples_per_cycle * num_cycles
            
            # この周期数で割り切れる有効サンプル数を探す
            for valid_total in valid_counts:
                # ループマッチ余地を引いた値が周期数で割り切れるかチェック
                wave_samples = valid_total - loop_match_reserve
                if wave_samples <= 0:
                    continue
                if wave_samples % num_cycles != 0:
                    continue

                actual_samples_per_cycle = wave_samples // num_cycles
                
                # 1周期あたりのサンプル数が少なすぎる場合はスキップ
                if actual_samples_per_cycle < 16:
                    continue
                
                actual_freq = rate / actual_samples_per_cycle
                cents_error = 1200 * math.log2(actual_freq / target_freq)
                
                candidates.append({
                    'rate': rate,
                    'rate_idx': rate_idx,
                    'samples_per_cycle': actual_samples_per_cycle,
                    'num_cycles': num_cycles,
                    'total_samples': valid_total,
                    'wave_samples': wave_samples,
                    'cents_error': cents_error,
                    'abs_cents_error': abs(cents_error),
                })
    
    if not candidates:
        return None
    
    # 許容誤差内の候補を探す
    good_candidates = [c for c in candidates if c['abs_cents_error'] <= max_cents_error]
    
    if good_candidates:
        if prefer_quality:
            # 高品質優先：サンプルレートが高く、1周期サンプル数が多いものを選ぶ
            best = max(good_candidates, key=lambda c: (c['rate'], c['samples_per_cycle']))
        else:
            # サイズ優先：最小サイズを選ぶ
            best = min(good_candidates, key=lambda c: (c['total_samples'], c['abs_cents_error']))
    else:
        # 許容誤差内がなければ、誤差最小を選ぶ
        best = min(candidates, key=lambda c: c['abs_cents_error'])
    
    return (best['rate'], best['rate_idx'], best['samples_per_cycle'],
            best['num_cycles'], best['wave_samples'])


def main():
    parser = argparse.ArgumentParser(description='NES dPCM波形ジェネレーター')
    parser.add_argument('--wave', '-w',
                        choices=['saw', 'triangle', 'sine', 'square', 'pulse25', 'pulse12'],
                        default='saw',
                        help='波形の種類')
    parser.add_argument('--hex', '-x',
                        type=str,
                        help='16進数文字列で波形を直接指定（例: "010203..."）')
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
    parser.add_argument('--note', '-n',
                        type=validate_note_name,
                        default='C4',
                        help='音名（例: C4, A4, G#3）')
    parser.add_argument('--freq', '-f',
                        type=validate_positive_float,
                        help='周波数を直接指定（--noteより優先）')
    parser.add_argument('--rate-index', '-r',
                        type=validate_rate_index,
                        help='サンプルレートのインデックス（0-15）を直接指定')
    parser.add_argument('--output', '-o',
                        default='output.dmc',
                        help='出力ファイル名')
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
                        help='サンプル数をdPCM有効長(8+128n)にぴったり合わせる（周波数微調整）')
    parser.add_argument('--quality', '-q',
                        action='store_true',
                        help='fitモード時、サイズより高サンプルレートを優先（高音質）')
    parser.add_argument('--min-rate-index',
                        type=validate_rate_index,
                        help='fitモード時、サンプルレートの下限インデックス（0-15）を指定')
    parser.add_argument('--info', '-i',
                        action='store_true',
                        help='サンプルレート一覧を表示')
    parser.add_argument('--show-wave',
                        action='store_true',
                        help='波形をASCIIアートで表示')
    parser.add_argument('--dpcm-index',
                        type=validate_non_negative_int,
                        default=0,
                        help='ppmck定義の番号（デフォルト: 0）')
    parser.add_argument('--dpcm-path',
                        type=str,
                        default='',
                        help='ppmck定義でのdmcファイルパス（例: "D:\\myFolder\\"）')
    parser.add_argument('--preview', '-p',
                        action='store_true',
                        help='プレビューWAVを生成（出力先: {output}.wav）')
    parser.add_argument('--preview-loops',
                        type=validate_positive_int,
                        default=4,
                        help='プレビューのループ回数（デフォルト: 4）')
    parser.add_argument('--raw-preview',
                        action='store_true',
                        help='エンコード前のWAVプレビューを生成（出力先: {output}_raw.wav）')
    parser.add_argument('--raw-preview-loops',
                        type=validate_positive_int,
                        help='エンコード前プレビューのループ回数（デフォルト: --preview-loopsと同値）')
    parser.add_argument('--lowpass',
                        type=validate_positive_float,
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
    
    if args.info:
        print("NTSC dPCM サンプルレート一覧:")
        print("-" * 40)
        for i, rate in enumerate(SAMPLE_RATES_NTSC):
            print(f"  ${i:X} ({i:2d}): {rate:8.2f} Hz")
        return
    
    # カスタム波形が指定されているかチェック
    custom_waveform = None
    wave_type_display = args.wave
    wav_sample_rate = None

    try:
        if args.hex:
            custom_waveform = parse_hex_waveform(args.hex)
            wave_type_display = f"カスタム ({len(custom_waveform)}サンプル)"
        elif args.hex_file:
            try:
                with open(args.hex_file, 'r') as f:
                    hex_data = f.read()
            except IOError as e:
                print(f"エラー: ファイルの読み込みに失敗しました: '{args.hex_file}' ({e})", file=sys.stderr)
                sys.exit(1)
            custom_waveform = parse_hex_waveform(hex_data)
            wave_type_display = f"カスタム ({len(custom_waveform)}サンプル, {args.hex_file})"
        elif args.fds:
            custom_waveform = parse_fds_waveform(args.fds)
            wave_type_display = f"FDS ({len(custom_waveform)}サンプル)"
        elif args.fds_file:
            try:
                with open(args.fds_file, 'r') as f:
                    fds_data = f.read()
            except IOError as e:
                print(f"エラー: ファイルの読み込みに失敗しました: '{args.fds_file}' ({e})", file=sys.stderr)
                sys.exit(1)
            custom_waveform = parse_fds_waveform(fds_data)
            wave_type_display = f"FDS ({len(custom_waveform)}サンプル, {args.fds_file})"
        elif args.wav:
            custom_waveform, wav_sample_rate = load_wav_waveform(args.wav)
            wave_type_display = f"WAV ({len(custom_waveform)}サンプル, {wav_sample_rate}Hz, {args.wav})"

            # WAV入力時のローパスフィルタ処理
            if not args.no_auto_lowpass:
                if args.lowpass:
                    # 明示的にカットオフ周波数が指定された場合
                    lowpass_cutoff = args.lowpass
                else:
                    # 自動計算: 出力サンプルレートの0.4倍（後で確定後に適用）
                    lowpass_cutoff = None  # 後で計算

                if lowpass_cutoff is not None:
                    custom_waveform = apply_lowpass_filter(
                        custom_waveform, wav_sample_rate,
                        lowpass_cutoff, args.lowpass_order
                    )
                    wave_type_display += f" [LP:{lowpass_cutoff:.0f}Hz]"
    except ValueError as e:
        print(f"エラー: {e}", file=sys.stderr)
        sys.exit(1)
    except FileNotFoundError as e:
        print(f"エラー: {e}", file=sys.stderr)
        sys.exit(1)
    
    # 目標周波数を決定
    if args.freq:
        target_freq = args.freq
        note_name = f"{target_freq:.2f}Hz"
    else:
        note_name = args.note
        target_freq = freq_from_note(note_name)
    
    # サンプルレートを決定
    fit_mode = args.fit
    num_cycles = args.cycles
    
    if fit_mode:
        # fitモード: 有効なdPCMサンプル数にぴったり合わせる
        # loop_matchが有効な場合、余地を確保
        loop_reserve = 64 if args.loop_match else 0
        # サブオクターブ混合時はループ境界整合のため偶数周期を要求
        require_even = args.sub_octave > 0
        result = find_best_fit_params(target_freq, min_cycles=args.cycles,
                                       max_cycles=max(args.cycles * 4, 64),
                                       prefer_quality=args.quality,
                                       min_rate_index=args.min_rate_index or 0,
                                       loop_match_reserve=loop_reserve,
                                       require_even_cycles=require_even)
        if result is None and require_even:
            # 偶数周期の解が見つからない場合は制約を外して再探索
            print("警告: 偶数周期の解が見つからず、サブオクターブがループ境界でずれる可能性があります")
            result = find_best_fit_params(target_freq, min_cycles=args.cycles,
                                           max_cycles=max(args.cycles * 4, 64),
                                           prefer_quality=args.quality,
                                           min_rate_index=args.min_rate_index or 0,
                                           loop_match_reserve=loop_reserve)
        if result is None:
            print("エラー: 適切なパラメータが見つかりませんでした")
            return
        sample_rate, rate_index, num_samples, num_cycles, total_samples = result
    elif args.rate_index is not None:
        sample_rate = SAMPLE_RATES_NTSC[args.rate_index]
        num_samples = round(sample_rate / target_freq)
        rate_index = args.rate_index
        # サブオクターブ混合時はループ境界整合のため偶数周期に揃える
        if args.sub_octave > 0 and num_cycles % 2 != 0:
            num_cycles += 1
            print(f"サブオクターブ整合のため周期数を偶数に調整: {num_cycles}")
        total_samples = num_samples * num_cycles
    else:
        sample_rate, rate_index, num_samples = find_best_sample_rate(target_freq)
        # サブオクターブ混合時はループ境界整合のため偶数周期に揃える
        if args.sub_octave > 0 and num_cycles % 2 != 0:
            num_cycles += 1
            print(f"サブオクターブ整合のため周期数を偶数に調整: {num_cycles}")
        total_samples = num_samples * num_cycles
    
    if sample_rate is None:
        print("エラー: 適切なサンプルレートが見つかりませんでした")
        return
    
    actual_freq = sample_rate / num_samples
    cents_error = 1200 * math.log2(actual_freq / target_freq)
    
    # 有効なdPCMサイズを取得
    final_samples, final_bytes = find_nearest_valid_sample_count(total_samples)

    # WAV入力時の自動ローパスフィルタ（サンプルレート確定後に適用）
    lowpass_applied = None
    if args.wav and wav_sample_rate and not args.no_auto_lowpass and not args.lowpass:
        # 自動計算: 出力サンプルレートの0.4倍
        auto_cutoff = sample_rate * 0.4
        custom_waveform = apply_lowpass_filter(
            custom_waveform, wav_sample_rate,
            auto_cutoff, args.lowpass_order
        )
        lowpass_applied = auto_cutoff
        wave_type_display += f" [LP:{auto_cutoff:.0f}Hz(auto)]"

    print(f"=== dPCM生成情報 ===")
    print(f"波形タイプ    : {wave_type_display}")
    print(f"目標音程      : {note_name}")
    print(f"目標周波数    : {target_freq:.2f} Hz")
    print(f"サンプルレート: ${rate_index:X} ({sample_rate:.2f} Hz)")
    print(f"1周期サンプル : {num_samples}")
    if num_cycles > 1 or fit_mode:
        print(f"周期数        : {num_cycles}")
        print(f"合計サンプル  : {total_samples}")
    print(f"実際の周波数  : {actual_freq:.2f} Hz")
    print(f"誤差          : {cents_error:+.1f} セント")
    if fit_mode:
        if args.min_rate_index:
            quality_str = f"レート下限${args.min_rate_index:X}"
        elif args.quality:
            quality_str = "高品質優先"
        else:
            quality_str = "サイズ優先"
        print(f"fitモード     : 有効 ({quality_str})")
    elif total_samples != final_samples:
        print(f"パディング    : {total_samples} → {final_samples} サンプル")
    print(f"ファイルサイズ: {final_bytes} バイト")
    if args.sub_octave > 0:
        print(f"サブオクターブ  : {args.sub_octave:.2f}（1オクターブ下を混合）")
    if args.auto_start:
        print(f"開始値自動設定: 有効")
    if args.loop_match:
        print(f"ループマッチ  : 有効")
    if args.warmup:
        print(f"ウォームアップ: 有効（開始値を定常状態へ収束）")
    if args.wav and not args.no_auto_lowpass:
        if args.lowpass:
            print(f"ローパスフィルタ: {args.lowpass:.0f}Hz (次数: {args.lowpass_order})")
        elif lowpass_applied:
            print(f"ローパスフィルタ: {lowpass_applied:.0f}Hz (自動, 次数: {args.lowpass_order})")
    print()

    # 波形生成（1周期分）
    if custom_waveform:
        # カスタム波形をリサンプリング
        waveform_1cycle = resample_waveform(custom_waveform, num_samples)
        print(f"元波形 {len(custom_waveform)}サンプル → {num_samples}サンプルにリサンプリング")
        
        # カスタム波形の場合、元波形も表示オプションで見せる
        if args.show_wave:
            print()
            print("=== 入力波形 ===")
            print(visualize_waveform(custom_waveform))
    else:
        waveform_1cycle = generate_waveform(args.wave, num_samples)
    
    # 音量調整
    if args.volume != 1.0:
        waveform_1cycle = adjust_volume(waveform_1cycle, args.volume)
        if args.volume > 1.0:
            print(f"音量調整: {args.volume:.0%}（クリッピングの可能性あり）")
        else:
            print(f"音量調整: {args.volume:.0%}")
    
    # 複数周期分に拡張（warmup有効時は助走用に波形の1周期分を先頭に追加。
    # サブオクターブ混合時は波形の周期が2倍になるため2周期分）
    warmup_cycles = (2 if args.sub_octave > 0 else 1) if args.warmup else 0
    waveform = waveform_1cycle * (num_cycles + warmup_cycles)

    # サブオクターブ混合（周期数は偶数に調整済み。万一奇数なら警告）
    if args.sub_octave > 0:
        if num_cycles % 2 != 0:
            print(f"警告: 周期数が奇数（{num_cycles}）のため、サブオクターブがループ境界でずれます")
        waveform = mix_sub_octave(
            waveform, num_samples,
            args.wave, args.sub_octave,
            custom_waveform=custom_waveform if custom_waveform else None
        )

    if args.show_wave:
        print()
        print("=== 出力波形 ===")
        print(visualize_waveform(waveform))

    # dPCMエンコード
    warmup_count = num_samples * warmup_cycles
    dpcm_data, actual_start = encode_dpcm(waveform, loop_match=args.loop_match, auto_start=args.auto_start, warmup_samples=warmup_count)

    # ファイル出力
    try:
        with open(args.output, 'wb') as f:
            f.write(dpcm_data)
    except PermissionError:
        print(f"エラー: ファイルへの書き込み権限がありません: '{args.output}'", file=sys.stderr)
        sys.exit(1)
    except IOError as e:
        print(f"エラー: ファイルの書き込みに失敗しました: '{args.output}' ({e})", file=sys.stderr)
        sys.exit(1)

    print(f"出力完了: {args.output}")

    # プレビュー生成
    if args.preview:
        # 開始値はエンコード時に使用した値をそのまま使う
        preview_start = actual_start

        # 出力パスから.wavパスを生成
        base_path = os.path.splitext(args.output)[0]
        preview_path = f"{base_path}.wav"

        try:
            generate_preview(dpcm_data, sample_rate, preview_path,
                            loops=args.preview_loops, start_value=preview_start)
            print(f"プレビュー: {preview_path} ({args.preview_loops}ループ)")
        except PermissionError:
            print(f"エラー: プレビューファイルへの書き込み権限がありません: '{preview_path}'", file=sys.stderr)
        except IOError as e:
            print(f"エラー: プレビューファイルの書き込みに失敗しました: '{preview_path}' ({e})", file=sys.stderr)

    # エンコード前プレビュー生成
    if args.raw_preview:
        base_path = os.path.splitext(args.output)[0]
        raw_preview_path = f"{base_path}_raw.wav"
        raw_loops = args.raw_preview_loops if args.raw_preview_loops else args.preview_loops

        try:
            generate_raw_preview(waveform, sample_rate, raw_preview_path, loops=raw_loops)
            print(f"エンコード前プレビュー: {raw_preview_path} ({raw_loops}ループ)")
        except PermissionError:
            print(f"エラー: エンコード前プレビューファイルへの書き込み権限がありません: '{raw_preview_path}'", file=sys.stderr)
        except IOError as e:
            print(f"エラー: エンコード前プレビューファイルの書き込みに失敗しました: '{raw_preview_path}' ({e})", file=sys.stderr)

    print()
    print("=== ppmckでの使用例 ===")
    filepath = f"{args.dpcm_path}{args.output}"
    print(f'@DPCM{args.dpcm_index} = {{ "{filepath}", {rate_index}, 0, 0, 1 }}')
    print()
    print("; MMLでループ再生する場合（Eチャンネルは音名ではなくnコマンドで指定）:")
    print(f"E n{args.dpcm_index}   ; @DPCM{args.dpcm_index}をトーンとして鳴らす")


if __name__ == "__main__":
    main()
