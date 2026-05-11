#!/usr/bin/env python3
"""
紙芝居動画ジェネレーター — Streamlit Web UI

Usage:
    streamlit run app.py
"""

from __future__ import annotations

import logging
import os
import tempfile
from pathlib import Path

import streamlit as st

from generate_video import (
    BGMConfig,
    Config,
    SlideEntry,
    get_video_duration,
    parse_script,
    process_slides,
    resolve_image_path,
)

# ---------------------------------------------------------------------------
# アプリのベースディレクトリ（app.py の場所に固定）
# ---------------------------------------------------------------------------

APP_DIR = Path(__file__).resolve().parent

# ---------------------------------------------------------------------------
# Google Cloud TTS 認証の自動検出（起動時）
# ---------------------------------------------------------------------------

# gcp-key.json が存在する場合は環境変数に設定する（後方互換）
_gcp_key_path = APP_DIR / "gcp-key.json"
if _gcp_key_path.exists():
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = str(_gcp_key_path)

# .api_key は generate_video.py 側で読み込むため、ここでは存在確認のみ
_api_key_path = APP_DIR / ".api_key"


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

# ---------------------------------------------------------------------------
# カスタム CSS — モダンUI スタイリング
# ---------------------------------------------------------------------------

st.markdown(
    """
<style>
/* ===== Google Fonts ===== */
@import url('https://fonts.googleapis.com/css2?family=Noto+Sans+JP:wght@300;400;500;700&display=swap');

/* ===== グローバル ===== */
.stApp {
    font-family: 'Noto Sans JP', sans-serif;
}

/* メインコンテナの余白調整 */
.block-container {
    padding-top: 1rem !important;
    max-width: 900px !important;
}

/* ===== カスタムヘッダー ===== */
.app-header {
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    border-radius: 16px;
    padding: 2rem 2.5rem;
    margin-bottom: 1.5rem;
    color: white;
    position: relative;
    overflow: hidden;
    box-shadow: 0 10px 40px rgba(102, 126, 234, 0.3);
}
.app-header::before {
    content: '';
    position: absolute;
    top: -50%;
    right: -20%;
    width: 300px;
    height: 300px;
    background: rgba(255, 255, 255, 0.08);
    border-radius: 50%;
}
.app-header::after {
    content: '';
    position: absolute;
    bottom: -30%;
    left: -10%;
    width: 200px;
    height: 200px;
    background: rgba(255, 255, 255, 0.05);
    border-radius: 50%;
}
.app-header h1 {
    margin: 0 0 0.3rem 0;
    font-size: 1.8rem;
    font-weight: 700;
    letter-spacing: -0.02em;
    position: relative;
    z-index: 1;
}
.app-header p {
    margin: 0;
    font-size: 0.95rem;
    opacity: 0.9;
    font-weight: 300;
    position: relative;
    z-index: 1;
}

/* ===== セクションタイトル ===== */
.section-title {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    font-size: 1.05rem;
    font-weight: 600;
    margin: 1.2rem 0 0.6rem 0;
    padding-bottom: 0.4rem;
    border-bottom: 2px solid;
    border-image: linear-gradient(90deg, #667eea, transparent) 1;
}
.section-title .icon {
    font-size: 1.2rem;
}

/* ===== Expander スタイリング ===== */
.stExpander {
    border: 1px solid rgba(128, 128, 128, 0.15) !important;
    border-radius: 12px !important;
    box-shadow: 0 2px 12px rgba(0, 0, 0, 0.06) !important;
    margin-bottom: 0.8rem !important;
    overflow: hidden;
    transition: box-shadow 0.3s ease;
}
.stExpander:hover {
    box-shadow: 0 4px 20px rgba(0, 0, 0, 0.1) !important;
}
.stExpander > details > summary {
    font-weight: 600 !important;
    font-size: 0.95rem !important;
    padding: 0.8rem 1rem !important;
}

/* ===== ボタン — プライマリ ===== */
.stButton > button[kind="primary"],
.stButton > button[data-testid="stBaseButton-primary"] {
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%) !important;
    border: none !important;
    border-radius: 10px !important;
    font-weight: 600 !important;
    font-size: 1rem !important;
    padding: 0.6rem 1.5rem !important;
    letter-spacing: 0.02em;
    box-shadow: 0 4px 15px rgba(102, 126, 234, 0.35) !important;
    transition: all 0.3s ease !important;
}
.stButton > button[kind="primary"]:hover,
.stButton > button[data-testid="stBaseButton-primary"]:hover {
    transform: translateY(-2px) !important;
    box-shadow: 0 6px 25px rgba(102, 126, 234, 0.5) !important;
}

/* ===== ボタン — セカンダリ ===== */
.stButton > button[kind="secondary"],
.stButton > button[data-testid="stBaseButton-secondary"] {
    border-radius: 10px !important;
    font-weight: 500 !important;
    border: 1.5px solid #667eea !important;
    color: #667eea !important;
    background: transparent !important;
    transition: all 0.3s ease !important;
}
.stButton > button[kind="secondary"]:hover,
.stButton > button[data-testid="stBaseButton-secondary"]:hover {
    background: rgba(102, 126, 234, 0.08) !important;
    transform: translateY(-1px) !important;
}

/* ===== ダウンロードボタン ===== */
.stDownloadButton > button {
    background: linear-gradient(135deg, #11998e 0%, #38ef7d 100%) !important;
    border: none !important;
    border-radius: 10px !important;
    color: white !important;
    font-weight: 600 !important;
    box-shadow: 0 4px 15px rgba(17, 153, 142, 0.35) !important;
    transition: all 0.3s ease !important;
}
.stDownloadButton > button:hover {
    transform: translateY(-2px) !important;
    box-shadow: 0 6px 25px rgba(17, 153, 142, 0.5) !important;
}

/* ===== テキスト入力 ===== */
.stTextInput > div > div > input {
    border-radius: 8px !important;
    border: 1.5px solid rgba(128, 128, 128, 0.25) !important;
    transition: border-color 0.3s ease, box-shadow 0.3s ease !important;
}
.stTextInput > div > div > input:focus {
    border-color: #667eea !important;
    box-shadow: 0 0 0 3px rgba(102, 126, 234, 0.15) !important;
}

/* ===== セレクトボックス ===== */
.stSelectbox > div > div {
    border-radius: 8px !important;
}

/* ===== スライダー ===== */
.stSlider > div > div > div > div {
    background: linear-gradient(90deg, #667eea, #764ba2) !important;
}

/* ===== プログレスバー ===== */
.stProgress > div > div > div {
    background: linear-gradient(90deg, #667eea, #764ba2) !important;
    border-radius: 10px !important;
}

/* ===== コンテナ（border=True）のスタイリング ===== */
[data-testid="stVerticalBlockBorderWrapper"] {
    border-radius: 10px !important;
    border-color: rgba(128, 128, 128, 0.15) !important;
    transition: box-shadow 0.3s ease;
}
[data-testid="stVerticalBlockBorderWrapper"]:hover {
    box-shadow: 0 2px 12px rgba(0, 0, 0, 0.06);
}

/* ===== テーブル ===== */
.stTable {
    border-radius: 10px !important;
    overflow: hidden;
}
.stTable table {
    border-collapse: separate !important;
    border-spacing: 0 !important;
}
.stTable thead th {
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%) !important;
    color: white !important;
    font-weight: 600 !important;
    padding: 0.7rem 1rem !important;
    font-size: 0.85rem !important;
}
.stTable tbody td {
    padding: 0.6rem 1rem !important;
    font-size: 0.85rem !important;
}
.stTable tbody tr:nth-child(even) {
    background: rgba(102, 126, 234, 0.03);
}

/* ===== アラート系のスタイリング ===== */
.stAlert {
    border-radius: 10px !important;
}

/* ===== サイドバー ===== */
[data-testid="stSidebar"] .sidebar-info {
    background: rgba(102, 126, 234, 0.08);
    border-radius: 10px;
    padding: 1rem;
    margin-bottom: 0.8rem;
    border-left: 3px solid #667eea;
}
[data-testid="stSidebar"] .sidebar-info h4 {
    margin: 0 0 0.4rem 0;
    font-size: 0.85rem;
    font-weight: 600;
    color: #667eea;
}
[data-testid="stSidebar"] .sidebar-info p {
    margin: 0;
    font-size: 0.8rem;
    opacity: 0.85;
    line-height: 1.5;
}

/* ===== 動画プレーヤー ===== */
.stVideo {
    border-radius: 12px !important;
    overflow: hidden;
    box-shadow: 0 4px 20px rgba(0, 0, 0, 0.12) !important;
}

/* ===== ファイルアップローダー ===== */
[data-testid="stFileUploader"] section {
    border-radius: 10px !important;
    border: 2px dashed rgba(102, 126, 234, 0.3) !important;
    transition: border-color 0.3s ease;
}
[data-testid="stFileUploader"] section:hover {
    border-color: #667eea !important;
}

/* ===== 結果セクション装飾 ===== */
.result-header {
    background: linear-gradient(135deg, rgba(17, 153, 142, 0.08) 0%, rgba(56, 239, 125, 0.08) 100%);
    border: 1px solid rgba(17, 153, 142, 0.2);
    border-radius: 12px;
    padding: 1rem 1.5rem;
    margin-bottom: 1rem;
}
.result-header h3 {
    margin: 0;
    font-weight: 700;
    font-size: 1.1rem;
}

/* ===== スクロールバー ===== */
::-webkit-scrollbar {
    width: 6px;
    height: 6px;
}
::-webkit-scrollbar-track {
    background: transparent;
}
::-webkit-scrollbar-thumb {
    background: rgba(102, 126, 234, 0.3);
    border-radius: 3px;
}
::-webkit-scrollbar-thumb:hover {
    background: rgba(102, 126, 234, 0.5);
}

/* ===== フェードインアニメーション ===== */
@keyframes fadeInUp {
    from {
        opacity: 0;
        transform: translateY(10px);
    }
    to {
        opacity: 1;
        transform: translateY(0);
    }
}
.stExpander {
    animation: fadeInUp 0.4s ease-out;
}
</style>
""",
    unsafe_allow_html=True,
)

