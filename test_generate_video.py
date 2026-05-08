#!/usr/bin/env python3
"""
generate_video.py のユニットテスト

実行方法:
    python -m pytest test_generate_video.py -v
    python test_generate_video.py  (pytest不要のスタンドアロン実行)
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

# テスト対象モジュールをインポート
sys.path.insert(0, str(Path(__file__).parent))
import generate_video as gv
from generate_video import (
    BGMConfig,
    Config,
    GoogleCloudTTS,
    SlideEntry,
    TTSProvider,
    concatenate_scenes,
    generate_silence,
    get_tts_provider,
    parse_script,
    resolve_image_path,
)


# ---------------------------------------------------------------------------
# ヘルパー
# ---------------------------------------------------------------------------

def _make_config_file(data: dict, directory: str | None = None) -> Path:
    """一時config.jsonを作成してパスを返す."""
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", delete=False, encoding="utf-8",
        dir=directory,
    ) as f:
        json.dump(data, f)
        return Path(f.name)


_FULL_CONFIG_DATA = {
    "tts": {
        "provider": "google",
        "language": "ja-JP",
        "voice": "ja-JP-Neural2-C",
        "speaking_rate": 0.9,
        "pitch": 0.0,
    },
    "video": {
        "resolution": [1920, 1080],
        "fps": 30,
        "silence_duration": 3.5,
        "padding_before": 0.5,
        "padding_after": 0.5,
        "transition": "none",
        "transition_duration": 0.5,
    },
    "bgm": {
        "enabled": False,
        "file": "",
        "volume": 0.15,
    },
    "paths": {
        "images_dir": "input/images",
        "script_file": "input/script.md",
        "output_dir": "output",
    },
}

_SCRIPT_CONTENT = """\
## 紙芝居パート：セリフ

### スライド1：タイトル
**セリフ**: （無言。BGMだけ。3〜4秒の間）

---

### スライド2：足元の卵
**セリフ**: 「あなたの足元に、何かが転がっています。」

---

### スライド13：足元を見る
**セリフ**: （3秒の間の後）「あなたの足元に、まだ見えていないものがある。」

---

## 語りパート：各テーマの解説メモ

