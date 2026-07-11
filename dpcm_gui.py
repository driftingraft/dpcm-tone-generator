#!/usr/bin/env python3
"""
NES dPCM Generator - Web GUI
標準ライブラリのみで動作するローカルWebサーバーを立ち上げ、
ブラウザからdPCMサンプルの生成・プレビュー・ダウンロードを行えます。

使い方:
    python dpcm_gui.py                # http://127.0.0.1:8765 で起動しブラウザを開く
    python dpcm_gui.py --port 8000    # ポート指定
    python dpcm_gui.py --no-browser   # ブラウザを自動で開かない
"""

import argparse
import base64
import io
import json
import math
import os
import re
import shutil
import struct
import sys
import tempfile
import time
import wave
import webbrowser
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from dpcm_generator import (
    generate_waveform, encode_dpcm, decode_dpcm, resample_waveform,
    adjust_volume, mix_sub_octave, apply_lowpass_filter,
    parse_hex_waveform, parse_fds_waveform, load_wav_waveform,
    freq_from_note, find_best_sample_rate, find_best_fit_params,
    find_nearest_valid_sample_count, generate_note_range,
    SAMPLE_RATES_NTSC,
)
from dpcm_batch import NOTES as BATCH_NOTES, generate_note_set, generate_ppmck_defines
from dpcm_sunsoft import (
    find_minimum_sample_set, generate_sunsoft_samples,
    generate_sunsoft_defines, generate_scale_preview, calculate_rate_ratios,
)

HTML_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'dpcm_gui.html')

# ブラウザ自動起動のスキップ判定用マーカーファイル。
# GUIページが定期的に/api/pingを送り、サーバーがこのファイルのmtimeを更新する。
# 起動時にmtimeが新しければ「再起動直前までタブが開いていた」とみなし自動起動しない。
_CLIENT_MARKER_PATH = None  # main()でポート込みのパスを設定
_CLIENT_RECENT_WINDOW = 180  # 秒。ping間隔30秒＋バックグラウンドタブのタイマー抑制を考慮


def _touch_client_marker():
    if _CLIENT_MARKER_PATH is None:
        return
    try:
        with open(_CLIENT_MARKER_PATH, 'a'):
            pass
        os.utime(_CLIENT_MARKER_PATH, None)
    except OSError:
        pass


def _client_recently_active():
    try:
        return (time.time() - os.path.getmtime(_CLIENT_MARKER_PATH)) < _CLIENT_RECENT_WINDOW
    except (OSError, TypeError):
        return False


# =============================================================================
# ユーティリティ
# =============================================================================

def b64(data: bytes) -> str:
    return base64.b64encode(data).decode('ascii')


def _float(p: dict, key: str, default: float) -> float:
    value = p.get(key)
    if value is None or value == '':
        return default
    return float(value)


def _int(p: dict, key: str, default: int) -> int:
    value = p.get(key)
    if value is None or value == '':
        return default
    return int(value)


def _opt_int(p: dict, key: str):
    value = p.get(key)
    if value is None or value == '':
        return None
    return int(value)


def _opt_float(p: dict, key: str):
    value = p.get(key)
    if value is None or value == '':
        return None
    return float(value)


# =============================================================================
# GUI表示メッセージの多言語化（GUIレスポンス専用。CLI側の文言には影響しない）
#   - リクエストの 'lang'（'ja'|'en'、既定 'ja'）に応じて英/日を返す
#   - 自由文（警告・エラー・失敗理由・ppmckコメント等）が対象
# =============================================================================

def _get_lang(p: dict) -> str:
    return 'en' if (p.get('lang') == 'en') else 'ja'


