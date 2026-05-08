#!/usr/bin/env python3
"""
紙芝居動画自動生成ツール

Markdown台本 + スライド画像 → TTS + FFmpeg → ナレーション付きMP4動画

Usage:
    python generate_video.py --config config.json
    python generate_video.py --config config.json --dry-run
    python generate_video.py --config config.json --slide 3
"""

from __future__ import annotations

import abc
import argparse
import json
import logging
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class SlideEntry:
    """パースされたスライド1枚分のデータ."""

    number: int
    title: str
    text: str  # TTS用テキスト。空文字列なら無音スライド
    is_silent: bool


@dataclass
class BGMConfig:
    """BGM合成の設定."""

    enabled: bool = False
    file: str = ""
    volume: float = 0.15


@dataclass
class Config:
    """設定ファイルの内容."""

    # TTS
    tts_provider: str
    tts_language: str
    tts_voice: str
    tts_speaking_rate: float
    tts_pitch: float
    tts_options: dict
    # Video
    resolution: tuple[int, int]
    fps: int
    silence_duration: float
    padding_before: float
    padding_after: float
    transition: str
    transition_duration: float
    # BGM
    bgm: BGMConfig
    # Paths
    images_dir: Path
    script_file: Path
    output_dir: Path

    @classmethod
    def from_json(cls, path: Path) -> Config:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)

        tts = data.get("tts", {})
        video = data.get("video", {})
        bgm_data = data.get("bgm", {})
        paths = data.get("paths", {})
        base_dir = path.parent

        return cls(
            tts_provider=tts.get("provider", "google"),
            tts_language=tts.get("language", "ja-JP"),
            tts_voice=tts.get("voice", "ja-JP-Neural2-C"),
            tts_speaking_rate=tts.get("speaking_rate", 0.9),
            tts_pitch=tts.get("pitch", 0.0),
            tts_options=tts.get("options", {}),
            resolution=tuple(video.get("resolution", [1920, 1080])),
            fps=video.get("fps", 30),
            silence_duration=video.get("silence_duration", 3.5),
            padding_before=video.get("padding_before", 0.5),
            padding_after=video.get("padding_after", 0.5),
            transition=video.get("transition", "none"),
            transition_duration=video.get("transition_duration", 0.5),
            bgm=BGMConfig(
                enabled=bgm_data.get("enabled", False),
                file=bgm_data.get("file", ""),
                volume=bgm_data.get("volume", 0.15),
            ),
            images_dir=base_dir / paths.get("images_dir", "input/images"),
            script_file=base_dir / paths.get("script_file", "input/script.md"),
            output_dir=base_dir / paths.get("output_dir", "output"),
        )


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="[%(levelname)s] %(message)s",
)
log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 1. 台本パース
# ---------------------------------------------------------------------------

# ### スライドN：タイトル
_SLIDE_HEADER_RE = re.compile(r"^###\s+スライド(\d+)[：:]\s*(.+)$", re.MULTILINE)
# 「テキスト」内のセリフ抽出
_SERIF_TEXT_RE = re.compile(r"「(.+?)」", re.DOTALL)


def parse_script(script_path: Path) -> list[SlideEntry]:
    """Markdown台本をパースしてSlideEntryのリストを返す."""
    content = script_path.read_text(encoding="utf-8")

    # 紙芝居パートのみ抽出（語りパート以降を除外）
    kamishibai_section = content
    lang_part_match = re.search(r"^##\s+語りパート", content, re.MULTILINE)
    if lang_part_match:
        kamishibai_section = content[: lang_part_match.start()]

    headers = list(_SLIDE_HEADER_RE.finditer(kamishibai_section))
    if not headers:
        raise ValueError(f"台本にスライドが見つかりません: {script_path}")

    entries: list[SlideEntry] = []

    for i, match in enumerate(headers):
        slide_num = int(match.group(1))
        slide_title = match.group(2).strip()

        # このスライドのセクション本文を取得
        start = match.end()
        end = (
            headers[i + 1].start() if i + 1 < len(headers) else len(kamishibai_section)
        )
        section_body = kamishibai_section[start:end]

        # セリフ行を探す
        serif_match = _SERIF_TEXT_RE.search(section_body)
        if serif_match:
            text = serif_match.group(1).strip()
            # 括弧内の演出指示を除去（例: 「（3秒の間の後）あなたの...」）
            text = re.sub(r"（[^）]*）", "", text).strip()
            entries.append(
                SlideEntry(
                    number=slide_num,
                    title=slide_title,
                    text=text,
                    is_silent=False,
                )
            )
        else:
            entries.append(
                SlideEntry(
                    number=slide_num,
                    title=slide_title,
                    text="",
                    is_silent=True,
                )
            )

    return entries


