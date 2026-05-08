#!/usr/bin/env python3
"""
紙芝居動画ジェネレーター — Streamlit Web UI

Usage:
    streamlit run app.py
"""

from __future__ import annotations

import logging
import tempfile
from pathlib import Path

import streamlit as st

from generate_video import (
    BGMConfig,
    Config,
    SlideEntry,
    parse_script,
    process_slides,
    resolve_image_path,
)

# ---------------------------------------------------------------------------
# ログキャプチャ用ハンドラ
# ---------------------------------------------------------------------------


class StreamlitLogHandler(logging.Handler):
    """ログメッセージを session_state のリストに蓄積するハンドラ."""

    def __init__(self, log_list: list[str]) -> None:
        super().__init__()
        self._log_list = log_list

    def emit(self, record: logging.LogRecord) -> None:
        msg = self.format(record)
        self._log_list.append(msg)


# ---------------------------------------------------------------------------
# 定数
# ---------------------------------------------------------------------------

RESOLUTION_OPTIONS: dict[str, tuple[int, int]] = {
    "1920x1080 (Full HD)": (1920, 1080),
    "1280x720 (HD)": (1280, 720),
    "3840x2160 (4K)": (3840, 2160),
    "1080x1920 (縦型 Full HD)": (1080, 1920),
    "720x1280 (縦型 HD)": (720, 1280),
}

TRANSITION_OPTIONS: dict[str, str] = {
    "なし": "none",
    "クロスフェード": "crossfade",
    "フェードブラック": "fade_black",
}

GOOGLE_VOICES: list[str] = [
    "ja-JP-Neural2-B",
    "ja-JP-Neural2-C",
    "ja-JP-Neural2-D",
    "ja-JP-Standard-A",
    "ja-JP-Standard-B",
    "ja-JP-Standard-C",
    "ja-JP-Standard-D",
    "ja-JP-Wavenet-A",
    "ja-JP-Wavenet-B",
    "ja-JP-Wavenet-C",
    "ja-JP-Wavenet-D",
]

# ---------------------------------------------------------------------------
# ページ設定
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="紙芝居動画ジェネレーター",
    page_icon="🎬",
    layout="centered",
)

st.title("紙芝居動画ジェネレーター")
st.caption("Markdown台本 + スライド画像 から TTS ナレーション付き MP4 動画を生成")


# ---------------------------------------------------------------------------
# セッションステート初期化
# ---------------------------------------------------------------------------

if "entries" not in st.session_state:
    st.session_state.entries = None
if "generated_video" not in st.session_state:
    st.session_state.generated_video = None
if "log_messages" not in st.session_state:
    st.session_state.log_messages = []


# ---------------------------------------------------------------------------
# ヘルパー関数
# ---------------------------------------------------------------------------


def load_script_from_path(script_path: str) -> list[SlideEntry] | None:
    """パス文字列から台本を読み込む."""
    p = Path(script_path)
    if not p.exists():
        st.error(f"台本ファイルが見つかりません: {p}")
        return None
    try:
        return parse_script(p)
    except ValueError as e:
        st.error(f"台本パースエラー: {e}")
        return None


def load_script_from_upload(uploaded_file) -> list[SlideEntry] | None:
    """アップロードファイルから台本を読み込む."""
    content = uploaded_file.read().decode("utf-8")
    # 一時ファイルに書き出してparse_scriptに渡す
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".md", delete=False, encoding="utf-8"
    ) as f:
        f.write(content)
        tmp_path = Path(f.name)
    try:
        return parse_script(tmp_path)
    except ValueError as e:
        st.error(f"台本パースエラー: {e}")
        return None
    finally:
        tmp_path.unlink(missing_ok=True)


def build_config(
    *,
    tts_provider: str,
    tts_voice: str,
    tts_speaking_rate: float,
    tts_pitch: float,
    tts_options: dict,
    resolution: tuple[int, int],
    transition: str,
    transition_duration: float,
    bgm_enabled: bool,
    bgm_file: str,
    bgm_volume: float,
    images_dir: str,
    script_file: str,
    output_dir: str,
) -> Config:
    """UI入力からConfigオブジェクトを構築する."""
    return Config(
        tts_provider=tts_provider,
        tts_language="ja-JP",
        tts_voice=tts_voice,
        tts_speaking_rate=tts_speaking_rate,
        tts_pitch=tts_pitch,
        tts_options=tts_options,
        resolution=resolution,
        fps=30,
        silence_duration=3.5,
        padding_before=0.5,
        padding_after=0.5,
        transition=transition,
        transition_duration=transition_duration,
        bgm=BGMConfig(
            enabled=bgm_enabled,
            file=bgm_file,
            volume=bgm_volume,
        ),
        images_dir=Path(images_dir),
        script_file=Path(script_file),
        output_dir=Path(output_dir),
    )


# ---------------------------------------------------------------------------
# 入力設定
# ---------------------------------------------------------------------------