_MSG = {
    'ja': {
        # wave_type_display（カスタムソース）
        'wt_hex': 'カスタムHEX ({n}サンプル)',
        'wt_fds': 'FDS ({n}サンプル)',
        'wt_wav': 'WAV ({n}サンプル, {rate}Hz)',
        # ローパス
        'lp_manual': '{cut}Hz (次数: {order})',
        'lp_auto': '{cut}Hz (自動, 次数: {order})',
        # fit品質
        'q_minrate': 'レート下限${idx}',
        'q_quality': '高品質優先',
        'q_size': 'サイズ優先',
        # 警告
        'w_suboct_no_even': '偶数周期の解が見つからず、サブオクターブがループ境界でずれる可能性があります',
        'w_suboct_adjust': 'サブオクターブ整合のため周期数を偶数に調整: {n}',
        'w_volume_clip': '音量{pct}: クリッピングの可能性があります',
        'w_odd_cycles': '周期数が奇数（{n}）のため、サブオクターブがループ境界でずれます',
        # エラー
        'e_wav_not_selected': 'WAVファイルが選択されていません',
        'e_wav_decode': 'WAVデータのデコードに失敗しました',
        'e_param_not_found': '適切なパラメータが見つかりませんでした',
        'e_freq_too_high': 'このサンプルレートでは音程が高すぎます',
        'e_rate_not_found': '適切なサンプルレートが見つかりませんでした',
        'e_start_end_order': '開始ノート（{start}）は終了ノート（{end}）以下にしてください',
        'e_no_files': '生成されたファイルがありません（{detail}）',
        'e_no_samples': '生成されたサンプルがありません（{detail}）',
        'e_bad_request': 'リクエスト形式が不正です',
        'e_server': 'サーバーエラー: {e}',
        # ppmckコメント（単一生成の例）
        'ppmck_loop': '; MMLでループ再生する場合（Eチャンネルは音名ではなくnコマンドで指定）:',
        'ppmck_tone': '; @DPCM{idx}をトーンとして鳴らす',
    },
    'en': {
        'wt_hex': 'Custom HEX ({n} samples)',
        'wt_fds': 'FDS ({n} samples)',
        'wt_wav': 'WAV ({n} samples, {rate}Hz)',
        'lp_manual': '{cut}Hz (order: {order})',
        'lp_auto': '{cut}Hz (auto, order: {order})',
        'q_minrate': 'Min rate ${idx}',
        'q_quality': 'Prefer quality',
        'q_size': 'Prefer size',
        'w_suboct_no_even': 'No even-cycle solution found; the sub-octave may drift at the loop boundary',
        'w_suboct_adjust': 'Adjusted cycles to an even number for sub-octave alignment: {n}',
        'w_volume_clip': 'Volume {pct}: clipping may occur',
        'w_odd_cycles': 'Odd cycle count ({n}); the sub-octave drifts at the loop boundary',
        'e_wav_not_selected': 'No WAV file selected',
        'e_wav_decode': 'Failed to decode WAV data',
        'e_param_not_found': 'No suitable parameters were found',
        'e_freq_too_high': 'The pitch is too high for this sample rate',
        'e_rate_not_found': 'No suitable sample rate was found',
        'e_start_end_order': 'Start note ({start}) must be at or below the end note ({end})',
        'e_no_files': 'No files were generated ({detail})',
        'e_no_samples': 'No samples were generated ({detail})',
        'e_bad_request': 'Invalid request format',
        'e_server': 'Server error: {e}',
        'ppmck_loop': '; To loop-play in MML (use the n command on the E channel, not note names):',
        'ppmck_tone': '; play @DPCM{idx} as a tone',
    },
}


def L(lang: str, key: str, **kw) -> str:
    d = _MSG.get(lang) or _MSG['ja']
    s = d.get(key) or _MSG['ja'].get(key) or key
    return s.format(**kw) if kw else s


# 共有関数（dpcm_batch/dpcm_sunsoft）が返す失敗理由・例外文をGUI用に英訳する。
# 既知パターンのみ対応し、未知の文字列はそのまま返す。
_REASON_EXACT = {
    '適切なパラメータが見つかりません': 'No suitable parameters found',
    '適切なサンプルレートが見つかりません': 'No suitable sample rate found',
    'WAVファイルが選択されていません': 'No WAV file selected',
    'WAVデータのデコードに失敗しました': 'Failed to decode WAV data',
}
_REASON_PREFIX = [
    ('出力ディレクトリの作成権限がありません: ', 'No permission to create the output directory: '),
    ('出力ディレクトリの作成に失敗: ', 'Failed to create the output directory: '),
    ('ファイル書き込み権限がありません: ', 'No permission to write the file: '),
    ('ファイル書き込みエラー: ', 'File write error: '),
    ('カバーできないノート: ', 'Uncoverable notes: '),
]
_REASON_SUFFIX = [
    ('（許容誤差を大きくするか、対象音域を調整してください）',
     ' (increase the tolerance or adjust the note range)'),
]


def localize_reason(lang: str, reason: str) -> str:
    """共有関数由来の日本語の失敗理由/例外文を英訳（未知はそのまま）。"""
    if lang != 'en' or not reason:
        return reason
    if reason in _REASON_EXACT:
        return _REASON_EXACT[reason]
    for jp, en in _REASON_PREFIX:
        if reason.startswith(jp):
            rest = reason[len(jp):]
            for js, es in _REASON_SUFFIX:
                rest = rest.replace(js, es)
            return en + rest
    m = re.match(r'^許容誤差(.+?)cents内で生成可能な基本サンプル候補がありません$', reason)
    if m:
        return f'No base-sample candidates can be generated within {m.group(1)} cents of tolerance'
    return reason


