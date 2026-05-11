#!/usr/bin/env python3
"""
html_to_video.py のユニットテスト

実行方法:
    python -m pytest test_html_to_video.py -v
    python test_html_to_video.py  (pytest不要のスタンドアロン実行)
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

# テスト対象モジュールをインポート
sys.path.insert(0, str(Path(__file__).parent))
from html_to_video import (
    _DEFAULT_FPS,
    _frames_to_video,
    _record_keypress_mode,
    _record_timeline_mode,
    _run_ffmpeg,
    _save_current_frames_as_clip,
    record_slides,
)


# ---------------------------------------------------------------------------
# 1. _run_ffmpeg のテスト
# ---------------------------------------------------------------------------


class TestRunFfmpeg(unittest.TestCase):
    """_run_ffmpeg 関数のテスト."""

    @patch("html_to_video.subprocess.run")
    def test_normal_execution_calls_subprocess(self, mock_run):
        """正常系: subprocessが呼ばれること."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_run.return_value = mock_result

        _run_ffmpeg(["-i", "input.mp4", "output.mp4"], "テスト変換")

        mock_run.assert_called_once()
        cmd = mock_run.call_args[0][0]
        self.assertEqual(cmd[0], "ffmpeg")
        self.assertIn("-i", cmd)
        self.assertIn("input.mp4", cmd)

    @patch("html_to_video.subprocess.run")
    def test_ffmpeg_prepends_standard_flags(self, mock_run):
        """ffmpegコマンドに -y -hide_banner -loglevel warning が先頭に付くこと."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_run.return_value = mock_result

        _run_ffmpeg(["-i", "in.mp4", "out.mp4"], "desc")

        cmd = mock_run.call_args[0][0]
        self.assertEqual(cmd[:5], ["ffmpeg", "-y", "-hide_banner", "-loglevel", "warning"])

    @patch("html_to_video.sys.exit")
    @patch("html_to_video.subprocess.run", side_effect=FileNotFoundError)
    def test_ffmpeg_not_found_calls_sys_exit(self, mock_run, mock_exit):
        """ffmpegが見つからない場合にsys.exit(1)が呼ばれること."""
        _run_ffmpeg([], "テスト")
        mock_exit.assert_called_once_with(1)

    @patch("html_to_video.subprocess.run")
    def test_nonzero_returncode_raises_runtime_error(self, mock_run):
        """ffmpegが非ゼロ終了コードを返した場合にRuntimeErrorが発生すること."""
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = "Conversion failed"
        mock_run.return_value = mock_result

        with self.assertRaises(RuntimeError) as ctx:
            _run_ffmpeg(["-i", "bad.mp4", "out.mp4"], "変換失敗テスト")
        self.assertIn("FFmpeg failed", str(ctx.exception))

    @patch("html_to_video.subprocess.run")
    def test_no_shell_true(self, mock_run):
        """subprocess.run に shell=True が渡されないこと."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_run.return_value = mock_result

        _run_ffmpeg(["dummy"], "テスト")

        _, kwargs = mock_run.call_args
        self.assertNotEqual(kwargs.get("shell"), True)


# ---------------------------------------------------------------------------
# 2. _frames_to_video のテスト
# ---------------------------------------------------------------------------


