"""Build script: download ffmpeg and run PyInstaller to include it in the build.

Usage: python build_dist.py

This script downloads ffmpeg into build/ffmpeg/bin and then runs PyInstaller
with --add-binary to include the ffmpeg executable into the distributed folder.
"""
import os
import sys
import shutil
import subprocess
from pathlib import Path

from build_tools.fetch_ffmpeg import download_and_extract_ffmpeg


def find_pyinstaller():
    return shutil.which('pyinstaller')


def main():
    # ensure running from repo root
    repo_root = Path(__file__).parent
    os.chdir(repo_root)

    print('Ensuring ffmpeg is available...')
    ffpath = download_and_extract_ffmpeg(str(repo_root / 'build' / 'ffmpeg'))
    print('ffmpeg at', ffpath)

    pyinstaller = find_pyinstaller()
    if not pyinstaller:
        print('pyinstaller not found on PATH. Activate your venv or install PyInstaller.')
        sys.exit(1)

    # PyInstaller add-binary sep differs between platforms
    sep = ';' if os.name == 'nt' else ':'
    add_binary = f"{ffpath}{sep}."

    # include web directory as data (same as original spec)
    add_data = f"web{sep}web"

    cmd = [
        pyinstaller,
        '--noconfirm',
        '--clean',
        '--name', 'main',
        '--add-binary', add_binary,
        '--add-data', add_data,
        'main.py',
    ]

    print('Running:', ' '.join(cmd))
    proc = subprocess.run(cmd)
    if proc.returncode != 0:
        print('PyInstaller failed with exit', proc.returncode)
        sys.exit(proc.returncode)

    print('Build complete. Check the dist/ directory.')


if __name__ == '__main__':
    main()