# ---------------------------------------------------------------------------
# 2. TTS プロバイダー
# ---------------------------------------------------------------------------


class TTSProvider(abc.ABC):
    """TTS プロバイダーの基底クラス.

    新しいプロバイダーを追加するには:
    1. このクラスを継承した具象クラスを作成
    2. synthesize() メソッドを実装
    3. _TTS_PROVIDERS 辞書にプロバイダー名とクラスを登録
    """

    @abc.abstractmethod
    def synthesize(self, text: str, output_path: Path, config: Config) -> None:
        """テキストを音声合成し、MP3ファイルとして保存する."""


class GoogleCloudTTS(TTSProvider):
    """Google Cloud TTS の実装."""

    def synthesize(self, text: str, output_path: Path, config: Config) -> None:
        try:
            from google.cloud import texttospeech
        except ImportError:
            log.error(
                "google-cloud-texttospeech がインストールされていません。\n"
                "  pip install google-cloud-texttospeech"
            )
            sys.exit(1)

        client = texttospeech.TextToSpeechClient()

        synthesis_input = texttospeech.SynthesisInput(text=text)
        voice = texttospeech.VoiceSelectionParams(
            language_code=config.tts_language,
            name=config.tts_voice,
        )
        audio_config = texttospeech.AudioConfig(
            audio_encoding=texttospeech.AudioEncoding.MP3,
            speaking_rate=config.tts_speaking_rate,
            pitch=config.tts_pitch,
        )

        response = client.synthesize_speech(
            input=synthesis_input,
            voice=voice,
            audio_config=audio_config,
        )

        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(response.audio_content)
        log.info("  TTS出力: %s", output_path.name)


class VoicevoxTTS(TTSProvider):
    """VOICEVOX ローカルエンジンの実装.

    VOICEVOXエンジン（http://localhost:50021）にHTTPリクエストを送信して音声合成する。
    事前にVOICEVOXを起動しておく必要がある。

    config.tts_options で以下を指定可能:
      - base_url: エンジンのURL（デフォルト: http://localhost:50021）
      - speaker: 話者ID（デフォルト: 1 = ずんだもん）
    """

    def synthesize(self, text: str, output_path: Path, config: Config) -> None:
        import urllib.parse
        import urllib.request

        base_url = config.tts_options.get("base_url", "http://localhost:50021")
        speaker = config.tts_options.get("speaker", 1)

        # 1. audio_query: テキストからクエリJSONを取得
        query_url = (
            f"{base_url}/audio_query"
            f"?text={urllib.parse.quote(text)}&speaker={speaker}"
        )
        req = urllib.request.Request(query_url, method="POST")
        try:
            with urllib.request.urlopen(req) as resp:
                query_json = resp.read()
        except Exception as e:
            log.error(
                "VOICEVOX audio_query に失敗しました。\n"
                "  VOICEVOXが起動していることを確認してください。\n"
                "  URL: %s\n  エラー: %s",
                base_url,
                e,
            )
            raise RuntimeError(f"VOICEVOX audio_query failed: {e}") from e

        # speaking_rate / pitch の適用
        query = json.loads(query_json)
        query["speedScale"] = config.tts_speaking_rate
        query["pitchScale"] = config.tts_pitch
        query_json = json.dumps(query).encode()

        # 2. synthesis: クエリJSONから音声WAVを取得
        synth_url = f"{base_url}/synthesis?speaker={speaker}"
        req = urllib.request.Request(
            synth_url,
            data=query_json,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req) as resp:
                wav_data = resp.read()
        except Exception as e:
            log.error("VOICEVOX synthesis に失敗しました: %s", e)
            raise RuntimeError(f"VOICEVOX synthesis failed: {e}") from e

        # 3. WAV → MP3 変換（FFmpeg）
        output_path.parent.mkdir(parents=True, exist_ok=True)
        wav_path = output_path.with_suffix(".wav")
        wav_path.write_bytes(wav_data)
        try:
            _run_ffmpeg(
                [
                    "-i",
                    str(wav_path),
                    "-c:a",
                    "libmp3lame",
                    "-q:a",
                    "4",
                    str(output_path),
                ],
                "VOICEVOX WAV→MP3変換",
            )
        finally:
            wav_path.unlink(missing_ok=True)
        log.info("  TTS出力 (VOICEVOX): %s", output_path.name)