class TestFramesToVideo(unittest.TestCase):
    """_frames_to_video 関数のテスト."""

    @patch("html_to_video._run_ffmpeg")
    def test_correct_framerate_argument(self, mock_ffmpeg):
        """FFmpegに正しいframerateが渡されること."""
        frames_dir = Path("/tmp/frames")
        output = Path("/tmp/out.webm")

        _frames_to_video(frames_dir, output, fps=20)

        mock_ffmpeg.assert_called_once()
        args = mock_ffmpeg.call_args[0][0]
        idx = args.index("-framerate")
        self.assertEqual(args[idx + 1], "20")

    @patch("html_to_video._run_ffmpeg")
    def test_input_pattern_uses_frame_format(self, mock_ffmpeg):
        """入力パスに frame_%06d.png パターンが使われること."""
        frames_dir = Path("/tmp/frames")
        output = Path("/tmp/out.webm")

        _frames_to_video(frames_dir, output)

        args = mock_ffmpeg.call_args[0][0]
        idx = args.index("-i")
        self.assertIn("frame_%06d.png", args[idx + 1])

    @patch("html_to_video._run_ffmpeg")
    def test_output_codec_is_vp9(self, mock_ffmpeg):
        """出力コーデックが libvpx-vp9 であること."""
        _frames_to_video(Path("/tmp/f"), Path("/tmp/out.webm"))
        args = mock_ffmpeg.call_args[0][0]
        self.assertIn("libvpx-vp9", args)

    @patch("html_to_video._run_ffmpeg")
    def test_scale_filter_uses_width_height(self, mock_ffmpeg):
        """scaleフィルターに指定した width x height が使われること."""
        _frames_to_video(Path("/tmp/f"), Path("/tmp/out.webm"), width=1280, height=720)
        args = mock_ffmpeg.call_args[0][0]
        vf_idx = args.index("-vf")
        self.assertIn("1280:720", args[vf_idx + 1])

    @patch("html_to_video._run_ffmpeg")
    def test_default_fps_is_used(self, mock_ffmpeg):
        """FPS未指定時にデフォルト値 _DEFAULT_FPS が使われること."""
        _frames_to_video(Path("/tmp/f"), Path("/tmp/out.webm"))
        args = mock_ffmpeg.call_args[0][0]
        idx = args.index("-framerate")
        self.assertEqual(args[idx + 1], str(_DEFAULT_FPS))


# ---------------------------------------------------------------------------
# 3. _save_current_frames_as_clip のテスト
# ---------------------------------------------------------------------------


class TestSaveCurrentFramesAsClip(unittest.TestCase):
    """_save_current_frames_as_clip 関数のテスト."""

    @patch("html_to_video.shutil.rmtree")
    @patch("html_to_video._frames_to_video")
    def test_calls_frames_to_video_when_frames_exist(self, mock_f2v, mock_rmtree):
        """frame_count > 0 の場合 _frames_to_video が呼ばれること."""
        frames_dir = Path("/tmp/frames_slide_1")
        clip_path = Path("/tmp/slide_1.webm")

        _save_current_frames_as_clip(frames_dir, 30, clip_path, fps=15, width=1920, height=1080)

        mock_f2v.assert_called_once_with(frames_dir, clip_path, fps=15, width=1920, height=1080)

    @patch("html_to_video.shutil.rmtree")
    @patch("html_to_video._frames_to_video")
    def test_skips_frames_to_video_when_no_frames(self, mock_f2v, mock_rmtree):
        """frame_count == 0 の場合 _frames_to_video が呼ばれないこと."""
        _save_current_frames_as_clip(
            Path("/tmp/frames"), 0, Path("/tmp/out.webm"), fps=15, width=1920, height=1080
        )
        mock_f2v.assert_not_called()

    @patch("html_to_video.shutil.rmtree")
    @patch("html_to_video._frames_to_video")
    def test_always_removes_frames_dir(self, mock_f2v, mock_rmtree):
        """frame_count の値に関わらず frames_dir が削除されること."""
        frames_dir = Path("/tmp/frames_slide_1")

        _save_current_frames_as_clip(frames_dir, 0, Path("/tmp/out.webm"), fps=15, width=1920, height=1080)

        mock_rmtree.assert_called_once_with(frames_dir, ignore_errors=True)

    @patch("html_to_video.shutil.rmtree")
    @patch("html_to_video._frames_to_video")
    def test_removes_dir_even_after_video_creation(self, mock_f2v, mock_rmtree):
        """動画生成後もディレクトリが削除されること."""
        frames_dir = Path("/tmp/frames_slide_2")

        _save_current_frames_as_clip(frames_dir, 10, Path("/tmp/out.webm"), fps=15, width=1920, height=1080)

        # _frames_to_video が呼ばれた後に rmtree が呼ばれること
        mock_f2v.assert_called_once()
        mock_rmtree.assert_called_once_with(frames_dir, ignore_errors=True)


