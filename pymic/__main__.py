"""python -m pymic でパッケージを直接実行するためのエントリーポイント。"""

from .app import main


def _main():
    """パッケージエントリーポイント用ラッパー。pymic.app.main() を呼び出す。"""
    main()


if __name__ == "__main__":
    _main()