# 将来のプロバイダーはここに追加:
# class OpenAITTS(TTSProvider): ...
# class ElevenLabsTTS(TTSProvider): ...

# プロバイダー名 → クラスのマッピング
_TTS_PROVIDERS: dict[str, type[TTSProvider]] = {
    "google": GoogleCloudTTS,
    "voicevox": VoicevoxTTS,
}


def get_tts_provider(provider_name: str) -> TTSProvider:
    """設定のプロバイダー名からTTSProviderインスタンスを返す."""
    cls = _TTS_PROVIDERS.get(provider_name)
    if cls is None:
        available = ", ".join(sorted(_TTS_PROVIDERS.keys()))
        raise ValueError(
            f"未対応のTTSプロバイダー: '{provider_name}'\n  利用可能: {available}"
        )
    return cls()


# ---------------------------------------------------------------------------
# 3. FFmpeg ユーティリティ
# ---------------------------------------------------------------------------


def _run_ffmpeg(args: list[str], description: str) -> None:
    """FFmpegコマンドを実行する. 失敗時は明確なエラーを出す."""
    cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "warning", *args]
    log.debug("実行: %s", " ".join(cmd))
    try:
        result = subprocess.run(cmd, capture_output=True, text=True)
    except FileNotFoundError:
        log.error(
            "ffmpeg が見つかりません。FFmpegをインストールしてPATHに追加してください。"
        )
        sys.exit(1)
    if result.returncode != 0:
        log.error(
            "%s に失敗しました (exit code %d)\nstderr: %s",
            description,
            result.returncode,
            result.stderr,
        )
        raise RuntimeError(f"FFmpeg failed: {description}")