# ---------------------------------------------------------------------------
# 4. record_slides のテスト
# ---------------------------------------------------------------------------


class TestRecordSlides(unittest.TestCase):
    """record_slides 関数のテスト."""

    def test_file_not_found_raises(self):
        """存在しないHTMLファイルを指定した場合にFileNotFoundErrorが発生すること."""
        with self.assertRaises(FileNotFoundError) as ctx:
            record_slides(
                html_path="/nonexistent/path/slide.html",
                output_dir="/tmp/out",
                num_slides=3,
            )
        self.assertIn("HTMLファイルが見つかりません", str(ctx.exception))

    def test_playwright_not_installed_raises_runtime_error(self):
        """playwrightがインストールされていない場合にRuntimeErrorが発生すること."""
        with tempfile.NamedTemporaryFile(suffix=".html", delete=False) as f:
            f.write(b"<html></html>")
            html_path = f.name

        try:
            import builtins
            original_import = builtins.__import__

            def mock_import(name, *args, **kwargs):
                if name == "playwright.sync_api":
                    raise ImportError("playwright not installed")
                return original_import(name, *args, **kwargs)

            with patch("builtins.__import__", side_effect=mock_import):
                with self.assertRaises(RuntimeError) as ctx:
                    record_slides(
                        html_path=html_path,
                        output_dir="/tmp/out",
                        num_slides=3,
                    )
            self.assertIn("playwright", str(ctx.exception).lower())
        finally:
            Path(html_path).unlink(missing_ok=True)

    @patch("html_to_video._record_timeline_mode")
    @patch("html_to_video._record_keypress_mode")
    def test_timeline_mode_selected_when_slide_counter_detected(
        self, mock_keypress, mock_timeline
    ):
        """スライドカウンターが検出された場合にタイムラインモードが選択されること."""
        mock_timeline.return_value = []

        with tempfile.NamedTemporaryFile(suffix=".html", delete=False) as f:
            f.write(b"<html></html>")
            html_path = f.name

        try:
            mock_page = MagicMock()
            mock_page.evaluate.side_effect = [1]  # initial_slide = 1

            mock_context = MagicMock()
            mock_context.new_page.return_value = mock_page

            mock_browser = MagicMock()
            mock_browser.new_context.return_value = mock_context

            mock_playwright_instance = MagicMock()
            mock_playwright_instance.chromium.launch.return_value = mock_browser

            mock_sync_playwright = MagicMock()
            mock_sync_playwright.return_value.__enter__ = MagicMock(
                return_value=mock_playwright_instance
            )
            mock_sync_playwright.return_value.__exit__ = MagicMock(return_value=False)

            with patch("html_to_video.sync_playwright", mock_sync_playwright, create=True):
                # sync_playwright をモジュールレベルで差し替える
                with patch.dict("sys.modules", {}):
                    pass

            # playwright をモックしてインポートをバイパスする別の方法
            mock_pw_module = MagicMock()
            mock_pw_module.sync_playwright = mock_sync_playwright

            with patch.dict("sys.modules", {"playwright.sync_api": mock_pw_module}):
                with tempfile.TemporaryDirectory() as tmpdir:
                    record_slides(
                        html_path=html_path,
                        output_dir=tmpdir,
                        num_slides=3,
                    )

            mock_timeline.assert_called_once()
            mock_keypress.assert_not_called()
        finally:
            Path(html_path).unlink(missing_ok=True)

    @patch("html_to_video._record_timeline_mode")
    @patch("html_to_video._record_keypress_mode")
    def test_keypress_mode_selected_when_no_slide_counter(
        self, mock_keypress, mock_timeline
    ):
        """スライドカウンターが検出されない場合にキー操作モードが選択されること."""
        mock_keypress.return_value = []

        with tempfile.NamedTemporaryFile(suffix=".html", delete=False) as f:
            f.write(b"<html></html>")
            html_path = f.name

        try:
            mock_page = MagicMock()
            mock_page.evaluate.return_value = None  # スライドカウンター未検出

            mock_context = MagicMock()
            mock_context.new_page.return_value = mock_page

            mock_browser = MagicMock()
            mock_browser.new_context.return_value = mock_context

            mock_playwright_instance = MagicMock()
            mock_playwright_instance.chromium.launch.return_value = mock_browser

            mock_sync_playwright = MagicMock()
            mock_sync_playwright.return_value.__enter__ = MagicMock(
                return_value=mock_playwright_instance
            )
            mock_sync_playwright.return_value.__exit__ = MagicMock(return_value=False)

            mock_pw_module = MagicMock()
            mock_pw_module.sync_playwright = mock_sync_playwright

            with patch.dict("sys.modules", {"playwright.sync_api": mock_pw_module}):
                with tempfile.TemporaryDirectory() as tmpdir:
                    record_slides(
                        html_path=html_path,
                        output_dir=tmpdir,
                        num_slides=3,
                    )

            mock_timeline.assert_not_called()
            mock_keypress.assert_called_once()
        finally:
            Path(html_path).unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# 5. _record_timeline_mode のテスト
