#!/usr/bin/env python3
"""HTML紙芝居からスライド画像を抽出するツール.

Playwright を使い、HTMLファイルをヘッドレスブラウザで開き、
キーボード操作でスライドを遷移しながらスクリーンショットを撮影する。

Usage (CLI):
    python html_to_images.py docs/紙芝居.html --slides 14 --output input/images/
    python html_to_images.py docs/紙芝居.html --slides 14 --output input/images/ --key ArrowRight
    python html_to_images.py docs/紙芝居.html --slides 14 --wait 3.0
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path


def capture_slides(
    html_path: str,
    output_dir: str,
    num_slides: int,
    nav_key: str = "ArrowRight",
    wait: float = 2.0,
    width: int = 1920,
    height: int = 1080,
    *,
    progress_callback: object | None = None,
) -> list[Path]:
    """HTMLファイルからスライドをスクリーンショットとしてキャプチャする.

    Args:
        html_path: HTMLファイルのパス.
        output_dir: スクリーンショットの出力先ディレクトリ.
        num_slides: 撮影するスライド数.
        nav_key: スライド遷移に使うキー (デフォルト: ArrowRight).
        wait: 初回読み込み待機時間（秒）.
        width: ビューポート幅.
        height: ビューポート高さ.
        progress_callback: 進捗報告用コールバック。呼び出し時に (current, total, path) を渡す.

    Returns:
        保存したスクリーンショットのパスリスト.

    Raises:
        FileNotFoundError: HTMLファイルが存在しない場合.
        RuntimeError: Playwright がインストールされていない場合.
    """
    html_file = Path(html_path).resolve()
    if not html_file.exists():
        msg = f"HTMLファイルが見つかりません: {html_file}"
        raise FileNotFoundError(msg)

    try:
        from playwright.sync_api import sync_playwright
    except ImportError as e:
        msg = (
            "playwright がインストールされていません。\n"
            "  pip install playwright\n"
            "  python -m playwright install chromium"
        )
        raise RuntimeError(msg) from e

    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)

    saved_paths: list[Path] = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": width, "height": height})

        # file:/// URL でHTMLを開く
        file_url = html_file.as_uri()
        page.goto(file_url)

        # JSバンドル展開を待機
        page.wait_for_load_state("networkidle")
        time.sleep(wait)

        for i in range(1, num_slides + 1):
            screenshot_path = output / f"slide_{i}.png"
            page.screenshot(path=str(screenshot_path))
            saved_paths.append(screenshot_path)

            if progress_callback is not None:
                progress_callback(i, num_slides, screenshot_path)
            else:
                print(f"  スライド {i}/{num_slides}: {screenshot_path}")

            if i < num_slides:
                # 次のスライドへ遷移
                page.keyboard.press(nav_key)
                time.sleep(1.0)  # 遷移アニメーション待機

        browser.close()

    return saved_paths


def main() -> None:
    """CLI エントリーポイント."""
    parser = argparse.ArgumentParser(
        description="HTML紙芝居からスライド画像を抽出する",
    )
    parser.add_argument(
        "html_path",
        help="HTMLファイルのパス",
    )
    parser.add_argument(
        "--slides",
        type=int,
        default=14,
        help="撮影するスライド数 (デフォルト: 14)",
    )
    parser.add_argument(
        "--output",
        default="input/images",
        help="出力ディレクトリ (デフォルト: input/images)",
    )
    parser.add_argument(
        "--key",
        default="ArrowRight",
        choices=["ArrowRight", "ArrowLeft", "ArrowDown", "ArrowUp", "Space", "Enter"],
        help="スライド遷移に使うキー (デフォルト: ArrowRight)",
    )
    parser.add_argument(
        "--wait",
        type=float,
        default=2.0,
        help="初回読み込み待機時間（秒） (デフォルト: 2.0)",
    )
    parser.add_argument(
        "--width",
        type=int,
        default=1920,
        help="ビューポート幅 (デフォルト: 1920)",
    )
    parser.add_argument(
        "--height",
        type=int,
        default=1080,
        help="ビューポート高さ (デフォルト: 1080)",
    )

    args = parser.parse_args()

    print(f"HTML紙芝居スクリーンショットツール")
    print(f"  入力: {args.html_path}")
    print(f"  出力: {args.output}")
    print(f"  スライド数: {args.slides}")
    print(f"  遷移キー: {args.key}")
    print(f"  待機時間: {args.wait}秒")
    print()

    try:
        paths = capture_slides(
            html_path=args.html_path,
            output_dir=args.output,
            num_slides=args.slides,
            nav_key=args.key,
            wait=args.wait,
            width=args.width,
            height=args.height,
        )
        print(f"\n完了: {len(paths)}枚のスクリーンショットを {args.output} に保存しました")
    except FileNotFoundError as e:
        print(f"エラー: {e}", file=sys.stderr)
        sys.exit(1)
    except RuntimeError as e:
        print(f"エラー: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