# ---------------------------------------------------------------------------
# カスタムヘッダー
# ---------------------------------------------------------------------------

st.markdown(
    """
<div class="app-header">
    <h1>🎬 紙芝居動画ジェネレーター</h1>
    <p>Markdown台本 + スライド画像 から TTS ナレーション付き MP4 動画を生成</p>
</div>
""",
    unsafe_allow_html=True,
)

# ---------------------------------------------------------------------------
# サイドバー — プロジェクト情報・ヘルプ
# ---------------------------------------------------------------------------

with st.sidebar:
    st.markdown(
        """
<div style="text-align:center; padding: 1rem 0 0.5rem 0;">
    <span style="font-size: 2.5rem;">🎬</span>
    <h3 style="margin: 0.3rem 0 0 0; font-weight: 700; font-size: 1.1rem;">
        Kamishibai Studio
    </h3>
    <p style="margin: 0; font-size: 0.75rem; opacity: 0.6;">v1.0</p>
</div>
""",
        unsafe_allow_html=True,
    )
    st.divider()
    st.markdown(
        """
<div class="sidebar-info">
    <h4>📋 使い方</h4>
    <p>
        1. 台本(.md)を読み込む<br/>
        2. 画像ソースを指定<br/>
        3. TTS・動画設定を調整<br/>
        4.「動画生成」をクリック
    </p>
</div>
<div class="sidebar-info">
    <h4>🎙️ 対応TTS</h4>
    <p>
        Google Cloud TTS<br/>
        VOICEVOX
    </p>
</div>
<div class="sidebar-info">
    <h4>🖼️ 画像ソース</h4>
    <p>
        フォルダ読込 / HTML静止画<br/>
        HTMLアニメ録画 / 外部動画
    </p>
</div>
""",
        unsafe_allow_html=True,
    )
    st.divider()
    output_dir_value = st.text_input(
        "出力ディレクトリ",
        value="output",
        help="生成された動画の保存先",
        key="output_dir_sidebar",
    )