def wav_bytes_pcm7(samples: list[int], sample_rate: float, loops: int = 1) -> bytes:
    """0〜127のPCMサンプル列を8bit WAVバイト列に変換"""
    all_samples = samples * loops
    data = bytes(min(255, s * 2) for s in all_samples)
    buf = io.BytesIO()
    with wave.open(buf, 'wb') as wf:
        wf.setnchannels(1)
        wf.setsampwidth(1)
        wf.setframerate(int(round(sample_rate)))
        wf.writeframes(data)
    return buf.getvalue()


def wav_bytes_raw(waveform: list[float], sample_rate: float, loops: int = 1) -> bytes:
    """0.0〜1.0の波形を16bit WAVバイト列に変換"""
    all_samples = waveform * loops
    data = b''.join(
        struct.pack('<h', max(-32768, min(32767, int((s - 0.5) * 65535))))
        for s in all_samples
    )
    buf = io.BytesIO()
    with wave.open(buf, 'wb') as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(int(round(sample_rate)))
        wf.writeframes(data)
    return buf.getvalue()


def resolve_custom_waveform(p: dict) -> tuple[list[float], int]:
    """
    リクエストパラメータからカスタム波形を読み込む

    Returns:
        (custom_waveform, wav_sample_rate)
        プリセット波形の場合は (None, None)
    """
    source = p.get('source', 'wave')
    if source == 'hex':
        return parse_hex_waveform(p.get('hex') or ''), None
    if source == 'fds':
        return parse_fds_waveform(p.get('fds') or ''), None
    if source == 'wav':
        raw = p.get('wav_data') or ''
        if not raw:
            raise ValueError('WAVファイルが選択されていません')
        try:
            data = base64.b64decode(raw)
        except Exception:
            raise ValueError('WAVデータのデコードに失敗しました')
        with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as tf:
            tf.write(data)
            tmp_path = tf.name
        try:
            return load_wav_waveform(tmp_path)
        finally:
            os.unlink(tmp_path)
    return None, None


def resolve_wave_type_name(p: dict) -> str:
    """バッチ/サンソフト用の波形名（ファイル名に使用）を決定"""
    source = p.get('source', 'wave')
    if source == 'wave':
        return p.get('wave') or 'saw'
    name = (p.get('name') or '').strip()
    if name:
        return name
    if source == 'wav':
        wav_name = (p.get('wav_name') or '').strip()
        if wav_name:
            return os.path.splitext(os.path.basename(wav_name))[0]
    return {'hex': 'custom', 'fds': 'fds'}.get(source, 'custom')


def make_zip(directory: str, keep) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as z:
        for fn in sorted(os.listdir(directory)):
            full = os.path.join(directory, fn)
            if os.path.isfile(full) and keep(fn):
                z.write(full, fn)
    return buf.getvalue()


def copy_outputs(tmpdir: str, output_dir: str, keep) -> dict:
    os.makedirs(output_dir, exist_ok=True)
    count = 0
    for fn in sorted(os.listdir(tmpdir)):
        full = os.path.join(tmpdir, fn)
        if os.path.isfile(full) and keep(fn):
            shutil.copy2(full, os.path.join(output_dir, fn))
            count += 1
    return {'dir': os.path.abspath(output_dir), 'files': count}


def read_file_b64(path: str) -> str:
    with open(path, 'rb') as f:
        return b64(f.read())


# =============================================================================
# 単一生成（dpcm_generator.pyのmain()相当）
# =============================================================================