def generate_silence(output_path: Path, duration: float) -> None:
    """指定秒数の無音MP3ファイルを生成する."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    _run_ffmpeg(
        [
            "-f",
            "lavfi",
            "-i",
            "anullsrc=r=44100:cl=stereo",
            "-t",
            str(duration),
            "-c:a",
            "libmp3lame",
            "-q:a",
            "4",
            str(output_path),
        ],
        f"無音生成 ({duration}s)",
    )
    log.info("  無音生成: %s (%.1fs)", output_path.name, duration)


def get_audio_duration(audio_path: Path) -> float:
    """ffprobeで音声ファイルの長さ（秒）を取得する."""
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        str(audio_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffprobe failed for {audio_path}: {result.stderr}")
    return float(result.stdout.strip())


def create_scene(
    image_path: Path,
    audio_path: Path,
    output_path: Path,
    config: Config,
) -> None:
    """1枚のスライド画像 + 音声 → MP4シーンを生成する."""
    duration = get_audio_duration(audio_path)
    total_duration = duration + config.padding_before + config.padding_after
    width, height = config.resolution

    output_path.parent.mkdir(parents=True, exist_ok=True)
    _run_ffmpeg(
        [
            "-loop",
            "1",
            "-i",
            str(image_path),
            "-i",
            str(audio_path),
            "-t",
            f"{total_duration:.3f}",
            "-vf",
            (
                f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
                f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color=black,"
                "format=yuv420p"
            ),
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            "-crf",
            "23",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-af",
            f"adelay={int(config.padding_before * 1000)}|{int(config.padding_before * 1000)},apad",
            "-shortest",
            "-r",
            str(config.fps),
            str(output_path),
        ],
        f"シーン生成 ({output_path.name})",
    )


def concatenate_scenes(scene_paths: list[Path], output_path: Path) -> None:
    """concat demuxerで複数のシーンMP4を結合する."""
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # 一時ファイルにconcat listを書き出す
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".txt", delete=False, encoding="utf-8"
    ) as f:
        for scene in scene_paths:
            # FFmpeg concat demuxer用。Windowsパスのバックスラッシュをエスケープ
            safe_path = str(scene.resolve()).replace("\\", "/")
            f.write(f"file '{safe_path}'\n")
        concat_list = f.name

    try:
        _run_ffmpeg(
            [
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                concat_list,
                "-c",
                "copy",
                str(output_path),
            ],
            "シーン結合",
        )
    finally:
        Path(concat_list).unlink(missing_ok=True)


def get_video_duration(video_path: Path) -> float:
    """ffprobeで動画ファイルの長さ（秒）を取得する."""
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        str(video_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffprobe failed for {video_path}: {result.stderr}")
    return float(result.stdout.strip())


def concatenate_scenes_with_transition(
    scene_paths: list[Path],
    output_path: Path,
    config: Config,
) -> None:
    """トランジション付きで複数のシーンMP4を結合する.

    config.transition が "none" または シーンが1つ以下の場合は
    通常の concat demuxer にフォールバックする。

    対応トランジション:
      - "crossfade": スライド間でクロスフェード（xfade transition=fade）
      - "fade_black": フェードアウト→黒→フェードイン（xfade transition=fadeblack）
    """
    if config.transition == "none" or len(scene_paths) < 2:
        concatenate_scenes(scene_paths, output_path)
        return

    # xfadeトランジション名のマッピング
    xfade_map = {
        "crossfade": "fade",
        "fade_black": "fadeblack",
    }
    xfade_name = xfade_map.get(config.transition)
    if xfade_name is None:
        log.warning(
            "未対応のトランジション '%s'。カット結合にフォールバックします。",
            config.transition,
        )
        concatenate_scenes(scene_paths, output_path)
        return

    duration = config.transition_duration

    # 各シーンの長さを取得
    durations = [get_video_duration(p) for p in scene_paths]

    # xfadeフィルターチェーンと音声acrossfadeチェーンを構築
    # 入力: [0], [1], [2], ...
    # ビデオ: [0][1]xfade=...offset=X[v0]; [v0][2]xfade=...offset=Y[v1]; ...
    # オーディオ: [0:a][1:a]acrossfade=d=D[a0]; [a0][2:a]acrossfade=d=D[a1]; ...
    inputs: list[str] = []
    for p in scene_paths:
        inputs.extend(["-i", str(p)])

    video_filters: list[str] = []
    audio_filters: list[str] = []

    # 累積offset: 各xfadeの開始位置は「前のシーンの終了時刻 - transition_duration」
    cumulative_duration = durations[0]

    for i in range(1, len(scene_paths)):
        offset = max(0.0, cumulative_duration - duration)

        # ビデオフィルター
        if i == 1:
            v_in = "[0:v][1:v]"
        else:
            v_in = f"[v{i - 2}][{i}:v]"

        if i == len(scene_paths) - 1:
            v_out = "[vout]"
        else:
            v_out = f"[v{i - 1}]"

        video_filters.append(
            f"{v_in}xfade=transition={xfade_name}"
            f":duration={duration:.3f}:offset={offset:.3f}{v_out}"
        )

        # オーディオフィルター
        if i == 1:
            a_in = "[0:a][1:a]"
        else:
            a_in = f"[a{i - 2}][{i}:a]"

        if i == len(scene_paths) - 1:
            a_out = "[aout]"
        else:
            a_out = f"[a{i - 1}]"

        audio_filters.append(
            f"{a_in}acrossfade=d={duration:.3f}:c1=tri:c2=tri{a_out}"
        )

        # 次のoffset計算のため、トランジション重なり分を引く
        cumulative_duration = offset + durations[i]

    filter_complex = ";".join(video_filters + audio_filters)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    _run_ffmpeg(
        [
            *inputs,
            "-filter_complex",
            filter_complex,
            "-map",
            "[vout]",
            "-map",
            "[aout]",
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            "-crf",
            "23",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            str(output_path),
        ],
        f"トランジション結合 ({config.transition})",
    )
    log.info("  トランジション結合完了: %s (%s)", output_path.name, config.transition)


def mix_bgm(video_path: Path, config: Config) -> Path:
    """最終動画にBGMをミックスする.

    BGMは動画の長さに合わせてループし、指定音量で合成する。
    元の動画を _no_bgm サフィックス付きで退避し、同じパスにBGM付き動画を出力する。
    """
    # config.jsonのあるディレクトリからの相対パスで解決
    bgm_file = (config.output_dir.parent / config.bgm.file).resolve()
    if not bgm_file.exists():
        log.warning("BGMファイルが見つかりません: %s (BGMなしで続行)", bgm_file)
        return video_path

    video_duration = get_audio_duration(video_path)
    log.info("BGM合成中 (%.1fs, volume=%.2f)...", video_duration, config.bgm.volume)

    output_path = video_path.with_stem(video_path.stem + "_with_bgm")
    _run_ffmpeg(
        [
            "-i",
            str(video_path),
            "-stream_loop",
            "-1",
            "-i",
            str(bgm_file),
            "-t",
            f"{video_duration:.3f}",
            "-filter_complex",
            (
                f"[1:a]volume={config.bgm.volume},"
                f"afade=t=out:st={max(0.0, video_duration - 2):.3f}:d=2[bgm];"
                "[0:a][bgm]amix=inputs=2:duration=first:dropout_transition=2[aout]"
            ),
            "-map",
            "0:v",
            "-map",
            "[aout]",
            "-c:v",
            "copy",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            str(output_path),
        ],
        "BGM合成",
    )

    # BGM付き動画を元のパスに置き換え
    backup_path = video_path.with_stem(video_path.stem + "_no_bgm")
    shutil.move(str(video_path), str(backup_path))
    shutil.move(str(output_path), str(video_path))
    log.info("  BGM合成完了 (バックアップ: %s)", backup_path.name)
    return video_path


# ---------------------------------------------------------------------------
# 4. 画像ファイル解決
# ---------------------------------------------------------------------------


def resolve_image_path(images_dir: Path, slide_number: int) -> Path:
    """スライド番号から画像ファイルパスを解決する.

    以下のパターンを順に探す:
      - pdf_page_{N}.png
      - slide_{N}.png
      - {N}.png
    """
    candidates = [
        images_dir / f"pdf_page_{slide_number}.png",
        images_dir / f"slide_{slide_number}.png",
        images_dir / f"{slide_number}.png",
    ]
    for path in candidates:
        if path.exists():
            return path

    raise FileNotFoundError(
        f"スライド{slide_number}の画像が見つかりません。\n"
        f"  検索パス: {', '.join(str(c) for c in candidates)}"
    )


# ---------------------------------------------------------------------------
# 5. メインフロー
# ---------------------------------------------------------------------------


def process_slides(
    entries: list[SlideEntry],
    config: Config,
    *,
    target_slide: int | None = None,
    dry_run: bool = False,
) -> Path | None:
    """スライドを処理して最終動画を生成する."""
    audio_dir = config.output_dir / "audio"
    scenes_dir = config.output_dir / "scenes"
    audio_dir.mkdir(parents=True, exist_ok=True)
    scenes_dir.mkdir(parents=True, exist_ok=True)

    # TTSプロバイダーを初期化
    tts = get_tts_provider(config.tts_provider)

    # フィルタリング
    if target_slide is not None:
        entries = [e for e in entries if e.number == target_slide]
        if not entries:
            log.error("スライド%d が台本に見つかりません。", target_slide)
            sys.exit(1)

    total = len(entries)
    log.info("処理対象: %d スライド", total)

    if dry_run:
        log.info("=== ドライラン結果 ===")
        for entry in entries:
            status = "無音" if entry.is_silent else f"TTS ({len(entry.text)}文字)"
            log.info(
                "  スライド%2d: [%s] %s — %s",
                entry.number,
                status,
                entry.title,
                entry.text[:50] + "..."
                if len(entry.text) > 50
                else entry.text or "(silence)",
            )
        return None

    scene_paths: list[Path] = []

    for idx, entry in enumerate(entries, 1):
        log.info(
            "スライド %d/%d 処理中 (スライド%d: %s)...",
            idx,
            total,
            entry.number,
            entry.title,
        )

        # 画像解決
        image_path = resolve_image_path(config.images_dir, entry.number)

        # 音声生成
        audio_path = audio_dir / f"slide_{entry.number:02d}.mp3"
        if entry.is_silent:
            generate_silence(audio_path, config.silence_duration)
        else:
            tts.synthesize(entry.text, audio_path, config)

        # シーン生成
        scene_path = scenes_dir / f"scene_{entry.number:02d}.mp4"
        create_scene(image_path, audio_path, scene_path, config)
        scene_paths.append(scene_path)
        log.info(
            "  シーン完了: %s (%.1fs)",
            scene_path.name,
            get_audio_duration(audio_path)
            + config.padding_before
            + config.padding_after,
        )

    # 結合
    if len(scene_paths) == 1:
        final_path = config.output_dir / f"slide_{entries[0].number:02d}.mp4"
        shutil.copy2(scene_paths[0], final_path)
    else:
        final_path = config.output_dir / "final.mp4"
        log.info("シーン結合中...")
        concatenate_scenes_with_transition(scene_paths, final_path, config)

    # BGM合成（有効な場合）
    if config.bgm.enabled and config.bgm.file:
        final_path = mix_bgm(final_path, config)

    log.info("完了: %s", final_path)
    return final_path


def main() -> None:
    parser = argparse.ArgumentParser(
        description="紙芝居動画自動生成ツール",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "例:\n"
            "  python generate_video.py --config config.json\n"
            "  python generate_video.py --config config.json --dry-run\n"
            "  python generate_video.py --config config.json --slide 3\n"
        ),
    )
    parser.add_argument(
        "--config",
        required=True,
        type=Path,
        help="設定ファイル (JSON) のパス",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="台本パースのみ実行 (TTS/FFmpegをスキップ)",
    )
    parser.add_argument(
        "--slide",
        type=int,
        default=None,
        metavar="N",
        help="特定のスライド番号のみ処理",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="詳細ログを出力",
    )
    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # 設定読み込み
    if not args.config.exists():
        log.error("設定ファイルが見つかりません: %s", args.config)
        sys.exit(1)

    config = Config.from_json(args.config)

    # 台本パース
    if not config.script_file.exists():
        log.error("台本ファイルが見つかりません: %s", config.script_file)
        sys.exit(1)

    log.info("台本読み込み: %s", config.script_file)
    entries = parse_script(config.script_file)
    log.info("パース完了: %d スライド検出", len(entries))

    # FFmpeg存在チェック (dry-run以外)
    if not args.dry_run:
        for tool in ("ffmpeg", "ffprobe"):
            try:
                result = subprocess.run(
                    [tool, "-version"],
                    capture_output=True,
                    text=True,
                )
                tool_missing = result.returncode != 0
            except FileNotFoundError:
                tool_missing = True
            if tool_missing:
                log.error(
                    "%s が見つかりません。FFmpegをインストールしてPATHに追加してください。",
                    tool,
                )
                sys.exit(1)

    # 処理実行
    process_slides(
        entries,
        config,
        target_slide=args.slide,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    main()
