"""pymic パッケージをコマンドラインから直接起動するためのエントリポイントモジュール。

``python -m pymic`` で起動するとアプリケーションのメインウィンドウが表示される。
"""

from .app import main


def _main():
    """パッケージエントリポイント。`app.main` を呼び出してアプリを起動する。"""
    main()


if __name__ == "__main__":
    _main()
