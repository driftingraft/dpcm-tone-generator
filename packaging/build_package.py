#!/usr/bin/env python3
"""
NES dPCM Generator - 配布パッケージ組み立てスクリプト

一般ユーザー（Pythonを持っていない人）向けの配布パッケージを作成します。
標準ライブラリのみで動作し、Windows/Mac/Linux のどこからでも実行できます。

作成されるもの（dist/ 以下）:
  - NES-dPCM-Generator-Windows/   … 埋め込みPython同梱。起動.bat をダブルクリックで動く
  - NES-dPCM-Generator-Mac/       … システムのpython3を使用。起動.command で動く
  （--zip を付けると、それぞれ .zip も作成）

使い方:
  python3 packaging/build_package.py                 # Win/Mac 両方をフォルダで作成
  python3 packaging/build_package.py --zip           # zip も作成
  python3 packaging/build_package.py --target windows # Windows版のみ
  python3 packaging/build_package.py --target mac     # Mac版のみ
  python3 packaging/build_package.py --no-python      # 埋め込みPythonをDLしない（構成確認用）
  python3 packaging/build_package.py --python-version 3.12.8
"""

import argparse
import os
import shutil
import stat
import sys
import urllib.request
import zipfile
from pathlib import Path

PACKAGING = Path(__file__).resolve().parent
REPO_ROOT = PACKAGING.parent
LAUNCHERS = PACKAGING / 'launchers'

# GUIの動作に必要なアプリ本体ファイル（app/ に配置）
APP_FILES = [
    'dpcm_gui.py',
    'dpcm_gui.html',
    'dpcm_generator.py',
    'dpcm_batch.py',
    'dpcm_sunsoft.py',
]

# 3.13以降は audioop 等の一部標準モジュールが削除されているため、
# 開発環境と同じ 3.12 系を既定にする（本ツールは標準ライブラリのみ使用）。
DEFAULT_PYTHON_VERSION = '3.12.8'
DEFAULT_ARCH = 'amd64'  # amd64 / win32 / arm64

PKG_BASENAME = 'NES-dPCM-Generator'


def log(msg: str) -> None:
    print(msg, flush=True)


def copy_app_files(dist: Path) -> None:
    """アプリ本体を dist/app/ にコピー"""
    app_dir = dist / 'app'
    app_dir.mkdir(parents=True, exist_ok=True)
    for name in APP_FILES:
        src = REPO_ROOT / name
        if not src.exists():
            raise FileNotFoundError(f'アプリファイルが見つかりません: {src}')
        shutil.copy2(src, app_dir / name)
    log(f'  アプリ本体をコピー: {len(APP_FILES)} ファイル -> app/')