### テーマ1
語りのポイント：スライドパートより後の内容（除外対象）。
"""


# ---------------------------------------------------------------------------
# 1. データクラスのテスト
# ---------------------------------------------------------------------------

class TestSlideEntry(unittest.TestCase):
    """SlideEntry データクラスのテスト."""

    def test_silent_slide(self):
        entry = SlideEntry(number=1, title="タイトル", text="", is_silent=True)
        self.assertTrue(entry.is_silent)
        self.assertEqual(entry.text, "")

    def test_tts_slide(self):
        entry = SlideEntry(number=2, title="テスト", text="こんにちは", is_silent=False)
        self.assertFalse(entry.is_silent)
        self.assertEqual(entry.text, "こんにちは")


class TestBGMConfig(unittest.TestCase):
    """BGMConfig データクラスのデフォルト値テスト."""

    def test_defaults(self):
        bgm = BGMConfig()
        self.assertFalse(bgm.enabled)
        self.assertEqual(bgm.file, "")
        self.assertAlmostEqual(bgm.volume, 0.15)


# ---------------------------------------------------------------------------
# 2. Config.from_json のテスト
# ---------------------------------------------------------------------------

class TestConfigFromJson(unittest.TestCase):
    """Config.from_json のテスト."""

    def setUp(self):
        self._tmp_files: list[Path] = []

    def tearDown(self):
        for p in self._tmp_files:
            p.unlink(missing_ok=True)

    def _make_config(self, data: dict) -> Config:
        path = _make_config_file(data)
        self._tmp_files.append(path)
        return Config.from_json(path)

    def test_full_config(self):
        """フルconfig.jsonが正しくパースされること."""
        config = self._make_config(_FULL_CONFIG_DATA)
        self.assertEqual(config.tts_provider, "google")
        self.assertEqual(config.tts_language, "ja-JP")
        self.assertEqual(config.tts_voice, "ja-JP-Neural2-C")
        self.assertAlmostEqual(config.tts_speaking_rate, 0.9)
        self.assertAlmostEqual(config.tts_pitch, 0.0)
        self.assertEqual(config.resolution, (1920, 1080))
        self.assertEqual(config.fps, 30)
        self.assertAlmostEqual(config.silence_duration, 3.5)
        self.assertAlmostEqual(config.padding_before, 0.5)
        self.assertAlmostEqual(config.padding_after, 0.5)
        self.assertEqual(config.transition, "none")
        self.assertFalse(config.bgm.enabled)

    def test_backward_compat_missing_provider(self):
        """providerフィールドがない旧形式でもデフォルト値でパースされること."""
        old_data = {
            "tts": {
                "language": "ja-JP",
                "voice": "ja-JP-Neural2-C",
                "speaking_rate": 0.9,
                "pitch": 0.0,
            },
            "video": {
                "resolution": [1920, 1080],
                "fps": 30,
                "silence_duration": 3.5,
            },
            "paths": {
                "images_dir": "input/images",
                "script_file": "input/script.md",
                "output_dir": "output",
            },
        }
        config = self._make_config(old_data)
        self.assertEqual(config.tts_provider, "google")  # デフォルト
        self.assertEqual(config.transition, "none")       # デフォルト
        self.assertFalse(config.bgm.enabled)              # デフォルト
        self.assertEqual(config.bgm.file, "")             # デフォルト
        self.assertAlmostEqual(config.padding_before, 0.5)  # デフォルト
        self.assertAlmostEqual(config.padding_after, 0.5)   # デフォルト

    def test_backward_compat_missing_bgm_section(self):
        """bgmセクションがない旧形式でもデフォルト値でパースされること."""
        data_no_bgm = {k: v for k, v in _FULL_CONFIG_DATA.items() if k != "bgm"}
        config = self._make_config(data_no_bgm)
        self.assertFalse(config.bgm.enabled)
        self.assertEqual(config.bgm.file, "")

    def test_bgm_enabled_config(self):
        """BGM有効設定が正しく読み込まれること."""
        data = {**_FULL_CONFIG_DATA, "bgm": {"enabled": True, "file": "bgm.mp3", "volume": 0.2}}
        config = self._make_config(data)
        self.assertTrue(config.bgm.enabled)
        self.assertEqual(config.bgm.file, "bgm.mp3")
        self.assertAlmostEqual(config.bgm.volume, 0.2)

    def test_paths_are_relative_to_config_file(self):
        """パスがconfig.jsonのあるディレクトリからの相対パスで解決されること."""
        path = _make_config_file(_FULL_CONFIG_DATA)
        self._tmp_files.append(path)
        config = Config.from_json(path)
        expected_images_dir = path.parent / "input/images"
        self.assertEqual(config.images_dir, expected_images_dir)


# ---------------------------------------------------------------------------
# 3. 台本パーステスト
# ---------------------------------------------------------------------------

class TestParseScript(unittest.TestCase):
    """parse_script 関数のテスト."""

    def setUp(self):
        self._tmp_files: list[Path] = []

    def tearDown(self):
        for p in self._tmp_files:
            p.unlink(missing_ok=True)

    def _write_script(self, content: str) -> Path:
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".md", delete=False, encoding="utf-8"
        ) as f:
            f.write(content)
            path = Path(f.name)
        self._tmp_files.append(path)
        return path

    def test_slide_count_from_sample_script(self):
        """サンプル台本から正しいスライド数（14）がパースされること."""
        script_path = Path(__file__).parent / "input" / "script.md"
        if not script_path.exists():
            self.skipTest("input/script.md が見つかりません")
        entries = parse_script(script_path)
        self.assertEqual(len(entries), 14)

    def test_slide1_is_silent(self):
        """スライド1（セリフなし）がis_silent=Trueになること."""
        script_path = Path(__file__).parent / "input" / "script.md"
        if not script_path.exists():
            self.skipTest("input/script.md が見つかりません")
        entries = parse_script(script_path)
        s1 = next(e for e in entries if e.number == 1)
        self.assertTrue(s1.is_silent)
        self.assertEqual(s1.text, "")

    def test_slide13_direction_removed(self):
        """スライド13の演出指示「（3秒の間の後）」がTTS用テキストから除去されること."""
        script_path = Path(__file__).parent / "input" / "script.md"
        if not script_path.exists():
            self.skipTest("input/script.md が見つかりません")
        entries = parse_script(script_path)
        s13 = next(e for e in entries if e.number == 13)
        self.assertFalse(s13.is_silent)
        # 全角括弧が残っていないこと
        import re
        self.assertFalse(re.search(r"[（）]", s13.text))
        # セリフ本文が残っていること
        self.assertGreater(len(s13.text), 0)

    def test_no_slides_raises(self):
        """スライドが見つからない台本でValueErrorが発生すること."""
        path = self._write_script("# スライドなし\nこれはスライドではない。\n")
        with self.assertRaises(ValueError, msg="台本にスライドが見つかりません"):
            parse_script(path)

    def test_kamishibai_section_only(self):
        """語りパート以降は除外されること."""
        path = self._write_script(_SCRIPT_CONTENT)
        entries = parse_script(path)
        # 語りパートのtheme1は除外される
        numbers = [e.number for e in entries]
        self.assertIn(1, numbers)
        self.assertIn(2, numbers)
        self.assertIn(13, numbers)
        # 3スライドのみ（語りパート内のスライド見出しは含まれない）
        self.assertEqual(len(entries), 3)

    def test_silent_slide_no_serif(self):
        """セリフ括弧なしのスライドはis_silent=Trueになること."""
        content = "## 紙芝居パート\n\n### スライド1：タイトル\n**セリフ**: （無言）\n"
        path = self._write_script(content)
        entries = parse_script(path)
        self.assertEqual(len(entries), 1)
        self.assertTrue(entries[0].is_silent)

    def test_tts_slide_with_serif(self):
        """「」括弧ありのスライドはis_silent=Falseでテキストが抽出されること."""
        content = '## 紙芝居パート\n\n### スライド2：テスト\n**セリフ**: 「こんにちは世界。」\n'
        path = self._write_script(content)
        entries = parse_script(path)
        self.assertEqual(len(entries), 1)
        self.assertFalse(entries[0].is_silent)
        self.assertEqual(entries[0].text, "こんにちは世界。")

    def test_direction_instruction_removal(self):
        """全角括弧で囲まれた演出指示がテキストから除去されること."""
        content = '## 紙芝居パート\n\n### スライド5：テスト\n**セリフ**: 「（3秒の間の後）あなたの足元に。」\n'
        path = self._write_script(content)
        entries = parse_script(path)
        self.assertEqual(entries[0].text, "あなたの足元に。")

    def test_multiple_direction_instructions(self):
        """複数の演出指示が全て除去されること."""
        content = '## 紙芝居パート\n\n### スライド3：テスト\n**セリフ**: 「（間）こんにちは（笑い声）世界。」\n'
        path = self._write_script(content)
        entries = parse_script(path)
        import re
        self.assertFalse(re.search(r"[（）]", entries[0].text))
        self.assertIn("こんにちは", entries[0].text)
        self.assertIn("世界", entries[0].text)

    def test_slide_numbers_sequential(self):
        """スライド番号が台本通りに解析されること."""
        path = self._write_script(_SCRIPT_CONTENT)
        entries = parse_script(path)
        numbers = [e.number for e in entries]
        self.assertEqual(numbers, [1, 2, 13])


# ---------------------------------------------------------------------------
# 4. TTSプロバイダーレジストリのテスト
# ---------------------------------------------------------------------------

class TestTTSProviderRegistry(unittest.TestCase):
    """get_tts_provider 関数のテスト."""

    def test_google_provider_returns_instance(self):
        """'google'プロバイダー名でGoogleCloudTTSインスタンスが返ること."""
        provider = get_tts_provider("google")
        self.assertIsInstance(provider, GoogleCloudTTS)

    def test_unknown_provider_raises_value_error(self):
        """未対応プロバイダー名でValueErrorが発生すること."""
        with self.assertRaises(ValueError) as ctx:
            get_tts_provider("nonexistent_provider")
        self.assertIn("nonexistent_provider", str(ctx.exception))
        self.assertIn("google", str(ctx.exception))

    def test_empty_provider_name_raises(self):
        """空文字のプロバイダー名でValueErrorが発生すること."""
        with self.assertRaises(ValueError):
            get_tts_provider("")

    def test_provider_is_abc_subclass(self):
        """GoogleCloudTTSがTTSProviderを継承していること."""
        self.assertTrue(issubclass(GoogleCloudTTS, TTSProvider))

    def test_provider_has_synthesize_method(self):
        """TTSProviderインスタンスがsynthesizeメソッドを持つこと."""
        provider = get_tts_provider("google")
        self.assertTrue(hasattr(provider, "synthesize"))
        self.assertTrue(callable(provider.synthesize))


# ---------------------------------------------------------------------------
# 5. 画像パス解決のテスト
# ---------------------------------------------------------------------------

class TestResolveImagePath(unittest.TestCase):
    """resolve_image_path 関数のテスト."""

    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()
        self._tmpdir_path = Path(self._tmpdir)

    def tearDown(self):
        import shutil
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def test_pdf_page_pattern(self):
        """pdf_page_{N}.png パターンが最初に検索されること."""
        img = self._tmpdir_path / "pdf_page_3.png"
        img.touch()
        result = resolve_image_path(self._tmpdir_path, 3)
        self.assertEqual(result, img)

    def test_slide_pattern(self):
        """slide_{N}.png パターンが検索されること."""
        img = self._tmpdir_path / "slide_5.png"
        img.touch()
        result = resolve_image_path(self._tmpdir_path, 5)
        self.assertEqual(result, img)

    def test_number_pattern(self):
        """{N}.png パターンが検索されること."""
        img = self._tmpdir_path / "7.png"
        img.touch()
        result = resolve_image_path(self._tmpdir_path, 7)
        self.assertEqual(result, img)

    def test_pdf_page_takes_priority_over_slide(self):
        """pdf_page_{N}.png が slide_{N}.png より優先されること."""
        pdf_img = self._tmpdir_path / "pdf_page_2.png"
        slide_img = self._tmpdir_path / "slide_2.png"
        pdf_img.touch()
        slide_img.touch()
        result = resolve_image_path(self._tmpdir_path, 2)
        self.assertEqual(result, pdf_img)

    def test_not_found_raises_file_not_found_error(self):
        """画像が見つからない場合にFileNotFoundErrorが発生すること."""
        with self.assertRaises(FileNotFoundError) as ctx:
            resolve_image_path(self._tmpdir_path, 99)
        error_msg = str(ctx.exception)
        self.assertIn("99", error_msg)

    def test_error_message_contains_all_candidate_paths(self):
        """エラーメッセージに全候補パスが含まれること."""
        with self.assertRaises(FileNotFoundError) as ctx:
            resolve_image_path(self._tmpdir_path, 42)
        error_msg = str(ctx.exception)
        self.assertIn("pdf_page_42", error_msg)
        self.assertIn("slide_42", error_msg)


# ---------------------------------------------------------------------------
# 6. エッジケーステスト
# ---------------------------------------------------------------------------

class TestEdgeCases(unittest.TestCase):
    """エッジケースのテスト."""

    def test_slide_entry_with_empty_text_is_silent(self):
        """textが空のSlideEntryはis_silent=Trueが期待される."""
        entry = SlideEntry(number=1, title="", text="", is_silent=True)
        self.assertEqual(entry.text, "")
        self.assertTrue(entry.is_silent)

    def test_config_resolution_is_tuple(self):
        """resolution が tuple 型として返されること."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False, encoding="utf-8"
        ) as f:
            json.dump(_FULL_CONFIG_DATA, f)
            tmp = Path(f.name)
        try:
            config = Config.from_json(tmp)
            self.assertIsInstance(config.resolution, tuple)
        finally:
            tmp.unlink(missing_ok=True)

    def test_parse_script_single_slide(self):
        """スライド1枚だけの台本が正しくパースされること."""
        content = '## 紙芝居パート\n\n### スライド1：タイトル\n**セリフ**: 「こんにちは。」\n'
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".md", delete=False, encoding="utf-8"
        ) as f:
            f.write(content)
            tmp = Path(f.name)
        try:
            entries = parse_script(tmp)
            self.assertEqual(len(entries), 1)
            self.assertEqual(entries[0].number, 1)
            self.assertFalse(entries[0].is_silent)
        finally:
            tmp.unlink(missing_ok=True)

    def test_process_slides_dry_run_returns_none(self):
        """dry_run=Trueの場合、process_slidesがNoneを返すこと."""
        entries = [
            SlideEntry(number=1, title="タイトル", text="", is_silent=True),
            SlideEntry(number=2, title="テスト", text="テキスト", is_silent=False),
        ]
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False, encoding="utf-8"
        ) as f:
            json.dump(_FULL_CONFIG_DATA, f)
            tmp = Path(f.name)
        try:
            config = Config.from_json(tmp)
            result = gv.process_slides(entries, config, dry_run=True)
            self.assertIsNone(result)
        finally:
            tmp.unlink(missing_ok=True)

    def test_get_tts_provider_case_sensitive(self):
        """プロバイダー名は大文字小文字を区別すること（'Google'はNG）."""
        with self.assertRaises(ValueError):
            get_tts_provider("Google")