def handle_generate(p: dict) -> dict:
    lang = _get_lang(p)
    warnings = []

    source = p.get('source', 'wave')
    wave_type = p.get('wave') or 'saw'
    custom_waveform, wav_sample_rate = resolve_custom_waveform(p)

    lowpass_cutoff = _opt_float(p, 'lowpass')
    lowpass_order = _int(p, 'lowpass_order', 63)
    no_auto_lowpass = bool(p.get('no_auto_lowpass'))
    lowpass_info = None

    if source == 'hex':
        wave_type_display = L(lang, 'wt_hex', n=len(custom_waveform))
    elif source == 'fds':
        wave_type_display = L(lang, 'wt_fds', n=len(custom_waveform))
    elif source == 'wav':
        wave_type_display = L(lang, 'wt_wav', n=len(custom_waveform), rate=wav_sample_rate)
        # 明示的なカットオフ指定はこの時点で適用（自動はレート確定後）
        if not no_auto_lowpass and lowpass_cutoff:
            custom_waveform = apply_lowpass_filter(
                custom_waveform, wav_sample_rate, lowpass_cutoff, lowpass_order)
            lowpass_info = L(lang, 'lp_manual', cut=f"{lowpass_cutoff:.0f}", order=lowpass_order)
    else:
        wave_type_display = wave_type

    # 目標周波数
    freq = _opt_float(p, 'freq')
    if freq:
        target_freq = freq
        note_name = f"{target_freq:.2f}Hz"
    else:
        note_name = p.get('note') or 'C4'
        target_freq = freq_from_note(note_name)

    fit_mode = bool(p.get('fit'))
    num_cycles = _int(p, 'cycles', 1)
    sub_octave = _float(p, 'sub_octave', 0.0)
    volume = _float(p, 'volume', 1.0)
    auto_start = bool(p.get('auto_start'))
    loop_match = bool(p.get('loop_match'))
    warmup = bool(p.get('warmup'))
    quality = bool(p.get('quality'))
    min_rate_index = _int(p, 'min_rate_index', 0)
    rate_index_param = _opt_int(p, 'rate_index')

    # サンプルレートを決定
    if fit_mode:
        loop_reserve = 64 if loop_match else 0
        require_even = sub_octave > 0
        result = find_best_fit_params(target_freq, min_cycles=num_cycles,
                                      max_cycles=max(num_cycles * 4, 64),
                                      prefer_quality=quality,
                                      min_rate_index=min_rate_index,
                                      loop_match_reserve=loop_reserve,
                                      require_even_cycles=require_even)
        if result is None and require_even:
            warnings.append(L(lang, 'w_suboct_no_even'))
            result = find_best_fit_params(target_freq, min_cycles=num_cycles,
                                          max_cycles=max(num_cycles * 4, 64),
                                          prefer_quality=quality,
                                          min_rate_index=min_rate_index,
                                          loop_match_reserve=loop_reserve)
        if result is None:
            raise ValueError(L(lang, 'e_param_not_found'))
        sample_rate, rate_index, num_samples, num_cycles, total_samples = result
    elif rate_index_param is not None:
        rate_index = rate_index_param
        sample_rate = SAMPLE_RATES_NTSC[rate_index]
        num_samples = round(sample_rate / target_freq)
        if num_samples < 1:
            raise ValueError(L(lang, 'e_freq_too_high'))
        if sub_octave > 0 and num_cycles % 2 != 0:
            num_cycles += 1
            warnings.append(L(lang, 'w_suboct_adjust', n=num_cycles))
        total_samples = num_samples * num_cycles
    else:
        sample_rate, rate_index, num_samples = find_best_sample_rate(target_freq)
        if sample_rate is None:
            raise ValueError(L(lang, 'e_rate_not_found'))
        if sub_octave > 0 and num_cycles % 2 != 0:
            num_cycles += 1
            warnings.append(L(lang, 'w_suboct_adjust', n=num_cycles))
        total_samples = num_samples * num_cycles

    actual_freq = sample_rate / num_samples
    cents_error = 1200 * math.log2(actual_freq / target_freq)
    final_samples, final_bytes = find_nearest_valid_sample_count(total_samples)

    # WAV入力時の自動ローパスフィルタ（レート確定後）
    if source == 'wav' and wav_sample_rate and not no_auto_lowpass and not lowpass_cutoff:
        auto_cutoff = sample_rate * 0.4
        custom_waveform = apply_lowpass_filter(
            custom_waveform, wav_sample_rate, auto_cutoff, lowpass_order)
        lowpass_info = L(lang, 'lp_auto', cut=f"{auto_cutoff:.0f}", order=lowpass_order)

    # 波形生成（1周期分）
    if custom_waveform:
        waveform_1cycle = resample_waveform(custom_waveform, num_samples)
    else:
        waveform_1cycle = generate_waveform(wave_type, num_samples)

    # 音量調整
    if volume != 1.0:
        waveform_1cycle = adjust_volume(waveform_1cycle, volume)
        if volume > 1.0:
            warnings.append(L(lang, 'w_volume_clip', pct=f"{volume:.0%}"))

    # 複数周期分に拡張（warmup有効時は助走用に波形の1周期分を先頭に追加。
    # サブオクターブ混合時は波形の周期が2倍になるため2周期分）
    warmup_cycles = (2 if sub_octave > 0 else 1) if warmup else 0
    waveform = waveform_1cycle * (num_cycles + warmup_cycles)

    # サブオクターブ混合
    if sub_octave > 0:
        if num_cycles % 2 != 0:
            warnings.append(L(lang, 'w_odd_cycles', n=num_cycles))
        waveform = mix_sub_octave(waveform, num_samples, wave_type, sub_octave,
                                  custom_waveform=custom_waveform if custom_waveform else None)

    # dPCMエンコード
    warmup_count = num_samples * warmup_cycles
    dpcm_data, actual_start = encode_dpcm(waveform, loop_match=loop_match,
                                          auto_start=auto_start,
                                          warmup_samples=warmup_count)

    decoded = decode_dpcm(dpcm_data, actual_start)
    preview_loops = _int(p, 'preview_loops', 4)
    raw_loops = _opt_int(p, 'raw_preview_loops') or preview_loops

    # 出力後の波形（warmup分を除いたエンコード対象）
    encoded_waveform = waveform[warmup_count:] if warmup_count else waveform

    if fit_mode:
        if min_rate_index:
            quality_str = L(lang, 'q_minrate', idx=f"{min_rate_index:X}")
        elif quality:
            quality_str = L(lang, 'q_quality')
        else:
            quality_str = L(lang, 'q_size')
    else:
        quality_str = None

    # ppmck定義例
    dpcm_index = _int(p, 'dpcm_index', 0)
    dpcm_path = p.get('dpcm_path') or ''
    filename = (p.get('output_name') or '').strip() or 'output.dmc'
    ppmck = (f'@DPCM{dpcm_index} = {{ "{dpcm_path}{filename}", {rate_index}, 0, 0, 1 }}\n\n'
             f'{L(lang, "ppmck_loop")}\n'
             f'E n{dpcm_index}   {L(lang, "ppmck_tone", idx=dpcm_index)}')

    return {
        'info': {
            'wave_type_display': wave_type_display,
            'note_name': note_name,
            'target_freq': target_freq,
            'rate_index': rate_index,
            'sample_rate': sample_rate,
            'samples_per_cycle': num_samples,
            'num_cycles': num_cycles,
            'total_samples': total_samples,
            'final_samples': final_samples,
            'actual_freq': actual_freq,
            'cents_error': cents_error,
            'file_size': len(dpcm_data),
            'fit_mode': fit_mode,
            'quality_str': quality_str,
            'start_value': actual_start,
            'auto_start': auto_start,
            'loop_match': loop_match,
            'warmup': warmup,
            'sub_octave': sub_octave,
            'volume': volume,
            'lowpass': lowpass_info,
        },
        'warnings': warnings,
        'dmc_base64': b64(dpcm_data),
        'preview_wav_base64': b64(wav_bytes_pcm7(decoded, sample_rate, preview_loops)),
        'raw_wav_base64': b64(wav_bytes_raw(encoded_waveform, sample_rate, raw_loops)),
        'decoded': decoded,
        'raw_waveform': [round(v, 4) for v in encoded_waveform],
        'ppmck': ppmck,
    }