# ---------------------------------------------------------------------------


class TestRecordTimelineMode(unittest.TestCase):
    """_record_timeline_mode 関数のテスト."""

    def _make_page_mock(
        self,
        slide_sequence: list[int | None],
        screenshot_succeeds: bool = True,
    ) -> MagicMock:
        """スライド番号の変化シーケンスをシミュレートするページモック."""
        page = MagicMock()
        call_count = [0]

        def fake_evaluate(js):
            idx = min(call_count[0], len(slide_sequence) - 1)
            result = slide_sequence[idx]
            call_count[0] += 1
            return result

        page.evaluate.side_effect = fake_evaluate
        return page

    @patch("html_to_video._save_current_frames_as_clip")
    @patch("html_to_video.time.sleep")
    @patch("html_to_video.time.monotonic")
    def test_returns_clip_paths_list(self, mock_time, mock_sleep, mock_save):
        """クリップパスのリストが返されること."""
        # 時刻を制御: タイムアウトしないように start_time より小さい elapsed を返す
        # _record_timeline_mode では max_duration=300 で while ループする
        # num_slides=1 かつ 1フレーム撮影 → len(clip_paths) >= 1 で break する
        # 単純化: 時刻を固定してタイムアウトが起きないようにし、スライド遷移を模擬

        # time.monotonic の呼ばれ順序:
        # 1. start_time = time.monotonic()  -> 0.0
        # 2. while time.monotonic() - start_time < 300  -> 0.0 (ループ1回目)
        # 3. now = time.monotonic()  -> 0.0
        # 4. last_frame_time = time.monotonic()  -> 0.0
        # スライドが変わったら break するのでループは短い
        mock_time.side_effect = [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]

        with tempfile.TemporaryDirectory() as tmpdir:
            output = Path(tmpdir)
            page = MagicMock()

            # evaluate の呼ばれ順:
            # 1. _JS_RETURN_TO_START: page.evaluate(_JS_RETURN_TO_START)
            # 2. current_slide: page.evaluate(_JS_GET_SLIDE_NUMBER) or 1 -> 1
            # 3. ループ内: detected_slide -> 2 (スライドが変わった)
            page.evaluate.side_effect = [
                True,   # _JS_RETURN_TO_START
                1,      # current_slide の初期値
                2,      # detected_slide がスライド2に変わった
            ]

            result = _record_timeline_mode(
                page, output, num_slides=1, width=1920, height=1080
            )

            # 戻り値はリスト
            self.assertIsInstance(result, list)

    @patch("html_to_video._save_current_frames_as_clip")
    @patch("html_to_video.time.sleep")
    @patch("html_to_video.time.monotonic")
    def test_progress_callback_called(self, mock_time, mock_sleep, mock_save):
        """progress_callbackが呼ばれること."""
        mock_time.side_effect = [0.0] * 20

        with tempfile.TemporaryDirectory() as tmpdir:
            output = Path(tmpdir)
            page = MagicMock()
            # 評価順:
            # 1. _JS_RETURN_TO_START -> True
            # 2. current_slide の初期値 -> 1
            # 3. ループ内 detected_slide -> 2 (スライド変化: clip生成 + len>=num_slides でbreak)
            page.evaluate.side_effect = [
                True,  # _JS_RETURN_TO_START
                1,     # current_slide の初期値
                2,     # detected_slide がスライド2へ変化 → clip生成 → break
            ]

            callback = MagicMock()

            _record_timeline_mode(
                page, output, num_slides=1, width=1920, height=1080,
                progress_callback=callback,
            )

            # 初回のprogress_callbackが呼ばれること
            callback.assert_called()

    @patch("html_to_video.shutil.rmtree")
    @patch("html_to_video._frames_to_video")
    @patch("html_to_video.time.sleep")
    @patch("html_to_video.time.monotonic")
    def test_cleanup_frames_dirs_at_end(self, mock_time, mock_sleep, mock_f2v, mock_rmtree):
        """録画終了後に _frames_slide_* ディレクトリが削除されること."""
        mock_time.side_effect = [0.0] * 30

        with tempfile.TemporaryDirectory() as tmpdir:
            output = Path(tmpdir)
            # 残存フレームディレクトリを作成
            leftover = output / "_frames_slide_99"
            leftover.mkdir()

            page = MagicMock()
            page.evaluate.side_effect = [
                True,  # _JS_RETURN_TO_START
                1,     # current_slide
                2,     # detected_slide -> スライド2に切り替わり
                None,  # final_check (ループ後の最終確認)
                None,  # 最終スライドチェック
            ]

            _record_timeline_mode(
                page, output, num_slides=1, width=1920, height=1080
            )

            # クリーンアップが実行されていること（rmtreeが呼ばれていること）
            self.assertTrue(mock_rmtree.called)


