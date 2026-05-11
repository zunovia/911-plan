#!/usr/bin/env python3
"""HTMLアニメーション紙芝居を動画として録画し、スライドごとのクリップを生成するツール.

自動再生タイムライン型HTMLに対応。
スライドカウンター（"NN / MM"）をリアルタイム監視しながらスクリーンショット連写を行い、
スライド境界で自動分割してクリップを生成する。

Usage (CLI):
    python html_to_video.py docs/紙芝居.html --slides 14 --output output/clips/
"""

from __future__ import annotations

import argparse
import logging
import shutil
import subprocess
import sys
import time
from collections.abc import Callable
from pathlib import Path

log = logging.getLogger(__name__)

# デフォルトFPS: スライドショーアニメーションには15fpsで十分
_DEFAULT_FPS = 15

# スライドカウンター検出用のJavaScript
_JS_GET_SLIDE_NUMBER = r"""() => {
    const all = document.body.querySelectorAll('*');
    for (const el of all) {
        if (el.children.length === 0) {
            const text = el.textContent.trim();
            const m = text.match(/^(\d+)\s*\/\s*(\d+)$/);
            if (m && el.getBoundingClientRect().top < 150) {
                return parseInt(m[1], 10);
            }
        }
    }
    return null;
}"""

# 先頭に戻すJavaScript
_JS_RETURN_TO_START = """() => {
    const buttons = document.querySelectorAll('button');
    for (const btn of buttons) {
        if (btn.title && btn.title.includes('Return to start')) {
            btn.click();
            return true;
        }
    }
    return false;
}"""


# ---------------------------------------------------------------------------
# FFmpeg ユーティリティ
# ---------------------------------------------------------------------------


def _run_ffmpeg(args: list[str], description: str) -> None:
    """FFmpegコマンドを実行する."""
    cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "warning", *args]
    log.debug("実行: %s", " ".join(cmd))
    try:
        result = subprocess.run(cmd, capture_output=True, text=True)
    except FileNotFoundError:
        log.error(
            "ffmpeg が見つかりません。FFmpegをインストールしてPATHに追加してください。"
        )
        sys.exit(1)
        return  # テストで sys.exit がモックされた場合に result への到達を防ぐ
    if result.returncode != 0:
        log.error(
            "%s に失敗しました (exit code %d)\nstderr: %s",
            description,
            result.returncode,
            result.stderr,
        )
        raise RuntimeError(f"FFmpeg failed: {description}")


def _frames_to_video(
    frames_dir: Path,
    output_path: Path,
    fps: int = _DEFAULT_FPS,
    width: int = 1920,
    height: int = 1080,
) -> None:
    """連番フレーム画像から動画を生成する."""
    _run_ffmpeg(
        [
            "-framerate", str(fps),
            "-i", str(frames_dir / "frame_%06d.png"),
            "-c:v", "libvpx-vp9",
            "-pix_fmt", "yuv420p",
            "-vf", f"scale={width}:{height}",
            "-b:v", "2M",
            str(output_path),
        ],
        f"フレーム→動画変換 ({output_path.name})",
    )


def _save_current_frames_as_clip(
    frames_dir: Path,
    frame_count: int,
    clip_path: Path,
    fps: int,
    width: int,
    height: int,
) -> None:
    """蓄積済みフレームから動画クリップを生成し、フレームを削除する."""
    if frame_count > 0:
        _frames_to_video(frames_dir, clip_path, fps=fps, width=width, height=height)
        log.info(
            "  クリップ生成: %s (%dフレーム, %.1fs)",
            clip_path.name,
            frame_count,
            frame_count / fps,
        )
    # フレームを削除
    shutil.rmtree(frames_dir, ignore_errors=True)


# ---------------------------------------------------------------------------
# メイン録画関数
# ---------------------------------------------------------------------------