# =============================================================================
# バッチ生成（dpcm_batch.py相当）
# =============================================================================

def _make_scale_previews(p, lang, tmpdir, target_notes, note_mapping,
                         base_samples, name_prefix):
    """スケールプレビューWAVを2種類（全音階／幹音のみ）生成してbase64で返す。

    バッチ・サンソフト両タブで共用。幹音のみ版は♯を除いたノート列で
    generate_scale_previewを呼び直すだけ（音楽初心者向けのドレミ確認用）。
    """
    out = {'scale_wav_base64': None, 'scale_major_wav_base64': None,
           'scale_error': None}
    if not p.get('scale_preview', True):
        return out
    duration = _float(p, 'scale_duration', 0.5)
    auto_start = bool(p.get('auto_start'))
    try:
        path = generate_scale_preview(
            target_notes, note_mapping, base_samples, tmpdir,
            output_filename=f"{name_prefix}_scale.wav",
            duration=duration, auto_start=auto_start)
        out['scale_wav_base64'] = read_file_b64(path)
    except ValueError as e:
        out['scale_error'] = localize_reason(lang, str(e))
    naturals = [n for n in target_notes if '#' not in n]
    if naturals:
        try:
            path = generate_scale_preview(
                naturals, note_mapping, base_samples, tmpdir,
                output_filename=f"{name_prefix}_scale_major.wav",
                duration=duration, auto_start=auto_start)
            out['scale_major_wav_base64'] = read_file_b64(path)
        except ValueError:
            pass  # 全音階側が成功していれば幹音のみ版の失敗は表示しない
    return out