# ---------------------------------------------------------------------------
# セッションステート初期化
# ---------------------------------------------------------------------------

if "entries" not in st.session_state:
    st.session_state.entries = None
if "generated_video" not in st.session_state:
    st.session_state.generated_video = None
if "log_messages" not in st.session_state:
    st.session_state.log_messages = []
if "error_message" not in st.session_state:
    st.session_state.error_message = None


# ---------------------------------------------------------------------------
# ヘルパー関数
# ---------------------------------------------------------------------------


def resolve_path(user_path: str) -> Path:
    """ユーザー入力パスを解決する。絶対パスならそのまま、相対パスならAPP_DIR基準。"""
    p = Path(user_path.strip().strip('"').strip("'"))
    if p.is_absolute():
        return p
    return APP_DIR / p


def load_script_from_path(script_path: str) -> list[SlideEntry] | None:
    """パス文字列から台本を読み込む。エラー時は None を返す（エラーは呼び出し元が session_state に保存）。"""
    p = resolve_path(script_path)
    if not p.exists():
        return None
    try:
        return parse_script(p)
    except ValueError as e:
        raise ValueError(f"台本パースエラー: {e}") from e


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
        raise ValueError(f"台本パースエラー: {e}") from e
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
        images_dir=resolve_path(images_dir),
        script_file=resolve_path(script_file),
        output_dir=resolve_path(output_dir),
    )