# ---------------------------------------------------------------------------
# 6. _record_keypress_mode のテスト
# ---------------------------------------------------------------------------


class TestRecordKeypressMode(unittest.TestCase):
    """_record_keypress_mode 関数のテスト."""

    @patch("html_to_video._save_current_frames_as_clip")
    @patch("html_to_video.shutil.rmtree")
    @patch("html_to_video.time.sleep")
    @patch("html_to_video.time.monotonic")
    def test_returns_clip_paths_for_each_slide(
        self, mock_time, mock_sleep, mock_rmtree, mock_save
    ):
        """スライド数分のクリップパスが返されること."""
        # num_slides=3 の場合、3つのクリップパスが返される
        # time.monotonic: start_time, while condition, now (フレームタイム計算)
        # 各スライドに最低3回の monotonic 呼び出しが必要
        # animation_wait=0.1秒に設定して1ループだけ回るように制御
        call_seq = []
        for i in range(3):
            # start_time, end_time計算用, while loop check(終了), 追加の呼び出し
            call_seq.extend([float(i), float(i) + 0.1, float(i) + 0.2])
        mock_time.side_effect = call_seq + [999.0] * 20

        with tempfile.TemporaryDirectory() as tmpdir:
            output = Path(tmpdir)
            page = MagicMock()

            result = _record_keypress_mode(
                page, output, num_slides=3, nav_key="ArrowRight",
                animation_wait=0.001,  # 極めて短い時間で各スライドを終わらせる
                width=1920, height=1080,
            )

            self.assertEqual(len(result), 3)
            for path in result:
                self.assertIsInstance(path, Path)
                self.assertTrue(str(path).endswith(".webm"))

    @patch("html_to_video._save_current_frames_as_clip")
    @patch("html_to_video.shutil.rmtree")
    @patch("html_to_video.time.sleep")
    @patch("html_to_video.time.monotonic")
    def test_keyboard_press_not_called_for_first_slide(
        self, mock_time, mock_sleep, mock_rmtree, mock_save
    ):
        """スライド1ではキー操作が行われないこと."""
        mock_time.side_effect = [0.0, 0.01, 0.02] + [999.0] * 10

        with tempfile.TemporaryDirectory() as tmpdir:
            output = Path(tmpdir)
            page = MagicMock()

            _record_keypress_mode(
                page, output, num_slides=1, nav_key="ArrowRight",
                animation_wait=0.001,
                width=1920, height=1080,
            )

            page.keyboard.press.assert_not_called()

    @patch("html_to_video._save_current_frames_as_clip")
    @patch("html_to_video.shutil.rmtree")
    @patch("html_to_video.time.sleep")
    @patch("html_to_video.time.monotonic")
    def test_keyboard_press_called_for_subsequent_slides(
        self, mock_time, mock_sleep, mock_rmtree, mock_save
    ):
        """スライド2以降でキー操作が行われること."""
        # スライド2枚: slide1(3回), slide2(3回) + 余裕
        mock_time.side_effect = [0.0, 0.01, 0.02, 1.0, 1.01, 1.02] + [999.0] * 10

        with tempfile.TemporaryDirectory() as tmpdir:
            output = Path(tmpdir)
            page = MagicMock()

            _record_keypress_mode(
                page, output, num_slides=2, nav_key="ArrowRight",
                animation_wait=0.001,
                width=1920, height=1080,
            )

            page.keyboard.press.assert_called_once_with("ArrowRight")

    @patch("html_to_video._save_current_frames_as_clip")
    @patch("html_to_video.shutil.rmtree")
    @patch("html_to_video.time.sleep")
    @patch("html_to_video.time.monotonic")
    def test_progress_callback_called_for_each_slide(
        self, mock_time, mock_sleep, mock_rmtree, mock_save
    ):
        """各スライドでprogress_callbackが呼ばれること."""
        mock_time.side_effect = [0.0, 0.01, 0.02, 1.0, 1.01, 1.02, 2.0, 2.01, 2.02] + [999.0] * 10

        with tempfile.TemporaryDirectory() as tmpdir:
            output = Path(tmpdir)
            page = MagicMock()
            callback = MagicMock()

            _record_keypress_mode(
                page, output, num_slides=3, nav_key="ArrowRight",
                animation_wait=0.001,
                width=1920, height=1080,
                progress_callback=callback,
            )

            # 3スライド分呼ばれること
            self.assertEqual(callback.call_count, 3)

    @patch("html_to_video._save_current_frames_as_clip")
    @patch("html_to_video.shutil.rmtree")
    @patch("html_to_video.time.sleep")
    @patch("html_to_video.time.monotonic")
    def test_clip_paths_named_correctly(
        self, mock_time, mock_sleep, mock_rmtree, mock_save
    ):
        """生成されるクリップパスが slide_{N}.webm の形式であること."""
        mock_time.side_effect = [0.0, 0.01, 0.02] + [999.0] * 10

        with tempfile.TemporaryDirectory() as tmpdir:
            output = Path(tmpdir)
            page = MagicMock()

            result = _record_keypress_mode(
                page, output, num_slides=1, nav_key="Space",
                animation_wait=0.001,
                width=1280, height=720,
            )

            self.assertEqual(result[0].name, "slide_1.webm")