def handle_batch(p: dict) -> dict:
    lang = _get_lang(p)
    custom_waveform, wav_sample_rate = resolve_custom_waveform(p)
    wave_type = resolve_wave_type_name(p)
    include_preview = bool(p.get('include_preview'))
    raw_preview = bool(p.get('raw_preview'))
    output_dir = (p.get('output_dir') or '').strip()

    start = p.get('start') or 'C2'
    end = p.get('end') or 'F4'
    notes = generate_note_range(start, end)
    if not notes:
        raise ValueError(L(lang, 'e_start_end_order', start=start, end=end))

    with tempfile.TemporaryDirectory() as tmpdir:
        results, failures = generate_note_set(
            wave_type, tmpdir,
            custom_waveform=custom_waveform,
            cycles=_int(p, 'cycles', 1),
            volume=_float(p, 'volume', 1.0),
            auto_start=bool(p.get('auto_start')),
            loop_match=bool(p.get('loop_match')),
            fit=bool(p.get('fit')),
            prefer_quality=bool(p.get('quality')),
            min_rate_index=_int(p, 'min_rate_index', 0),
            preview=True,  # ブラウザ再生用に常に生成（ZIP収録は選択制）
            preview_loops=_int(p, 'preview_loops', 4),
            raw_preview=raw_preview,
            raw_preview_loops=_opt_int(p, 'raw_preview_loops'),
            warmup=bool(p.get('warmup')),
            lowpass_cutoff=_opt_float(p, 'lowpass'),
            lowpass_order=_int(p, 'lowpass_order', 63),
            wav_sample_rate=wav_sample_rate,
            no_auto_lowpass=bool(p.get('no_auto_lowpass')),
            sub_octave=_float(p, 'sub_octave', 0.0),
            notes=notes,
        )

        failures_out = [{'note': n, 'reason': localize_reason(lang, r)} for n, r in failures]
        if not results:
            detail = '; '.join(f"{f['note'] or ''}: {f['reason']}" for f in failures_out)
            raise ValueError(L(lang, 'e_no_files', detail=detail))

        defines = generate_ppmck_defines(results, wave_type,
                                         start_index=_int(p, 'dpcm_start_index', 0),
                                         dpcm_path=p.get('dpcm_path') or '',
                                         lang=lang)
        defines_name = f"{wave_type}_defines.txt"
        with open(os.path.join(tmpdir, defines_name), 'w') as f:
            f.write(defines)

        # スケールプレビュー（バッチは各ノートが自分自身のサンプルなので恒等マッピング）
        scale = _make_scale_previews(
            p, lang, tmpdir, [r['note'] for r in results],
            {r['note']: (r['note'], r['rate_index'], 0.0) for r in results},
            results, wave_type)

        out_results = []
        for r in results:
            path = os.path.join(tmpdir, r['filename'])
            item = dict(r)
            item['cents_error'] = 1200 * math.log2(r['actual_freq'] / r['target_freq'])
            item['dmc_base64'] = read_file_b64(path)
            wav_path = os.path.splitext(path)[0] + '.wav'
            if os.path.exists(wav_path):
                item['preview_wav_base64'] = read_file_b64(wav_path)
            out_results.append(item)

        def keep(fn):
            if fn.endswith('.dmc') or fn.endswith('.txt'):
                return True
            return include_preview and fn.endswith('.wav')

        zip_data = make_zip(tmpdir, keep)
        copied = copy_outputs(tmpdir, output_dir, keep) if output_dir else None

    return {
        'wave_type': wave_type,
        'start': start,
        'end': end,
        'results': out_results,
        'failures': failures_out,
        'defines': defines,
        'defines_name': defines_name,
        'zip_base64': b64(zip_data),
        'total_size': sum(r['size'] for r in results),
        'copied': copied,
        **scale,
    }


# =============================================================================
# サンソフトベース方式（dpcm_sunsoft.py相当）
# =============================================================================

def _sunsoft_plan(p: dict):
    start = p.get('start') or 'C2'
    end = p.get('end') or 'F4'
    max_error = _float(p, 'max_error', 25.0)
    prefer_higher_rate = bool(p.get('prefer_quality'))
    prefer_quality_samples = not bool(p.get('size_priority'))
    cycles = _int(p, 'cycles', 8)
    base_notes, note_mapping = find_minimum_sample_set(
        start, end, max_error, prefer_higher_rate, prefer_quality_samples,
        cycles=cycles)
    target_notes = generate_note_range(start, end)
    return start, end, max_error, base_notes, note_mapping, target_notes