# ---------------------------------------------------------------------------
# 入力設定
# ---------------------------------------------------------------------------

st.markdown(
    '<div class="section-title"><span class="icon">📂</span> 入力設定</div>',
    unsafe_allow_html=True,
)
with st.expander("台本・画像ソース", expanded=True):
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
            value="",
            placeholder="例: input/script.md",
            help="台本ファイル(.md)のパスを入力してください",
        )
    else:
        uploaded_script = st.file_uploader(
            "台本ファイル (.md)",
            type=["md", "txt"],
        )

    st.divider()
    st.markdown("**画像ソース**")

    image_source = st.radio(
        "画像の取得方法",
        [
            "フォルダから読み込み",
            "HTMLファイルから生成（静止画）",
            "HTMLアニメーション録画（動画）",
            "外部動画ファイル（ナレーションオーバーレイ）",
        ],
        horizontal=True,
    )

    # video_clips_dir はHTMLアニメーション録画モードでのみ使用
    video_clips_dir_value: str | None = None
    # 外部動画ファイルモード用
    external_video_path_value: str | None = None

    if image_source == "フォルダから読み込み":
        images_dir_value = st.text_input(
            "画像フォルダパス",
            value="",
            placeholder="例: input/images",
            help="スライド画像が入ったフォルダのパスを入力してください",
        )
    elif image_source == "HTMLファイルから生成（静止画）":
        # HTML -> 画像変換モード（既存）
        html_file_path = st.text_input(
            "HTMLファイルパス",
            value="",
            help="Claude Artifact等のHTMLファイルのパスを入力",
            key="html_screenshot_path",
        )
        col_slides, col_key, col_wait = st.columns(3)
        with col_slides:
            html_num_slides = st.number_input(
                "スライド数",
                min_value=1,
                max_value=100,
                value=14,
                step=1,
                key="screenshot_num_slides",
            )
        with col_key:
            html_nav_key = st.selectbox(
                "遷移キー",
                ["ArrowRight", "ArrowLeft", "ArrowDown", "Space", "Enter"],
                index=0,
                key="screenshot_nav_key",
            )
        with col_wait:
            html_wait_time = st.number_input(
                "待機時間（秒）",
                min_value=0.5,
                max_value=10.0,
                value=2.0,
                step=0.5,
                key="screenshot_wait_time",
            )

        images_dir_value = "input/images"

        if st.button("スクリーンショット実行", type="secondary"):
            if not html_file_path:
                st.error("HTMLファイルのパスを入力してください。")
            else:
                resolved_html = resolve_path(html_file_path)
                if not resolved_html.exists():
                    st.error(f"HTMLファイルが見つかりません: {resolved_html}")
                else:
                    try:
                        from html_to_images import capture_slides

                        output_path = resolve_path(images_dir_value)
                        progress_bar = st.progress(0)
                        status_text = st.empty()

                        def _update_progress(
                            current: int, total: int, path: Path
                        ) -> None:
                            progress_bar.progress(current / total)
                            status_text.text(
                                f"スライド {current}/{total}: {path.name}"
                            )

                        with st.spinner("HTMLからスクリーンショットを撮影中..."):
                            paths = capture_slides(
                                html_path=str(resolved_html),
                                output_dir=str(output_path),
                                num_slides=int(html_num_slides),
                                nav_key=html_nav_key,
                                wait=float(html_wait_time),
                                progress_callback=_update_progress,
                            )
                        progress_bar.progress(1.0)
                        st.success(
                            f"{len(paths)}枚のスクリーンショットを"
                            f" {output_path} に保存しました"
                        )
                    except FileNotFoundError as e:
                        st.error(str(e))
                    except RuntimeError as e:
                        st.error(str(e))
                    except Exception as e:
                        st.error(f"スクリーンショット撮影エラー: {e}")
    elif image_source == "HTMLアニメーション録画（動画）":
        # HTMLアニメーション録画モード（新規）
        html_video_path = st.text_input(
            "HTMLファイルパス",
            value="",
            help="アニメーション付きHTMLファイルのパスを入力",
            key="html_video_path",
        )
        col_vslides, col_vkey, col_vwait = st.columns(3)
        with col_vslides:
            html_video_num_slides = st.number_input(
                "スライド数",
                min_value=1,
                max_value=100,
                value=14,
                step=1,
                key="video_num_slides",
            )
        with col_vkey:
            html_video_nav_key = st.selectbox(
                "遷移キー",
                ["ArrowRight", "ArrowLeft", "ArrowDown", "Space", "Enter"],
                index=0,
                key="video_nav_key",
            )
        with col_vwait:
            html_video_wait_time = st.number_input(
                "初回待機（秒）",
                min_value=0.5,
                max_value=10.0,
                value=2.0,
                step=0.5,
                key="video_wait_time",
            )
        html_video_animation_wait = st.number_input(
            "アニメーション時間（秒）",
            min_value=1.0,
            max_value=30.0,
            value=3.0,
            step=0.5,
            help="各スライドのアニメーション再生待ち時間",
            key="video_animation_wait",
        )

        images_dir_value = "input/images"
        video_clips_dir_value = "output/clips"

        if st.button("アニメーション録画実行", type="secondary"):
            if not html_video_path:
                st.error("HTMLファイルのパスを入力してください。")
            else:
                resolved_html = resolve_path(html_video_path)
                if not resolved_html.exists():
                    st.error(f"HTMLファイルが見つかりません: {resolved_html}")
                else:
                    try:
                        from html_to_video import record_full_presentation

                        clips_output = resolve_path(video_clips_dir_value)
                        progress_bar = st.progress(0)
                        status_text = st.empty()

                        def _update_video_progress(
                            current: int, total: int, path: Path
                        ) -> None:
                            progress_bar.progress(current / total)
                            status_text.text(
                                f"スライド {current}/{total} 録画中..."
                            )

                        with st.spinner("HTMLアニメーションをフル録画中..."):
                            video_path, timestamps = record_full_presentation(
                                html_path=str(resolved_html),
                                output_dir=str(clips_output),
                                num_slides=int(html_video_num_slides),
                                nav_key=html_video_nav_key,
                                wait=float(html_video_wait_time),
                                animation_wait=float(html_video_animation_wait),
                                progress_callback=_update_video_progress,
                            )
                        progress_bar.progress(1.0)
                        st.success(
                            f"フル録画完了: {video_path.name}"
                            f" ({len(timestamps)}スライド)"
                        )
                    except FileNotFoundError as e:
                        st.error(str(e))
                    except RuntimeError as e:
                        st.error(str(e))
                    except Exception as e:
                        st.error(f"アニメーション録画エラー: {e}")
    else:
        # 外部動画ファイル（ナレーションオーバーレイ）モード
        external_video_path_value = st.text_input(
            "動画ファイルパス",
            value="",
            placeholder="例: C:/Videos/presentation.mp4",
            help=(
                "ナレーションを重ねたい動画ファイルのパスを入力してください。"
                "対応フォーマット: MP4, MOV, AVI, MKV, WebM, WMV 等（FFmpeg対応形式全て）"
            ),
            key="external_video_path",
        )
        images_dir_value = "input/images"  # 画像は不要だがConfig構築に必要

        # 動画情報の取得・表示
        if external_video_path_value:
            resolved_ext_video = resolve_path(external_video_path_value)
            if resolved_ext_video.exists():
                try:
                    ext_video_duration = get_video_duration(resolved_ext_video)
                    st.info(
                        f"動画ファイル: {resolved_ext_video.name}  |  "
                        f"長さ: {ext_video_duration:.1f}秒 "
                        f"({int(ext_video_duration // 60)}分{ext_video_duration % 60:.1f}秒)"
                    )
                    # session_stateに動画情報を保存
                    st.session_state["ext_video_duration"] = ext_video_duration
                    st.session_state["ext_video_path"] = str(resolved_ext_video)
                except Exception as e:
                    st.warning(f"動画情報の取得に失敗しました: {e}")
            else:
                st.warning(f"動画ファイルが見つかりません: {resolved_ext_video}")

    # エラーメッセージ表示（リラン後も session_state から復元して表示）
    if st.session_state.error_message:
        st.error(st.session_state.error_message)

    # 台本読み込みボタン
    if st.button("台本を読み込む", type="secondary"):
        st.session_state.error_message = None
        if script_mode == "ファイルパス入力":
            if script_path_value:
                try:
                    result = load_script_from_path(script_path_value)
                    if result is None:
                        resolved = resolve_path(script_path_value)
                        st.session_state.error_message = (
                            f"台本ファイルが見つかりません: {resolved}"
                        )
                    else:
                        st.session_state.entries = result
                        st.session_state.generated_video = None
                except ValueError as e:
                    st.session_state.error_message = str(e)
            else:
                st.session_state.error_message = (
                    "台本ファイルのパスを入力してください。"
                )
        else:
            if uploaded_script is not None:
                try:
                    result = load_script_from_upload(uploaded_script)
                    st.session_state.entries = result
                    st.session_state.generated_video = None
                except ValueError as e:
                    st.session_state.error_message = str(e)
            else:
                st.session_state.error_message = (
                    "台本ファイルをアップロードしてください。"
                )
        st.rerun()