def copy_launcher(src_name: str, dist: Path, *, crlf: bool = False, executable: bool = False) -> None:
    """ランチャー/説明ファイルを dist/ 直下にコピー（batはCRLF化、commandは実行権限付与）"""
    src = LAUNCHERS / src_name
    dest = dist / src_name
    data = src.read_bytes()
    if crlf:
        data = data.replace(b'\r\n', b'\n').replace(b'\n', b'\r\n')
    dest.write_bytes(data)
    if executable:
        dest.chmod(dest.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    log(f'  ランチャーを配置: {src_name}')


def download_embedded_python(target: Path, version: str, arch: str) -> None:
    """python.org から Windows 埋め込みパッケージを取得して展開"""
    url = f'https://www.python.org/ftp/python/{version}/python-{version}-embed-{arch}.zip'
    tmp_zip = target.parent / f'_embed_{version}_{arch}.zip'
    log(f'  埋め込みPythonをダウンロード: {url}')
    try:
        urllib.request.urlretrieve(url, tmp_zip)
    except Exception as e:
        raise RuntimeError(
            f'埋め込みPythonのダウンロードに失敗しました: {e}\n'
            f'  URL: {url}\n'
            f'  バージョンやアーキテクチャ（--python-version / --arch）をご確認ください。'
        )
    target.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(tmp_zip) as z:
        z.extractall(target)
    tmp_zip.unlink()
    exe = target / 'python.exe'
    if not exe.exists():
        raise RuntimeError(f'展開後に python.exe が見つかりません: {exe}')
    log(f'  埋め込みPythonを展開: python/ ({version} {arch})')
    patch_pth_for_app(target)


def patch_pth_for_app(python_dir: Path) -> None:
    """埋め込みPythonの ._pth に app/ を追記し、兄弟モジュールをimport可能にする。

    埋め込み版は ._pth で sys.path が固定され、スクリプトの隣のモジュールを
    自動では見つけられないことがある。python/ から見た app/ は ..\\app なので、
    その相対パスを検索パスに加える。
    """
    pth_files = list(python_dir.glob('*._pth'))
    if not pth_files:
        raise RuntimeError(f'._pth ファイルが見つかりません: {python_dir}')
    app_entry = '..\\app'
    for pth in pth_files:
        lines = pth.read_text(encoding='utf-8').splitlines()
        if any(line.strip() == app_entry for line in lines):
            continue
        # 先頭の path エントリ群の直後（最初のコメント/空行の前）に挿入
        insert_at = len(lines)
        for i, line in enumerate(lines):
            s = line.strip()
            if s == '' or s.startswith('#'):
                insert_at = i
                break
        lines.insert(insert_at, app_entry)
        pth.write_text('\r\n'.join(lines) + '\r\n', encoding='utf-8')
        log(f'  ._pth に app/ を追記: {pth.name} (+{app_entry})')


def make_zip_archive(dist: Path) -> Path:
    """dist フォルダを zip 化（.command の実行権限を保持）"""
    zip_path = dist.parent / (dist.name + '.zip')
    if zip_path.exists():
        zip_path.unlink()
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as z:
        for path in sorted(dist.rglob('*')):
            if path.is_dir():
                continue
            rel = path.relative_to(dist.parent)
            zi = zipfile.ZipInfo(rel.as_posix())
            zi.compress_type = zipfile.ZIP_DEFLATED
            # 実行権限などのunixパーミッションを保持（Macの .command 用）
            zi.external_attr = (path.stat().st_mode & 0xFFFF) << 16
            z.writestr(zi, path.read_bytes())
    size_mb = zip_path.stat().st_size / (1024 * 1024)
    log(f'  zip作成: {zip_path.name} ({size_mb:.1f} MB)')
    return zip_path


def build_windows(out_dir: Path, version: str, arch: str, include_python: bool, make_zip: bool) -> None:
    dist = out_dir / f'{PKG_BASENAME}-Windows'
    log(f'[Windows版] {dist}')
    if dist.exists():
        shutil.rmtree(dist)
    dist.mkdir(parents=True)
    copy_app_files(dist)
    copy_launcher('起動.bat', dist, crlf=True)
    copy_launcher('お読みください.txt', dist, crlf=True)
    if include_python:
        download_embedded_python(dist / 'python', version, arch)
    else:
        log('  （--no-python 指定のため埋め込みPythonはスキップ）')
    if make_zip:
        make_zip_archive(dist)
    log('  完了\n')


def build_mac(out_dir: Path, make_zip: bool) -> None:
    dist = out_dir / f'{PKG_BASENAME}-Mac'
    log(f'[Mac版] {dist}')
    if dist.exists():
        shutil.rmtree(dist)
    dist.mkdir(parents=True)
    copy_app_files(dist)
    copy_launcher('起動.command', dist, executable=True)
    copy_launcher('お読みください.txt', dist)
    if make_zip:
        make_zip_archive(dist)
    log('  完了\n')


def main() -> int:
    parser = argparse.ArgumentParser(description='NES dPCM Generator 配布パッケージ組み立て')
    parser.add_argument('--target', choices=['windows', 'mac', 'all'], default='all',
                        help='作成する対象（デフォルト: all）')
    parser.add_argument('--out-dir', default=str(REPO_ROOT / 'dist'),
                        help='出力先ディレクトリ（デフォルト: dist/）')
    parser.add_argument('--python-version', default=DEFAULT_PYTHON_VERSION,
                        help=f'埋め込みPythonのバージョン（デフォルト: {DEFAULT_PYTHON_VERSION}）')
    parser.add_argument('--arch', default=DEFAULT_ARCH,
                        help=f'埋め込みPythonのアーキテクチャ amd64/win32/arm64（デフォルト: {DEFAULT_ARCH}）')
    parser.add_argument('--no-python', action='store_true',
                        help='Windows版で埋め込みPythonをダウンロードしない（構成確認用）')
    parser.add_argument('--zip', action='store_true', help='フォルダに加えてzipも作成する')
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    log('=== NES dPCM Generator 配布パッケージ組み立て ===')
    log(f'出力先: {out_dir}\n')

    if args.target in ('windows', 'all'):
        build_windows(out_dir, args.python_version, args.arch,
                      include_python=not args.no_python, make_zip=args.zip)
    if args.target in ('mac', 'all'):
        build_mac(out_dir, make_zip=args.zip)

    log('すべて完了しました。')
    return 0


if __name__ == '__main__':
    sys.exit(main())