def _mapping_to_list(target_notes, note_mapping, base_note_to_idx=None):
    out = []
    for note in target_notes:
        if note in note_mapping:
            base_note, rate_idx, error = note_mapping[note]
            entry = {'note': note, 'base': base_note,
                     'rate_index': rate_idx, 'error': error}
            if base_note_to_idx is not None:
                entry['sample_index'] = base_note_to_idx.get(base_note)
            out.append(entry)
        else:
            out.append({'note': note, 'base': None})
    return out


def _mapping_stats(target_notes, note_mapping):
    errors = [abs(note_mapping[n][2]) for n in target_notes if n in note_mapping]
    if not errors:
        return None
    return {
        'max_error': max(errors),
        'avg_error': sum(errors) / len(errors),
        'covered': len(errors),
        'total': len(target_notes),
    }


def handle_sunsoft_analyze(p: dict) -> dict:
    start, end, max_error, base_notes, note_mapping, target_notes = _sunsoft_plan(p)
    return {
        'start': start,
        'end': end,
        'max_error': max_error,
        'base_notes': base_notes,
        'mapping': _mapping_to_list(target_notes, note_mapping),
        'stats': _mapping_stats(target_notes, note_mapping),
    }


def handle_sunsoft_generate(p: dict) -> dict:
    lang = _get_lang(p)
    custom_waveform, wav_sample_rate = resolve_custom_waveform(p)
    wave_type = resolve_wave_type_name(p)
    prefix = p.get('prefix') if p.get('prefix') is not None else 'sunsoft_'
    include_preview = bool(p.get('include_preview'))
    output_dir = (p.get('output_dir') or '').strip()

    start, end, max_error, base_notes, note_mapping, target_notes = _sunsoft_plan(p)

    with tempfile.TemporaryDirectory() as tmpdir:
        samples, failures = generate_sunsoft_samples(
            base_notes, wave_type, tmpdir,
            prefix=prefix,
            custom_waveform=custom_waveform,
            cycles=_int(p, 'cycles', 8),
            volume=_float(p, 'volume', 1.0),
            auto_start=bool(p.get('auto_start')),
            loop_match=bool(p.get('loop_match')),
            fit=bool(p.get('fit', True)),
            prefer_quality=bool(p.get('prefer_quality')),
            preview=True,  # ブラウザ再生用に常に生成（ZIP収録は選択制）
            preview_loops=_int(p, 'preview_loops', 4),
            raw_preview=bool(p.get('raw_preview')),
            raw_preview_loops=_opt_int(p, 'raw_preview_loops'),
            warmup=bool(p.get('warmup')),
            max_cents_error=max_error,
            lowpass_cutoff=_opt_float(p, 'lowpass'),
            lowpass_order=_int(p, 'lowpass_order', 63),
            wav_sample_rate=wav_sample_rate,
            no_auto_lowpass=bool(p.get('no_auto_lowpass')),
            sub_octave=_float(p, 'sub_octave', 0.0),
        )

        failures_out = [{'note': n, 'reason': localize_reason(lang, r)} for n, r in failures]
        if not samples:
            detail = '; '.join(f"{f['note'] or ''}: {f['reason']}" for f in failures_out)
            raise ValueError(L(lang, 'e_no_samples', detail=detail))

        defines = generate_sunsoft_defines(
            samples, note_mapping, target_notes, wave_type, start, end, max_error,
            start_index=_int(p, 'dpcm_start_index', 0),
            dpcm_path=p.get('dpcm_path') or '',
            lang=lang)
        defines_name = f"{prefix}{wave_type}_defines.txt"
        with open(os.path.join(tmpdir, defines_name), 'w', encoding='utf-8') as f:
            f.write(defines)

        # スケールプレビュー
        scale = _make_scale_previews(
            p, lang, tmpdir, target_notes, note_mapping, samples,
            f"{prefix}{wave_type}")

        out_samples = []
        base_note_to_idx = {}
        for idx, s in enumerate(samples):
            base_note_to_idx[s['note']] = idx
            path = os.path.join(tmpdir, s['filename'])
            item = dict(s)
            item['cents_error'] = 1200 * math.log2(s['actual_freq'] / s['target_freq'])
            item['dmc_base64'] = read_file_b64(path)
            wav_path = os.path.splitext(path)[0] + '.wav'
            if os.path.exists(wav_path):
                item['preview_wav_base64'] = read_file_b64(wav_path)
            out_samples.append(item)

        def keep(fn):
            if fn.endswith('.dmc') or fn.endswith('.txt'):
                return True
            return include_preview and fn.endswith('.wav')

        zip_data = make_zip(tmpdir, keep)
        copied = copy_outputs(tmpdir, output_dir, keep) if output_dir else None

    total_size = sum(s['size'] for s in samples)
    return {
        'wave_type': wave_type,
        'start': start,
        'end': end,
        'max_error': max_error,
        'base_notes': base_notes,
        'samples': out_samples,
        'failures': failures_out,
        'mapping': _mapping_to_list(target_notes, note_mapping, base_note_to_idx),
        'stats': _mapping_stats(target_notes, note_mapping),
        'defines': defines,
        'defines_name': defines_name,
        'zip_base64': b64(zip_data),
        'total_size': total_size,
        'copied': copied,
        **scale,
    }