# ---------------------------------------------------------------------------
# TTS設定
# ---------------------------------------------------------------------------

st.markdown(
    '<div class="section-title"><span class="icon">🎙️</span> 音声・動画設定</div>',
    unsafe_allow_html=True,
)
with st.expander("TTS設定（音声合成）"):
    tts_provider = st.radio(
        "TTSプロバイダー",
        ["Google Cloud TTS", "VOICEVOX"],
        horizontal=True,
        key="tts_provider_radio",
    )

    provider_key = "google" if tts_provider == "Google Cloud TTS" else "voicevox"

    if provider_key == "google":
        # APIキーの状態表示と入力フォーム
        with st.container(border=True):
            st.caption("Google Cloud APIキーの設定")
            if _api_key_path.exists():
                st.success("APIキーが保存されています")
            else:
                st.warning("APIキーが未設定です。下記から設定してください。")

            gcp_api_key_input = st.text_input(
                "Google Cloud APIキー",
                type="password",
                placeholder="AIza...",
                help="Google Cloud Console の Text-to-Speech API で取得したAPIキーを入力してください",
                key="gcp_api_key_input",
            )

            if st.button("保存", key="save_gcp_api_key"):
                if gcp_api_key_input:
                    _api_key_path.write_text(gcp_api_key_input.strip(), encoding="utf-8")
                    st.success("APIキーを保存しました！")
                    st.rerun()
                else:
                    st.error("APIキーを入力してください。")

        # 音声選択
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
        # 永続ストア（widget keyとは別にしてStreamlitの自動削除を回避）
        if "_vv_base_url" not in st.session_state:
            st.session_state["_vv_base_url"] = "http://localhost:50021"
        if "_vv_speaker_id" not in st.session_state:
            st.session_state["_vv_speaker_id"] = 1

        def _on_base_url_change():
            st.session_state["_vv_base_url"] = st.session_state["vv_base_url_widget"]

        def _on_speaker_change():
            st.session_state["_vv_speaker_id"] = int(st.session_state["vv_speaker_id_widget"])

        st.text_input(
            "VOICEVOX Base URL",
            value=st.session_state["_vv_base_url"],
            key="vv_base_url_widget",
            on_change=_on_base_url_change,
        )
        st.number_input(
            "Speaker ID（話者一覧は左サイドバーのページから確認）",
            min_value=0,
            value=st.session_state["_vv_speaker_id"],
            step=1,
            key="vv_speaker_id_widget",
            on_change=_on_speaker_change,
            help="0=四国めたん(あまあま), 1=ずんだもん(あまあま), 3=ずんだもん(ノーマル), 14=冥鳴ひまり, etc.",
        )