with st.expander("入力設定", expanded=True):
    script_mode = st.radio(
        "台本ファイルの指定方法",
        ["ファイルパス入力", "ファイルアップロード"],
        horizontal=True,
    )

    script_path_value = ""
    uploaded_script = None

    if script_mode == "ファイルパス入力":
        script_path_value = st.text_input(
            "台本ファイルパス",
            value="input/script.md",
            help="Markdownファイルのパスを入力",
        )
    else:
        uploaded_script = st.file_uploader(
            "台本ファイル (.md)",
            type=["md", "txt"],
        )

    images_dir_value = st.text_input(
        "画像フォルダパス",
        value="input/images",
        help="スライド画像が格納されたフォルダのパスを入力",
    )

    # 台本読み込みボタン
    if st.button("台本を読み込む", type="secondary"):
        if script_mode == "ファイルパス入力":
            if script_path_value:
                st.session_state.entries = load_script_from_path(script_path_value)
            else:
                st.error("台本ファイルのパスを入力してください。")
        else:
            if uploaded_script is not None:
                st.session_state.entries = load_script_from_upload(uploaded_script)
            else:
                st.error("台本ファイルをアップロードしてください。")

        # 台本読み込み時に前回の生成結果をクリア
        st.session_state.generated_video = None


# ---------------------------------------------------------------------------
# TTS設定
# ---------------------------------------------------------------------------

with st.expander("TTS設定"):
    tts_provider = st.radio(
        "TTSプロバイダー",
        ["Google Cloud TTS", "VOICEVOX"],
        horizontal=True,
    )

    provider_key = "google" if tts_provider == "Google Cloud TTS" else "voicevox"

    if provider_key == "google":
        tts_voice = st.selectbox("音声", GOOGLE_VOICES, index=1)
    else:
        tts_voice = "voicevox"  # VOICEVOXでは使わないがConfigに必要

    col_rate, col_pitch = st.columns(2)
    with col_rate:
        tts_speaking_rate = st.slider(
            "話速",
            min_value=0.5,
            max_value=2.0,
            value=0.9,
            step=0.05,
        )
    with col_pitch:
        tts_pitch = st.slider(
            "ピッチ",
            min_value=-10.0,
            max_value=10.0,
            value=0.0,
            step=0.5,
        )

    tts_options: dict = {}
    if provider_key == "voicevox":
        vv_base_url = st.text_input(
            "VOICEVOX Base URL",
            value="http://localhost:50021",
        )
        vv_speaker = st.number_input(
            "Speaker ID",
            min_value=0,
            value=1,
            step=1,
            help="0=四国めたん, 1=ずんだもん, 2=春日部つむぎ, etc.",
        )
        tts_options = {"base_url": vv_base_url, "speaker": int(vv_speaker)}


# ---------------------------------------------------------------------------
# 動画設定
# ---------------------------------------------------------------------------

with st.expander("動画設定"):
    resolution_label = st.selectbox(
        "解像度",
        list(RESOLUTION_OPTIONS.keys()),
        index=0,
    )
    resolution = RESOLUTION_OPTIONS[resolution_label]

    transition_label = st.selectbox(
        "トランジション",
        list(TRANSITION_OPTIONS.keys()),
        index=0,
    )
    transition = TRANSITION_OPTIONS[transition_label]

    transition_duration = st.slider(
        "トランジション時間（秒）",
        min_value=0.1,
        max_value=2.0,
        value=0.5,
        step=0.1,
        disabled=(transition == "none"),
    )


# ---------------------------------------------------------------------------
# BGM設定
# ---------------------------------------------------------------------------

with st.expander("BGM設定"):
    bgm_enabled = st.checkbox("BGMを有効にする", value=False)
    bgm_file_value = ""
    bgm_volume = 0.15

    if bgm_enabled:
        bgm_file_value = st.text_input(
            "BGMファイルパス",
            value="",
            help="MP3/WAVファイルのパスを入力",
        )
        bgm_volume = st.slider(
            "BGM音量",
            min_value=0.0,
            max_value=1.0,
            value=0.15,
            step=0.01,
        )


# ---------------------------------------------------------------------------
# 台本プレビュー
# ---------------------------------------------------------------------------

entries: list[SlideEntry] | None = st.session_state.entries

if entries:
    with st.expander("台本プレビュー", expanded=True):
        st.write(f"**{len(entries)} スライド検出**")

        # スライドタブ表示
        for entry in entries:
            status_icon = "🔇" if entry.is_silent else "🔊"
            with st.container(border=True):
                col_info, col_preview = st.columns([3, 2])
                with col_info:
                    st.markdown(
                        f"**スライド {entry.number}**: {entry.title} {status_icon}"
                    )
                    if entry.is_silent:
                        st.caption("（無音スライド）")
                    else:
                        st.write(f"「{entry.text}」")

                with col_preview:
                    # 画像プレビュー
                    images_dir_path = Path(images_dir_value)
                    try:
                        img_path = resolve_image_path(
                            images_dir_path, entry.number
                        )
                        st.image(
                            str(img_path),
                            caption=f"スライド {entry.number}",
                            use_container_width=True,
                        )
                    except FileNotFoundError:
                        st.info(
                            f"画像なし (スライド{entry.number})",
                            icon="🖼️",
                        )