# ---------------------------------------------------------------------------
# 7. セキュリティ関連テスト
# ---------------------------------------------------------------------------

class TestSecurityChecks(unittest.TestCase):
    """セキュリティ関連のテスト."""

    def test_no_shell_true_in_subprocess_calls(self):
        """subprocess.run呼び出しにshell=Trueが使われていないこと."""
        import ast
        with open(Path(__file__).parent / "generate_video.py", encoding="utf-8") as f:
            source = f.read()
        tree = ast.parse(source)

        shell_true_calls = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                # subprocess.run(... shell=True ...) を探す
                for kw in getattr(node, "keywords", []):
                    if kw.arg == "shell" and isinstance(kw.value, ast.Constant) and kw.value.value is True:
                        shell_true_calls.append(node.lineno)

        self.assertEqual(
            shell_true_calls, [],
            f"shell=True が以下の行で使われています: {shell_true_calls}"
        )

    def test_subprocess_uses_list_not_string(self):
        """subprocess.runの第一引数がリスト形式であること（文字列コマンドはNG）."""
        import ast
        with open(Path(__file__).parent / "generate_video.py", encoding="utf-8") as f:
            source = f.read()
        tree = ast.parse(source)

        string_cmd_calls = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                # subprocess.run("string command") の形式を検出
                func = node.func
                is_subprocess_run = (
                    isinstance(func, ast.Attribute) and func.attr == "run"
                    and isinstance(func.value, ast.Name) and func.value.id == "subprocess"
                )
                if is_subprocess_run and node.args:
                    first_arg = node.args[0]
                    if isinstance(first_arg, ast.Constant) and isinstance(first_arg.value, str):
                        string_cmd_calls.append(node.lineno)

        self.assertEqual(
            string_cmd_calls, [],
            f"subprocess.runに文字列コマンドが渡されています: {string_cmd_calls}"
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