# ---------------------------------------------------------------------------
# 動画設定
# ---------------------------------------------------------------------------

with st.expander("動画設定（解像度・トランジション）"):
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

with st.expander("BGM設定（バックグラウンドミュージック）"):
    # 永続ストア初期化
    if "_bgm_enabled" not in st.session_state:
        st.session_state["_bgm_enabled"] = False
    if "_bgm_file" not in st.session_state:
        st.session_state["_bgm_file"] = ""
    if "_bgm_volume" not in st.session_state:
        st.session_state["_bgm_volume"] = 0.15

    def _on_bgm_enabled_change():
        st.session_state["_bgm_enabled"] = st.session_state["bgm_enabled_widget"]

    def _on_bgm_file_change():
        st.session_state["_bgm_file"] = st.session_state["bgm_file_widget"]

    def _on_bgm_volume_change():
        st.session_state["_bgm_volume"] = st.session_state["bgm_volume_widget"]

    bgm_enabled = st.checkbox(
        "BGMを有効にする",
        value=st.session_state["_bgm_enabled"],
        key="bgm_enabled_widget",
        on_change=_on_bgm_enabled_change,
    )
    bgm_file_value = ""
    bgm_volume = 0.15

    if bgm_enabled:
        bgm_file_value = st.text_input(
            "BGMファイルパス",
            value=st.session_state["_bgm_file"],
            key="bgm_file_widget",
            on_change=_on_bgm_file_change,
            help="MP3/WAVファイルのパスを入力",
        )
        bgm_volume = st.slider(
            "BGM音量",
            min_value=0.0,
            max_value=1.0,
            value=st.session_state["_bgm_volume"],
            step=0.01,
            key="bgm_volume_widget",
            on_change=_on_bgm_volume_change,
        )