# ---------------------------------------------------------------------------
# 7. セキュリティチェック
# ---------------------------------------------------------------------------


class TestSecurityChecks(unittest.TestCase):
    """セキュリティ関連のテスト."""

    def test_no_shell_true_in_subprocess_calls(self):
        """subprocess.run呼び出しにshell=Trueが使われていないこと."""
        import ast
        with open(Path(__file__).parent / "html_to_video.py", encoding="utf-8") as f:
            source = f.read()
        tree = ast.parse(source)

        shell_true_calls = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                for kw in getattr(node, "keywords", []):
                    if (
                        kw.arg == "shell"
                        and isinstance(kw.value, ast.Constant)
                        and kw.value.value is True
                    ):
                        shell_true_calls.append(node.lineno)

        self.assertEqual(
            shell_true_calls, [],
            f"shell=True が以下の行で使われています: {shell_true_calls}",
        )

    def test_subprocess_uses_list_not_string(self):
        """subprocess.runの第一引数がリスト形式であること（文字列コマンドはNG）."""
        import ast
        with open(Path(__file__).parent / "html_to_video.py", encoding="utf-8") as f:
            source = f.read()
        tree = ast.parse(source)

        string_cmd_calls = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func = node.func
                is_subprocess_run = (
                    isinstance(func, ast.Attribute)
                    and func.attr == "run"
                    and isinstance(func.value, ast.Name)
                    and func.value.id == "subprocess"
                )
                if is_subprocess_run and node.args:
                    first_arg = node.args[0]
                    if isinstance(first_arg, ast.Constant) and isinstance(
                        first_arg.value, str
                    ):
                        string_cmd_calls.append(node.lineno)

        self.assertEqual(
            string_cmd_calls, [],
            f"subprocess.runに文字列コマンドが渡されています: {string_cmd_calls}",
        )

    def test_dead_code_removed(self):
        """不要な変数 elapsed_since_start と sum(1 for _ in []) が除去されていること."""
        with open(Path(__file__).parent / "html_to_video.py", encoding="utf-8") as f:
            source = f.read()

        self.assertNotIn("elapsed_since_start", source)
        self.assertNotIn("sum(1 for _ in [])", source)

    def test_no_unused_re_import(self):
        """未使用の re モジュールがインポートされていないこと."""
        import ast
        with open(Path(__file__).parent / "html_to_video.py", encoding="utf-8") as f:
            source = f.read()
        tree = ast.parse(source)

        imported_names = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imported_names.append(alias.name)

        # re がインポートされている場合は使われているかチェック
        if "re" in imported_names:
            self.assertIn("re.", source, "re がインポートされているが使われていません")

    def test_callable_type_hint_used(self):
        """progress_callback の型ヒントが Callable を使っていること."""
        with open(Path(__file__).parent / "html_to_video.py", encoding="utf-8") as f:
            source = f.read()
        self.assertIn("Callable", source)
        self.assertNotIn("object | None", source)