# =============================================================================
# HTTPサーバー
# =============================================================================

def handle_rates(_p=None) -> dict:
    return {
        'rates': SAMPLE_RATES_NTSC,
        'cents_from_f': calculate_rate_ratios(),
        'batch_notes': BATCH_NOTES,
    }


POST_ROUTES = {
    '/api/generate': handle_generate,
    '/api/batch': handle_batch,
    '/api/sunsoft/analyze': handle_sunsoft_analyze,
    '/api/sunsoft/generate': handle_sunsoft_generate,
}


class GuiHandler(BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'

    def _send_json(self, obj, status=200):
        body = json.dumps(obj).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = self.path.split('?', 1)[0]
        if path in ('/', '/index.html'):
            _touch_client_marker()
            try:
                with open(HTML_PATH, 'rb') as f:
                    body = f.read()
            except IOError:
                self._send_json({'error': f'GUIファイルが見つかりません: {HTML_PATH}'}, 500)
                return
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif path == '/api/ping':
            _touch_client_marker()
            self._send_json({'ok': True})
        elif path == '/api/rates':
            self._send_json(handle_rates())
        else:
            self._send_json({'error': 'not found'}, 404)

    def do_POST(self):
        handler = POST_ROUTES.get(self.path)
        if handler is None:
            self._send_json({'error': 'not found'}, 404)
            return
        lang = 'ja'
        try:
            length = int(self.headers.get('Content-Length') or 0)
            params = json.loads(self.rfile.read(length) or b'{}')
            if not isinstance(params, dict):
                raise ValueError(L('ja', 'e_bad_request'))
            lang = _get_lang(params)
            result = handler(params)
            self._send_json(result)
        except (ValueError, KeyError, TypeError, FileNotFoundError) as e:
            # ハンドラで組み立てたメッセージは既に対象言語。共有関数由来の
            # 日本語例外文はここで英訳のフォールバックを試みる。
            self._send_json({'error': localize_reason(lang, str(e))}, 400)
        except Exception as e:
            self._send_json({'error': L(lang, 'e_server', e=e)}, 500)

    def log_message(self, fmt, *args):
        # APIアクセスログは1行だけ簡潔に（定期pingはログに出さない）
        if self.path == '/api/ping':
            return
        sys.stderr.write(f"[GUI] {self.command} {self.path} - {args[1] if len(args) > 1 else ''}\n")


def main():
    parser = argparse.ArgumentParser(description='NES dPCM Generator - Web GUI')
    parser.add_argument('--port', type=int, default=8765, help='ポート番号（デフォルト: 8765）')
    parser.add_argument('--host', default='127.0.0.1', help='バインドするホスト（デフォルト: 127.0.0.1）')
    parser.add_argument('--no-browser', action='store_true', help='ブラウザを自動で開かない')
    args = parser.parse_args()

    if not os.path.exists(HTML_PATH):
        print(f"エラー: GUIファイルが見つかりません: {HTML_PATH}", file=sys.stderr)
        sys.exit(1)

    global _CLIENT_MARKER_PATH
    _CLIENT_MARKER_PATH = os.path.join(
        tempfile.gettempdir(), f'dpcm_gui_client_{args.port}.marker')

    server = ThreadingHTTPServer((args.host, args.port), GuiHandler)
    url = f"http://{args.host}:{args.port}/"
    print("=== NES dPCM Generator GUI ===")
    print(f"起動しました: {url}")
    print("終了するには Ctrl+C を押してください")

    if not args.no_browser:
        if _client_recently_active():
            print("直近までGUIが開かれていたため、ブラウザの自動起動をスキップしました")
            print("（開いていたタブをそのまま利用できます。閉じた場合は上記URLを開いてください）")
        else:
            webbrowser.open(url)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n終了します")
        server.shutdown()


if __name__ == '__main__':
    main()