# ---------------------------------------------------------------------------
# 台本プレビュー
# ---------------------------------------------------------------------------

entries: list[SlideEntry] | None = st.session_state.entries

if entries:
    st.markdown(
        '<div class="section-title"><span class="icon">📖</span> 台本プレビュー</div>',
        unsafe_allow_html=True,
    )
    with st.expander(f"全 {len(entries)} スライド", expanded=True):
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
                    # 画像プレビュー（resolve_path でAPP_DIR基準に解決）
                    images_dir_path = resolve_path(images_dir_value)
                    try:
                        img_path = resolve_image_path(images_dir_path, entry.number)
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
# タイムスタンプ入力（外部動画モード時のみ）
# ---------------------------------------------------------------------------

if "manual_timestamps" not in st.session_state:
    st.session_state.manual_timestamps = {}

if (
    image_source == "外部動画ファイル（ナレーションオーバーレイ）"
    and entries
    and external_video_path_value
):
    with st.expander("タイムスタンプ設定", expanded=True):
        st.write("各スライドのナレーション開始時刻（秒）を指定してください。")

        ext_dur = st.session_state.get("ext_video_duration", 0.0)
        if ext_dur > 0:
            st.caption(f"動画の長さ: {ext_dur:.1f}秒")

        # 均等分割ボタン
        if ext_dur > 0 and st.button("均等分割で自動入力", key="auto_timestamps"):
            interval = ext_dur / len(entries)
            for i, entry in enumerate(entries):
                st.session_state.manual_timestamps[entry.number] = round(
                    i * interval, 1
                )
            st.rerun()

        # 各スライドの開始秒数入力
        cols_per_row = 3
        for row_start in range(0, len(entries), cols_per_row):
            row_entries = entries[row_start : row_start + cols_per_row]
            cols = st.columns(cols_per_row)
            for col, entry in zip(cols, row_entries):
                with col:
                    default_val = st.session_state.manual_timestamps.get(
                        entry.number, 0.0
                    )
                    ts_val = st.number_input(
                        f"スライド{entry.number}: {entry.title[:10]}",
                        min_value=0.0,
                        max_value=max(ext_dur, 86400.0),
                        value=float(default_val),
                        step=0.5,
                        format="%.1f",
                        key=f"ts_slide_{entry.number}",
                    )
                    st.session_state.manual_timestamps[entry.number] = ts_val


# ---------------------------------------------------------------------------
# 実行ボタン
# ---------------------------------------------------------------------------

st.markdown(
    '<div class="section-title"><span class="icon">🚀</span> 実行</div>',
    unsafe_allow_html=True,
)

col_dry, col_gen = st.columns(2)

with col_dry:
    dry_run_clicked = st.button(
        "🔍 ドライラン",
        disabled=(entries is None),
        use_container_width=True,
    )

with col_gen:
    generate_clicked = st.button(
        "🎬 動画生成",
        type="primary",
        disabled=(entries is None),
        use_container_width=True,
    )

# 出力ディレクトリ（サイドバーで設定済み。未設定時のフォールバック）
if "output_dir_sidebar" not in st.session_state:
    output_dir_value = "output"

# ---------------------------------------------------------------------------
# ドライラン実行
# ---------------------------------------------------------------------------