# ---------------------------------------------------------------------------
# 8. app.py との統合確認
# ---------------------------------------------------------------------------


class TestAppIntegration(unittest.TestCase):
    """app.py から html_to_video のインポートが成功すること."""

    def test_record_slides_importable(self):
        """record_slides が html_to_video からインポートできること."""
        from html_to_video import record_slides as rs
        self.assertTrue(callable(rs))

    def test_module_has_expected_public_api(self):
        """html_to_video モジュールが期待する公開APIを持つこと."""
        import html_to_video as m
        self.assertTrue(hasattr(m, "record_slides"))
        self.assertTrue(callable(m.record_slides))

    def test_record_slides_signature_accepts_progress_callback(self):
        """record_slides が progress_callback キーワード引数を受け付けること."""
        import inspect
        sig = inspect.signature(record_slides)
        self.assertIn("progress_callback", sig.parameters)

    def test_record_slides_signature_has_required_params(self):
        """record_slides が html_path, output_dir, num_slides を必須引数として持つこと."""
        import inspect
        sig = inspect.signature(record_slides)
        params = sig.parameters
        self.assertIn("html_path", params)
        self.assertIn("output_dir", params)
        self.assertIn("num_slides", params)


if __name__ == "__main__":
    unittest.main(verbosity=2)
