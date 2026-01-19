#!/usr/bin/env python3
"""
複数音階のdPCMファイルを一括生成
ppmckで使えるサンプル定義も出力します
"""

import os
from dpcm_generator import (
    generate_waveform, encode_dpcm, resample_waveform, adjust_volume,
    freq_from_note, find_best_sample_rate, find_best_fit_params,
    parse_hex_waveform, parse_fds_waveform, load_wav_waveform, 
    get_valid_dpcm_sample_counts, find_nearest_valid_sample_count,
    SAMPLE_RATES_NTSC
)

# 生成する音階の範囲
NOTES = [
    # オクターブ2
    "C2", "C#2", "D2", "D#2", "E2", "F2", "F#2", "G2", "G#2", "A2", "A#2", "B2",
    # オクターブ3
    "C3", "C#3", "D3", "D#3", "E3", "F3", "F#3", "G3", "G#3", "A3", "A#3", "B3",
    # オクターブ4
    "C4", "C#4", "D4", "D#4", "E4", "F4",
]

def generate_note_set(wave_type: str, output_dir: str, prefix: str = "", custom_waveform: list[float] = None, cycles: int = 1, volume: float = 1.0, auto_start: bool = False, loop_match: bool = False, fit: bool = False, prefer_quality: bool = False):
    """
    指定波形で全音階を生成
    custom_waveform が指定されている場合はそれを使用
    """
    os.makedirs(output_dir, exist_ok=True)
    
    results = []
    
    for note in NOTES:
        target_freq = freq_from_note(note)
        
        if fit:
            # fitモード: 有効なdPCMサンプル数にぴったり合わせる
            result = find_best_fit_params(target_freq, min_cycles=cycles, 
                                          max_cycles=max(cycles * 4, 64),
                                          prefer_quality=prefer_quality)
            if result is None:
                print(f"  {note}: スキップ（適切なパラメータなし）")
                continue
            sample_rate, rate_index, num_samples, num_cycles, total_samples = result
        else:
            sample_rate, rate_index, num_samples = find_best_sample_rate(target_freq, min_samples=16)
            if sample_rate is None:
                print(f"  {note}: スキップ（適切なサンプルレートなし）")
                continue
            num_cycles = cycles
            total_samples = num_samples * num_cycles
        
        actual_freq = sample_rate / num_samples
        
        # ファイル名（#を_sに置換）
        safe_note = note.replace("#", "_s")
        filename = f"{prefix}{wave_type}_{safe_note}.dmc"
        filepath = os.path.join(output_dir, filename)
        
        # 波形生成（1周期分）
        if custom_waveform:
            waveform_1cycle = resample_waveform(custom_waveform, num_samples)
        else:
            waveform_1cycle = generate_waveform(wave_type, num_samples)
        
        # 音量調整
        if volume != 1.0:
            waveform_1cycle = adjust_volume(waveform_1cycle, volume)
        
        # 複数周期に拡張
        waveform = waveform_1cycle * num_cycles
        
        # エンコード
        dpcm_data = encode_dpcm(waveform, loop_match=loop_match, auto_start=auto_start)
        
        with open(filepath, 'wb') as f:
            f.write(dpcm_data)
        
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
    
    return results


def generate_ppmck_defines(results: list, wave_type: str) -> str:
    """
    ppmck用のサンプル定義を生成
    """
    lines = [f"; === {wave_type}波 dPCMサンプル定義 ==="]
    lines.append("; 注意: 各音階ごとにサンプルレートが異なります")
    lines.append("")
    
    for i, r in enumerate(results):
        note = r['note']
        lines.append(f'@DPCM{i} = {{ "{r["filename"]}", {r["rate_index"]} }}  ; {note}')
    
    lines.append("")
    lines.append("; 使用例（Eチャンネル）:")
    lines.append("; E @DPCM0 | c4  ; ループ再生でトーン")
    
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
                        type=str,
                        help='16進数波形定義が書かれたファイルを読み込む')
    parser.add_argument('--fds',
                        type=str,
                        help='FDS形式（スペース区切り10進数0-63）で波形を直接指定')
    parser.add_argument('--fds-file',
                        type=str,
                        help='FDS形式波形定義が書かれたファイルを読み込む')
    parser.add_argument('--wav',
                        type=str,
                        help='WAVファイルから1周期分の波形を読み込む')
    parser.add_argument('--name', '-n',
                        type=str,
                        help='カスタム波形使用時のファイル名プレフィックス（デフォルト: custom）')
    parser.add_argument('--cycles', '-c',
                        type=int,
                        default=1,
                        help='含める波形の周期数（デフォルト: 1）')
    parser.add_argument('--volume', '-v',
                        type=float,
                        default=1.0,
                        help='音量（振幅）係数（デフォルト: 1.0、0.5=半分、2.0=2倍）')
    parser.add_argument('--auto-start', '-a',
                        action='store_true',
                        help='開始値を波形の最初の値に自動設定（デフォルト: 64から開始）')
    parser.add_argument('--loop-match', '-l',
                        action='store_true',
                        help='ループ終端のDC値を開始値に合わせる')
    parser.add_argument('--fit',
                        action='store_true',
                        help='サンプル数をdPCM有効長(8+128n)にぴったり合わせる')
    parser.add_argument('--quality', '-q',
                        action='store_true',
                        help='fitモード時、サイズより高サンプルレートを優先（高音質）')
    parser.add_argument('--output-dir', '-o',
                        default='./dpcm_samples',
                        help='出力ディレクトリ')
    
    args = parser.parse_args()
    
    # カスタム波形の読み込み
    custom_waveform = None
    wave_type = args.wave
    
    if args.hex:
        custom_waveform = parse_hex_waveform(args.hex)
        wave_type = args.name if args.name else "custom"
        print(f"=== カスタム波形 dPCMサンプル一括生成 ===")
        print(f"元波形サンプル数: {len(custom_waveform)}")
    elif args.hex_file:
        with open(args.hex_file, 'r') as f:
            hex_data = f.read()
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
        with open(args.fds_file, 'r') as f:
            fds_data = f.read()
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
    
    print(f"出力先: {args.output_dir}")
    if args.cycles > 1:
        print(f"周期数: {args.cycles}")
    if args.volume != 1.0:
        if args.volume > 1.0:
            print(f"音量: {args.volume:.0%}（クリッピングの可能性あり）")
        else:
            print(f"音量: {args.volume:.0%}")
    if args.fit:
        quality_str = "高品質優先" if args.quality else "サイズ優先"
        print(f"fitモード: 有効 ({quality_str})")
    if args.auto_start:
        print(f"開始値自動設定: 有効")
    if args.loop_match:
        print(f"ループマッチ: 有効")
    print()
    
    results = generate_note_set(wave_type, args.output_dir, custom_waveform=custom_waveform,
                                 cycles=args.cycles, volume=args.volume, auto_start=args.auto_start,
                                 loop_match=args.loop_match, fit=args.fit, prefer_quality=args.quality)
    
    # ppmck定義ファイル出力
    defines = generate_ppmck_defines(results, wave_type)
    defines_path = os.path.join(args.output_dir, f"{wave_type}_defines.txt")
    with open(defines_path, 'w') as f:
        f.write(defines)
    
    print()
    print(f"生成完了: {len(results)}ファイル")
    print(f"ppmck定義: {defines_path}")
    print()
    
    # 合計サイズ
    total_size = sum(r['size'] for r in results)
    print(f"合計サイズ: {total_size} バイト ({total_size / 1024:.1f} KB)")


if __name__ == "__main__":
    main()