if dry_run_clicked and entries:
    st.markdown(
        '<div class="result-header"><h3>🔍 ドライラン結果</h3></div>',
        unsafe_allow_html=True,
    )

    # テーブル表示
    dry_run_data = []
    for entry in entries:
        status = "無音" if entry.is_silent else f"TTS ({len(entry.text)}文字)"
        text_preview = (
            entry.text[:60] + "..."
            if len(entry.text) > 60
            else entry.text or "（無音）"
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
        effective_script_path = str(resolve_path(script_path_value))
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

    # VOICEVOX設定: 永続ストア(_vv_*)から読み取り（widget keyはStreamlitが削除する場合がある）
    if provider_key == "voicevox":
        tts_options = {
            "base_url": st.session_state.get("_vv_base_url", "http://localhost:50021"),
            "speaker": int(st.session_state.get("_vv_speaker_id", 1)),
        }
    st.info(f"TTS設定: provider={provider_key}, options={tts_options}")

    # BGM設定: 永続ストアから読み取り
    _bgm_enabled = st.session_state.get("_bgm_enabled", False)
    _bgm_file = st.session_state.get("_bgm_file", "")
    _bgm_volume = st.session_state.get("_bgm_volume", 0.15)

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
        bgm_enabled=_bgm_enabled,
        bgm_file=_bgm_file,
        bgm_volume=_bgm_volume,
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
            # --- 外部動画ファイルモード ---
            if (
                image_source == "外部動画ファイル（ナレーションオーバーレイ）"
                and external_video_path_value
            ):
                ext_video = resolve_path(external_video_path_value)
                if not ext_video.exists():
                    st.error(f"動画ファイルが見つかりません: {ext_video}")
                    st.stop()

                # 手動タイムスタンプをリスト形式に変換
                manual_ts = st.session_state.get("manual_timestamps", {})
                max_slide_num = max(e.number for e in entries)
                ts_list = []
                for i in range(max_slide_num):
                    slide_num = i + 1  # 1-indexed
                    ts_list.append(manual_ts.get(slide_num, 0.0))

                st.info(
                    f"外部動画ファイルでナレーションオーバーレイモードで生成します。"
                    f" ({ext_video.name})"
                )
                result_path = process_slides(
                    entries,
                    config,
                    full_video_path=ext_video,
                    slide_timestamps=ts_list,
                )

            # --- フル動画オーバーレイモードの自動検出 / 従来モード ---
            else:
                full_video = resolve_path("output/clips/full_presentation.webm")
                timestamps_file = resolve_path("output/clips/timestamps.json")

                if full_video.exists() and timestamps_file.exists():
                    # フル動画 + タイムスタンプが存在 → オーバーレイモード
                    import json as _json

                    ts_data = _json.loads(
                        timestamps_file.read_text(encoding="utf-8")
                    )
                    st.info(
                        "フル録画動画を検出しました。"
                        "ナレーションオーバーレイモードで生成します。"
                    )
                    result_path = process_slides(
                        entries,
                        config,
                        full_video_path=full_video,
                        slide_timestamps=ts_data["timestamps"],
                    )
                else:
                    # 従来モード: 動画クリップ or 静止画
                    vcd = None
                    if video_clips_dir_value:
                        vcd = resolve_path(video_clips_dir_value)
                    if vcd is None:
                        auto_clips = resolve_path("output/clips")
                        if auto_clips.is_dir() and (
                            any(auto_clips.glob("slide_*.webm"))
                            or any(auto_clips.glob("slide_*.mp4"))
                        ):
                            vcd = auto_clips
                            st.info(
                                "output/clips に動画クリップを検出しました。"
                                "動画クリップモードで生成します。"
                            )
                    result_path = process_slides(
                        entries, config, video_clips_dir=vcd
                    )

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
        st.markdown(
            '<div class="section-title"><span class="icon">✅</span> 生成結果</div>',
            unsafe_allow_html=True,
        )
        st.markdown(
            '<div class="result-header"><h3>🎉 動画の生成が完了しました</h3></div>',
            unsafe_allow_html=True,
        )

        # 動画プレビュー
        st.video(str(video_path))

        # ダウンロードボタン
        with open(video_path, "rb") as vf:
            st.download_button(
                label="📥 動画をダウンロード",
                data=vf.read(),
                file_name=video_path.name,
                mime="video/mp4",
                use_container_width=True,
            )