# ---------------------------------------------------------------------------
# 実行ボタン
# ---------------------------------------------------------------------------

st.divider()

col_dry, col_gen = st.columns(2)

with col_dry:
    dry_run_clicked = st.button(
        "ドライラン",
        disabled=(entries is None),
        use_container_width=True,
    )

with col_gen:
    generate_clicked = st.button(
        "動画生成",
        type="primary",
        disabled=(entries is None),
        use_container_width=True,
    )

# 出力ディレクトリ
output_dir_value = "output"

# ---------------------------------------------------------------------------
# ドライラン実行
# ---------------------------------------------------------------------------

if dry_run_clicked and entries:
    st.subheader("ドライラン結果")

    # テーブル表示
    dry_run_data = []
    for entry in entries:
        status = "無音" if entry.is_silent else f"TTS ({len(entry.text)}文字)"
        text_preview = (
            entry.text[:60] + "..." if len(entry.text) > 60 else entry.text or "（無音）"
        )
        dry_run_data.append(
            {
                "スライド": entry.number,
                "タイトル": entry.title,
                "状態": status,
                "セリフ": text_preview,
            }
        )

    st.table(dry_run_data)
    st.success(f"{len(entries)} スライドを検出しました。動画生成の準備ができています。")


# ---------------------------------------------------------------------------
# 動画生成実行
# ---------------------------------------------------------------------------

if generate_clicked and entries:
    # 台本ファイルパスの決定
    if script_mode == "ファイルパス入力":
        effective_script_path = script_path_value
    else:
        # アップロードファイルの場合、一時ファイルとして保存
        if uploaded_script is not None:
            content = uploaded_script.read().decode("utf-8")
            tmp_script = tempfile.NamedTemporaryFile(
                mode="w", suffix=".md", delete=False, encoding="utf-8"
            )
            tmp_script.write(content)
            tmp_script.close()
            effective_script_path = tmp_script.name
        else:
            st.error("台本ファイルが指定されていません。")
            st.stop()

    # Config構築
    config = build_config(
        tts_provider=provider_key,
        tts_voice=tts_voice,
        tts_speaking_rate=tts_speaking_rate,
        tts_pitch=tts_pitch,
        tts_options=tts_options,
        resolution=resolution,
        transition=transition,
        transition_duration=transition_duration,
        bgm_enabled=bgm_enabled,
        bgm_file=bgm_file_value,
        bgm_volume=bgm_volume,
        images_dir=images_dir_value,
        script_file=effective_script_path,
        output_dir=output_dir_value,
    )

    # ログキャプチャ設定
    st.session_state.log_messages = []
    log_handler = StreamlitLogHandler(st.session_state.log_messages)
    log_handler.setFormatter(logging.Formatter("[%(levelname)s] %(message)s"))

    # generate_video モジュールのロガーにハンドラを追加
    gv_logger = logging.getLogger("generate_video")
    gv_logger.addHandler(log_handler)
    # ルートロガーにも追加（generate_video.py が __name__ ロガーを使うため）
    root_logger = logging.getLogger()
    root_logger.addHandler(log_handler)

    try:
        # 生成実行
        with st.spinner("動画を生成中..."):
            progress_text = st.empty()
            progress_text.text(
                f"処理中: {len(entries)} スライド ({config.tts_provider} / "
                f"{resolution_label} / {transition_label})"
            )
            result_path = process_slides(entries, config)

        if result_path and result_path.exists():
            st.session_state.generated_video = str(result_path)
            st.success(f"動画生成が完了しました: {result_path.name}")
        else:
            st.error("動画の生成に失敗しました。ログを確認してください。")

    except Exception as e:
        st.error(f"エラーが発生しました: {e}")

    finally:
        # ハンドラを除去（重複防止）
        gv_logger.removeHandler(log_handler)
        root_logger.removeHandler(log_handler)

    # ログ表示
    if st.session_state.log_messages:
        with st.expander("生成ログ", expanded=False):
            st.code("\n".join(st.session_state.log_messages), language="text")


# ---------------------------------------------------------------------------
# 生成結果
# ---------------------------------------------------------------------------

if st.session_state.generated_video:
    video_path = Path(st.session_state.generated_video)
    if video_path.exists():
        st.subheader("生成結果")

        # 動画プレビュー
        st.video(str(video_path))

        # ダウンロードボタン
        with open(video_path, "rb") as vf:
            st.download_button(
                label="動画をダウンロード",
                data=vf.read(),
                file_name=video_path.name,
                mime="video/mp4",
                use_container_width=True,
            )
