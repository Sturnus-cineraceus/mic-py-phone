import os
import sys
import shutil
import zipfile
import tempfile
from urllib.request import urlopen

DEFAULT_WIN_URL = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"


def download_and_extract_ffmpeg(dest_dir: str, url: str = None):
    """現在のプラットフォーム向け ffmpeg を zip でダウンロードし、dest_dir/bin に展開する。

    Download ffmpeg zip for the current platform and extract ffmpeg binary
    into dest_dir/bin (creates directories as needed).

    ダウンロードの進捗はコンソールに出力される。
    ディレクトリが存在しない場合は自動的に作成する。

    Args:
        dest_dir: ffmpeg を展開する先のディレクトリパス。
        url: ダウンロード元 URL。省略時は Windows 向けのデフォルト URL を使用。

    Returns:
        str: 展開された ffmpeg 実行ファイルの絶対パス。

    Raises:
        RuntimeError: アーカイブ内に ffmpeg バイナリが見つからない場合。
    """
    if url is None:
        url = DEFAULT_WIN_URL

    os.makedirs(dest_dir, exist_ok=True)
    bin_dir = os.path.join(dest_dir, "bin")
    os.makedirs(bin_dir, exist_ok=True)

    # Download to temporary file with progress reporting
    tmpfd, tmpname = tempfile.mkstemp(suffix=".zip")
    os.close(tmpfd)
    try:
        print(f"Downloading ffmpeg from {url} ...")
        with urlopen(url) as resp, open(tmpname, "wb") as out:
            total = resp.getheader("Content-Length")
            try:
                total = int(total) if total is not None else None
            except Exception:
                total = None

            downloaded = 0
            chunk_size = 64 * 1024
            while True:
                chunk = resp.read(chunk_size)
                if not chunk:
                    break
                out.write(chunk)
                downloaded += len(chunk)
                if total:
                    pct = downloaded / total * 100.0
                    print(
                        f"\rDownloaded {downloaded / 1024 / 1024:.2f} MB / {total / 1024 / 1024:.2f} MB ({pct:5.1f}%)",
                        end="",
                    )
                else:
                    print(f"\rDownloaded {downloaded / 1024 / 1024:.2f} MB", end="")
            print("\nDownload complete, extracting...")
        with zipfile.ZipFile(tmpname, "r") as z:
            # Find ffmpeg.exe or ffmpeg in archive and extract
            candidates = [
                n
                for n in z.namelist()
                if n.lower().endswith("ffmpeg.exe") or n.endswith("/ffmpeg")
            ]
            if not candidates:
                # fallback: extract all and search
                z.extractall(dest_dir)
            else:
                # extract only directories containing candidates to preserve relative layout
                for cand in candidates:
                    # extract the file
                    target_name = os.path.basename(cand)
                    out_path = os.path.join(bin_dir, target_name)
                    with z.open(cand) as src, open(out_path, "wb") as dst:
                        shutil.copyfileobj(src, dst)
                    # ensure executable bit on non-windows
                    try:
                        os.chmod(out_path, 0o755)
                    except Exception:
                        pass

        # If extraction didn't place ffmpeg in bin, try to locate in dest_dir
        ffpath = None
        for root, dirs, files in os.walk(dest_dir):
            for f in files:
                if f.lower().startswith("ffmpeg"):
                    candidate = os.path.join(root, f)
                    # prefer exe on windows
                    if sys.platform.startswith("win") and f.lower().endswith(".exe"):
                        ffpath = candidate
                        break
                    if ffpath is None:
                        ffpath = candidate
            if ffpath:
                break

        if ffpath is None:
            raise RuntimeError("ffmpeg binary not found inside downloaded archive")

        # copy to bin_dir if not already there
        final = os.path.join(bin_dir, os.path.basename(ffpath))
        if os.path.abspath(ffpath) != os.path.abspath(final):
            shutil.copy2(ffpath, final)
            try:
                os.chmod(final, 0o755)
            except Exception:
                pass

        return os.path.abspath(final)
    finally:
        try:
            os.remove(tmpname)
        except Exception:
            pass


if __name__ == "__main__":
    out = download_and_extract_ffmpeg("build/ffmpeg")
    print("ffmpeg extracted to", out)