def record_slides(
    html_path: str,
    output_dir: str,
    num_slides: int,
    nav_key: str = "ArrowRight",
    wait: float = 2.0,
    animation_wait: float = 3.0,
    width: int = 1920,
    height: int = 1080,
    *,
    progress_callback: Callable[[int, int, Path], None] | None = None,
) -> list[Path]:
    """HTMLアニメーション紙芝居を録画し、スライドごとのWebMクリップを生成する.

    自動再生タイムライン型HTMLに対応:
    1. ページを読み込み、アニメーション再生を開始
    2. スライドカウンター（"NN / MM"）をリアルタイム監視
    3. スクリーンショットを連写しながら、スライド番号が変わったら区切り
    4. 区切りごとのフレーム群をFFmpegでWebM動画に変換

    従来のキー操作型HTMLにもフォールバック対応。スライドカウンターが
    検出できない場合は animation_wait 秒固定でキー操作方式に切り替える。

    Args:
        html_path: HTMLファイルのパス.
        output_dir: クリップの出力先ディレクトリ.
        num_slides: スライド数.
        nav_key: スライド遷移に使うキー（フォールバック時）.
        wait: 初回読み込み待機時間（秒）.
        animation_wait: フォールバック時の各スライド録画時間（秒）.
            タイムライン型では無視される（自動検出）.
        width: ビューポート幅.
        height: ビューポート高さ.
        progress_callback: 進捗報告用コールバック。(current, total, path) を渡す.

    Returns:
        生成されたクリップファイルのパスリスト.

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

    file_url = html_file.as_uri()
    clip_paths: list[Path] = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={"width": width, "height": height},
        )
        page = context.new_page()

        # HTMLを読み込む
        page.goto(file_url)
        page.wait_for_load_state("networkidle")
        time.sleep(wait)

        # タイムライン型かどうかを判定: スライドカウンターの存在を確認
        initial_slide = page.evaluate(_JS_GET_SLIDE_NUMBER)

        if initial_slide is not None:
            # タイムライン型: スライドカウンター監視方式
            log.info(
                "タイムライン型HTML検出 (スライド%d/%d)。"
                "自動再生を監視しながら録画します (%dfps)",
                initial_slide,
                num_slides,
                _DEFAULT_FPS,
            )
            clip_paths = _record_timeline_mode(
                page, output, num_slides, width, height,
                progress_callback=progress_callback,
            )
        else:
            # キー操作型: 従来方式にフォールバック
            log.info(
                "キー操作型HTML検出。ArrowRight方式で録画します "
                "(%dfps, %.1fs/スライド)",
                _DEFAULT_FPS,
                animation_wait,
            )
            clip_paths = _record_keypress_mode(
                page, output, num_slides, nav_key, animation_wait,
                width, height, progress_callback=progress_callback,
            )

        page.close()
        context.close()
        browser.close()

    return clip_paths


def _record_timeline_mode(
    page,
    output: Path,
    num_slides: int,
    width: int,
    height: int,
    *,
    fps: int = _DEFAULT_FPS,
    progress_callback: Callable[[int, int, Path], None] | None = None,
) -> list[Path]:
    """タイムライン型HTML: スライドカウンター監視で自動分割録画する."""
    clip_paths: list[Path] = []
    frame_interval = 1.0 / fps

    # 先頭に戻す
    page.evaluate(_JS_RETURN_TO_START)
    time.sleep(0.5)

    current_slide = page.evaluate(_JS_GET_SLIDE_NUMBER) or 1
    log.info("  録画開始: スライド %d", current_slide)

    # 現在のスライド用のフレームディレクトリ
    frames_dir = output / f"_frames_slide_{current_slide}"
    frames_dir.mkdir(parents=True, exist_ok=True)
    frame_count = 0

    if progress_callback is not None:
        clip_path = output / f"slide_{current_slide}.webm"
        progress_callback(current_slide, num_slides, clip_path)

    # 全スライドが完了するか、タイムアウト（5分）まで録画
    max_duration = 300.0
    start_time = time.monotonic()
    last_frame_time = start_time

    while time.monotonic() - start_time < max_duration:
        # スクリーンショット撮影
        frame_path = frames_dir / f"frame_{frame_count:06d}.png"
        page.screenshot(path=str(frame_path))
        frame_count += 1

        # スライド番号を確認
        detected_slide = page.evaluate(_JS_GET_SLIDE_NUMBER)

        if detected_slide is not None and detected_slide != current_slide:
            # スライドが変わった → 今までのフレームをクリップに変換
            clip_path = output / f"slide_{current_slide}.webm"
            _save_current_frames_as_clip(
                frames_dir, frame_count, clip_path, fps, width, height,
            )
            clip_paths.append(clip_path)

            # 次のスライドに切り替え
            current_slide = detected_slide
            log.info("  スライド %d/%d 録画中...", current_slide, num_slides)

            if progress_callback is not None:
                next_clip = output / f"slide_{current_slide}.webm"
                progress_callback(current_slide, num_slides, next_clip)

            # 新しいフレームディレクトリ
            frames_dir = output / f"_frames_slide_{current_slide}"
            frames_dir.mkdir(parents=True, exist_ok=True)
            frame_count = 0

            # 最後のスライドが完了していたら終了
            if len(clip_paths) >= num_slides:
                break

        # 全スライド到達チェック（最終スライドの録画完了を待つ）
        if current_slide == num_slides and frame_count > 0:
            # 最終スライドは少なくとも3秒間録画してから判断
            if frame_count >= fps * 3:
                # 最終スライドのカウンターがまだ同じなら完了と判断
                final_check = page.evaluate(_JS_GET_SLIDE_NUMBER)
                if final_check is None or final_check != current_slide:
                    # アニメーション終了（カウンターが消えた）
                    break

        # 次のフレームタイミングまで待機
        now = time.monotonic()
        target = last_frame_time + frame_interval
        sleep_time = target - now
        if sleep_time > 0:
            time.sleep(sleep_time)
        last_frame_time = time.monotonic()

    # 最後のスライドの残りフレームを変換
    if frame_count > 0:
        clip_path = output / f"slide_{current_slide}.webm"
        _save_current_frames_as_clip(
            frames_dir, frame_count, clip_path, fps, width, height,
        )
        clip_paths.append(clip_path)

    # 残ったフレームディレクトリを掃除
    for d in output.glob("_frames_slide_*"):
        shutil.rmtree(d, ignore_errors=True)

    log.info("  録画完了: %d クリップ生成", len(clip_paths))
    return clip_paths


def _record_keypress_mode(
    page,
    output: Path,
    num_slides: int,
    nav_key: str,
    animation_wait: float,
    width: int,
    height: int,
    *,
    fps: int = _DEFAULT_FPS,
    progress_callback: Callable[[int, int, Path], None] | None = None,
) -> list[Path]:
    """キー操作型HTML: ArrowRightで遷移しながら固定時間録画する（フォールバック）."""
    clip_paths: list[Path] = []

    for i in range(1, num_slides + 1):
        clip_path = output / f"slide_{i}.webm"
        frames_dir = output / f"_frames_slide_{i}"
        frames_dir.mkdir(parents=True, exist_ok=True)

        log.info("  スライド %d/%d 録画中...", i, num_slides)
        if progress_callback is not None:
            progress_callback(i, num_slides, clip_path)

        # スライド1以外: キー操作で次のスライドへ遷移
        if i > 1:
            page.keyboard.press(nav_key)
            time.sleep(0.5)

        # スクリーンショット連写
        frame_interval = 1.0 / fps
        frame_count = 0
        start_time = time.monotonic()
        end_time = start_time + animation_wait

        while time.monotonic() < end_time:
            frame_path = frames_dir / f"frame_{frame_count:06d}.png"
            page.screenshot(path=str(frame_path))
            frame_count += 1

            elapsed = time.monotonic() - start_time
            next_frame_time = frame_count * frame_interval
            sleep_time = next_frame_time - elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)

        # フレーム → 動画変換
        _save_current_frames_as_clip(
            frames_dir, frame_count, clip_path, fps, width, height,
        )
        clip_paths.append(clip_path)

    # 残ったフレームディレクトリを掃除
    for d in output.glob("_frames_slide_*"):
        shutil.rmtree(d, ignore_errors=True)

    return clip_paths


# ---------------------------------------------------------------------------
# フル録画関数（1本の連続動画）
# ---------------------------------------------------------------------------


def record_full_presentation(
    html_path: str,
    output_dir: str,
    num_slides: int,
    nav_key: str = "ArrowRight",
    wait: float = 2.0,
    animation_wait: float = 3.0,
    width: int = 1920,
    height: int = 1080,
    *,
    progress_callback: Callable[[int, int, Path], None] | None = None,
) -> tuple[Path, list[float]]:
    """HTML全体を1本の連続動画として録画し、各スライドのタイムスタンプを返す.

    Playwright内蔵の動画録画機能を使用して、ブラウザ画面全体を1本の動画として
    録画する。スライドごとの分割は行わず、各スライドの表示開始タイムスタンプを
    記録して返す。

    生成される動画はつなぎ目のない滑らかな映像になる。後から overlay_narration()
    でTTS音声を正しいタイミングで重ねることで、最終動画を生成する。

    Args:
        html_path: HTMLファイルのパス.
        output_dir: 出力先ディレクトリ.
        num_slides: スライド数.
        nav_key: スライド遷移に使うキー（キー操作型の場合）.
        wait: 初回読み込み待機時間（秒）.
        animation_wait: 各スライドのアニメーション再生時間（秒）.
        width: ビューポート幅.
        height: ビューポート高さ.
        progress_callback: 進捗報告用コールバック。(current, total, path) を渡す.

    Returns:
        (video_path, timestamps): 動画ファイルパスと各スライドの開始秒リスト.

    Raises:
        FileNotFoundError: HTMLファイルが存在しない場合.
        RuntimeError: Playwright がインストールされていない / 録画失敗.
    """
    import json as _json

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

    file_url = html_file.as_uri()
    video_tmpdir = output / "_video_recording"
    video_tmpdir.mkdir(exist_ok=True)

    timestamps: list[float] = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={"width": width, "height": height},
            record_video_dir=str(video_tmpdir),
            record_video_size={"width": width, "height": height},
        )
        page = context.new_page()

        page.goto(file_url)
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(int(wait * 1000))

        # タイムライン型かキー操作型かを判定
        initial_slide = page.evaluate(_JS_GET_SLIDE_NUMBER)
        start = time.monotonic()

        if initial_slide is not None:
            # タイムライン型: スライドカウンター監視
            page.evaluate(_JS_RETURN_TO_START)
            page.wait_for_timeout(500)
            start = time.monotonic()
            timestamps = [0.0]
            current_slide = 1

            log.info(
                "フル録画開始（タイムライン型, %dスライド）", num_slides,
            )
            if progress_callback:
                progress_callback(1, num_slides, output / "full_presentation.webm")

            max_wait = 300.0
            while current_slide < num_slides and time.monotonic() - start < max_wait:
                page.wait_for_timeout(100)
                detected = page.evaluate(_JS_GET_SLIDE_NUMBER)
                if detected and detected != current_slide:
                    timestamps.append(time.monotonic() - start)
                    current_slide = detected
                    log.info(
                        "  スライド %d/%d 検出 (%.1fs)",
                        current_slide, num_slides, timestamps[-1],
                    )
                    if progress_callback:
                        progress_callback(
                            current_slide, num_slides,
                            output / "full_presentation.webm",
                        )

            # 最終スライドの余白録画（ナレーション用）
            page.wait_for_timeout(int(animation_wait * 1000 * 3))
        else:
            # キー操作型: 手動遷移
            timestamps = [0.0]
            log.info(
                "フル録画開始（キー操作型, %dスライド, %.1fs/スライド）",
                num_slides, animation_wait,
            )
            if progress_callback:
                progress_callback(1, num_slides, output / "full_presentation.webm")

            for i in range(1, num_slides):
                page.wait_for_timeout(int(animation_wait * 1000))
                page.keyboard.press(nav_key)
                page.wait_for_timeout(500)
                timestamps.append(time.monotonic() - start)
                log.info(
                    "  スライド %d/%d (%.1fs)", i + 1, num_slides, timestamps[-1],
                )
                if progress_callback:
                    progress_callback(
                        i + 1, num_slides, output / "full_presentation.webm",
                    )

            # 最終スライドの余白録画（ナレーション用）
            page.wait_for_timeout(int(animation_wait * 1000 * 3))

        page.close()
        context.close()
        browser.close()

    # 録画ファイルを取得してリネーム
    final_path = output / "full_presentation.webm"
    video_files = list(video_tmpdir.glob("*.webm"))
    if not video_files:
        shutil.rmtree(video_tmpdir, ignore_errors=True)
        msg = "動画ファイルが生成されませんでした"
        raise RuntimeError(msg)

    shutil.move(str(video_files[0]), str(final_path))
    shutil.rmtree(video_tmpdir, ignore_errors=True)

    # タイムスタンプをJSON保存
    ts_file = output / "timestamps.json"
    ts_file.write_text(
        _json.dumps(
            {"timestamps": timestamps, "num_slides": num_slides},
            indent=2,
        ),
        encoding="utf-8",
    )

    log.info("フル録画完了: %s (%dスライド)", final_path.name, len(timestamps))
    return final_path, timestamps


def main() -> None:
    """CLI エントリーポイント."""
    parser = argparse.ArgumentParser(
        description="HTMLアニメーション紙芝居を録画してスライドごとにクリップ分割する",
    )
    parser.add_argument(
        "html_path",
        help="HTMLファイルのパス",
    )
    parser.add_argument(
        "--slides",
        type=int,
        default=14,
        help="スライド数 (デフォルト: 14)",
    )
    parser.add_argument(
        "--output",
        default="output/clips",
        help="出力ディレクトリ (デフォルト: output/clips)",
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
        "--animation-wait",
        type=float,
        default=3.0,
        help="各スライドのアニメーション再生待ち時間（秒） (デフォルト: 3.0)",
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

    logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")

    print("HTMLアニメーション録画ツール")
    print(f"  入力: {args.html_path}")
    print(f"  出力: {args.output}")
    print(f"  スライド数: {args.slides}")
    print(f"  遷移キー: {args.key}")
    print(f"  初回待機: {args.wait}秒")
    print(f"  アニメーション待機: {args.animation_wait}秒")
    print()

    try:
        paths = record_slides(
            html_path=args.html_path,
            output_dir=args.output,
            num_slides=args.slides,
            nav_key=args.key,
            wait=args.wait,
            animation_wait=args.animation_wait,
            width=args.width,
            height=args.height,
        )
        print(f"\n完了: {len(paths)}個のクリップを {args.output} に保存しました")
    except FileNotFoundError as e:
        print(f"エラー: {e}", file=sys.stderr)
        sys.exit(1)
    except RuntimeError as e:
        print(f"エラー: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
