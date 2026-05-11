#!/usr/bin/env python3
"""VOICEVOX 話者一覧ページ."""

from __future__ import annotations

import streamlit as st

st.set_page_config(
    page_title="VOICEVOX 話者一覧",
    page_icon="🎙",
    layout="wide",
)

# ---------------------------------------------------------------------------
# カスタム CSS
# ---------------------------------------------------------------------------

st.markdown(
    """
<style>
@import url('https://fonts.googleapis.com/css2?family=Noto+Sans+JP:wght@300;400;500;700&display=swap');

.stApp {
    font-family: 'Noto Sans JP', sans-serif;
}

.block-container {
    padding-top: 1rem !important;
    max-width: 1100px !important;
}

/* ヘッダー */
.app-header {
    background: linear-gradient(135deg, #43e97b 0%, #38f9d7 50%, #667eea 100%);
    border-radius: 16px;
    padding: 2rem 2.5rem;
    margin-bottom: 1.5rem;
    color: white;
    position: relative;
    overflow: hidden;
    box-shadow: 0 10px 40px rgba(67, 233, 123, 0.3);
}
.app-header h1 {
    margin: 0;
    font-size: 2rem;
    font-weight: 700;
}
.app-header p {
    margin: 0.5rem 0 0 0;
    font-size: 1rem;
    opacity: 0.9;
}

/* セクションタイトル */
.section-title {
    font-size: 1.3rem;
    font-weight: 700;
    margin: 1.5rem 0 0.8rem 0;
    padding-bottom: 0.4rem;
    border-bottom: 3px solid;
    border-image: linear-gradient(90deg, #667eea, #764ba2) 1;
}

/* カード */
.speaker-card {
    background: linear-gradient(135deg, #f8f9ff 0%, #f0f2ff 100%);
    border: 1px solid #e0e4f5;
    border-radius: 12px;
    padding: 1rem 1.2rem;
    margin-bottom: 0.5rem;
    transition: all 0.2s ease;
}
.speaker-card:hover {
    box-shadow: 0 4px 15px rgba(102, 126, 234, 0.15);
    transform: translateY(-1px);
}

/* テーブルスタイル */
.styled-table {
    width: 100%;
    border-collapse: separate;
    border-spacing: 0;
    border-radius: 12px;
    overflow: hidden;
    box-shadow: 0 2px 10px rgba(0,0,0,0.08);
    margin-bottom: 1.5rem;
}
.styled-table thead tr {
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    color: white;
}
.styled-table th {
    padding: 12px 16px;
    text-align: left;
    font-weight: 500;
    font-size: 0.9rem;
}
.styled-table td {
    padding: 10px 16px;
    font-size: 0.85rem;
    border-bottom: 1px solid #eee;
}
.styled-table tbody tr:nth-child(even) {
    background-color: #f8f9ff;
}
.styled-table tbody tr:hover {
    background-color: #eef0ff;
}

/* ID バッジ */
.id-badge {
    display: inline-block;
    background: linear-gradient(135deg, #667eea, #764ba2);
    color: white;
    border-radius: 6px;
    padding: 2px 10px;
    font-weight: 700;
    font-size: 0.85rem;
    min-width: 32px;
    text-align: center;
}

/* スタイルタグ */
.style-tag {
    display: inline-block;
    background: #e8eaff;
    color: #5a5ea0;
    border-radius: 20px;
    padding: 2px 12px;
    font-size: 0.8rem;
    font-weight: 500;
}

/* フィルターボックス */
.filter-box {
    background: linear-gradient(135deg, #f0f2ff 0%, #e8eaff 100%);
    border-radius: 12px;
    padding: 1rem 1.5rem;
    margin-bottom: 1.5rem;
    border: 1px solid #d0d4f0;
}

/* ボタン */
.stButton > button {
    border-radius: 8px !important;
    font-weight: 500 !important;
    transition: all 0.2s ease !important;
}
.stButton > button:hover {
    transform: translateY(-1px) !important;
    box-shadow: 0 4px 12px rgba(102, 126, 234, 0.3) !important;
}
</style>
""",
    unsafe_allow_html=True,
)

# ---------------------------------------------------------------------------
# データ
# ---------------------------------------------------------------------------

SPEAKERS: list[dict[str, str | int]] = [
    {"id": 0, "name": "四国めたん", "style": "あまあま"},
    {"id": 1, "name": "ずんだもん", "style": "あまあま"},
    {"id": 2, "name": "四国めたん", "style": "ノーマル"},
    {"id": 3, "name": "ずんだもん", "style": "ノーマル"},
    {"id": 4, "name": "四国めたん", "style": "セクシー"},
    {"id": 5, "name": "ずんだもん", "style": "セクシー"},
    {"id": 6, "name": "四国めたん", "style": "ツンツン"},
    {"id": 7, "name": "ずんだもん", "style": "ツンツン"},
    {"id": 8, "name": "春日部つむぎ", "style": "ノーマル"},
    {"id": 9, "name": "波音リツ", "style": "ノーマル"},
    {"id": 10, "name": "雨晴はう", "style": "ノーマル"},
    {"id": 11, "name": "玄野武宏", "style": "ノーマル"},
    {"id": 12, "name": "白上虎太郎", "style": "ふつう"},
    {"id": 13, "name": "青山龍星", "style": "ノーマル"},
    {"id": 14, "name": "冥鳴ひまり", "style": "ノーマル"},
    {"id": 15, "name": "九州そら", "style": "あまあま"},
    {"id": 16, "name": "九州そら", "style": "ノーマル"},
    {"id": 17, "name": "九州そら", "style": "セクシー"},
    {"id": 18, "name": "九州そら", "style": "ツンツン"},
    {"id": 19, "name": "九州そら", "style": "ささやき"},
    {"id": 20, "name": "もち子さん", "style": "ノーマル"},
    {"id": 21, "name": "剣崎雌雄", "style": "ノーマル"},
    {"id": 22, "name": "ずんだもん", "style": "ささやき"},
    {"id": 23, "name": "WhiteCUL", "style": "ノーマル"},
    {"id": 24, "name": "WhiteCUL", "style": "たのしい"},
    {"id": 25, "name": "WhiteCUL", "style": "かなしい"},
    {"id": 26, "name": "WhiteCUL", "style": "びえーん"},
    {"id": 27, "name": "後鬼", "style": "人間ver."},
    {"id": 28, "name": "後鬼", "style": "ぬいぐるみver."},
    {"id": 29, "name": "No.7", "style": "ノーマル"},
    {"id": 30, "name": "No.7", "style": "アナウンス"},
    {"id": 31, "name": "No.7", "style": "読み聞かせ"},
    {"id": 32, "name": "白上虎太郎", "style": "わーい"},
    {"id": 33, "name": "白上虎太郎", "style": "びくびく"},
    {"id": 34, "name": "白上虎太郎", "style": "おこ"},
    {"id": 35, "name": "白上虎太郎", "style": "びえーん"},
    {"id": 36, "name": "四国めたん", "style": "ささやき"},
    {"id": 37, "name": "四国めたん", "style": "ヒソヒソ"},
    {"id": 38, "name": "ずんだもん", "style": "ヒソヒソ"},
    {"id": 39, "name": "玄野武宏", "style": "喜び"},
    {"id": 40, "name": "玄野武宏", "style": "ツンギレ"},
    {"id": 41, "name": "玄野武宏", "style": "悲しみ"},
    {"id": 42, "name": "ちび式じい", "style": "ノーマル"},
    {"id": 43, "name": "櫻歌ミコ", "style": "ノーマル"},
    {"id": 44, "name": "櫻歌ミコ", "style": "第二形態"},
    {"id": 45, "name": "櫻歌ミコ", "style": "ロリ"},
    {"id": 46, "name": "小夜/SAYO", "style": "ノーマル"},
    {"id": 47, "name": "ナースロボ_タイプT", "style": "ノーマル"},
    {"id": 48, "name": "ナースロボ_タイプT", "style": "楽々"},
    {"id": 49, "name": "ナースロボ_タイプT", "style": "恐怖"},
    {"id": 50, "name": "ナースロボ_タイプT", "style": "内緒話"},
    {"id": 51, "name": "聖騎士 紅桜", "style": "ノーマル"},
    {"id": 52, "name": "雀松朱司", "style": "ノーマル"},
    {"id": 53, "name": "麒ヶ島宗麟", "style": "ノーマル"},
    {"id": 54, "name": "春歌ナナ", "style": "ノーマル"},
    {"id": 55, "name": "猫使アル", "style": "ノーマル"},
    {"id": 56, "name": "猫使アル", "style": "おちつき"},
    {"id": 57, "name": "猫使アル", "style": "うきうき"},
    {"id": 58, "name": "猫使ビィ", "style": "ノーマル"},
    {"id": 59, "name": "猫使ビィ", "style": "おちつき"},
    {"id": 60, "name": "猫使ビィ", "style": "人見知り"},
    {"id": 61, "name": "中国うさぎ", "style": "ノーマル"},
    {"id": 62, "name": "中国うさぎ", "style": "おどろき"},
    {"id": 63, "name": "中国うさぎ", "style": "こわがり"},
    {"id": 64, "name": "中国うさぎ", "style": "へろへろ"},
    {"id": 65, "name": "波音リツ", "style": "クイーン"},
    {"id": 66, "name": "もち子さん", "style": "セクシー/あん子"},
    {"id": 67, "name": "栗田まろん", "style": "ノーマル"},
    {"id": 68, "name": "あいえるたん", "style": "ノーマル"},
    {"id": 69, "name": "満別花丸", "style": "ノーマル"},
    {"id": 70, "name": "満別花丸", "style": "元気"},
    {"id": 71, "name": "満別花丸", "style": "ささやき"},
    {"id": 72, "name": "満別花丸", "style": "ぶりっ子"},
    {"id": 73, "name": "満別花丸", "style": "ボーイ"},
    {"id": 74, "name": "琴詠ニア", "style": "ノーマル"},
]

# 話者名のユニークリスト
SPEAKER_NAMES = sorted(set(s["name"] for s in SPEAKERS))

# ---------------------------------------------------------------------------
# ヘッダー
# ---------------------------------------------------------------------------

st.markdown(
    """
<div class="app-header">
    <h1>VOICEVOX 話者一覧</h1>
    <p>話者ID・スタイルのリファレンス &mdash; 設定画面で使うIDを確認できます</p>
</div>
""",
    unsafe_allow_html=True,
)

# ---------------------------------------------------------------------------
# フィルター
# ---------------------------------------------------------------------------

col1, col2, col3 = st.columns([2, 2, 1])
with col1:
    search = st.text_input(
        "話者名で検索",
        placeholder="例: ずんだもん",
        key="speaker_search",
    )
with col2:
    selected_names = st.multiselect(
        "話者で絞り込み",
        options=SPEAKER_NAMES,
        key="speaker_filter",
    )
with col3:
    st.markdown("<br>", unsafe_allow_html=True)
    show_all = st.checkbox("全表示", value=True, key="show_all")

# フィルタリング
filtered = SPEAKERS
if search:
    filtered = [s for s in filtered if search.lower() in str(s["name"]).lower()]
if selected_names:
    filtered = [s for s in filtered if s["name"] in selected_names]

st.markdown(
    f'<p style="color:#888; font-size:0.85rem;">'
    f"{len(filtered)} 件 / 全 {len(SPEAKERS)} 件</p>",
    unsafe_allow_html=True,
)

# ---------------------------------------------------------------------------
# テーブル表示
# ---------------------------------------------------------------------------

if filtered:
    # 話者ごとにグルーピング
    grouped: dict[str, list[dict]] = {}
    for s in filtered:
        name = str(s["name"])
        grouped.setdefault(name, []).append(s)

    # グループごとにカード表示
    for speaker_name, styles in grouped.items():
        ids_display = " / ".join(str(s["id"]) for s in styles)
        styles_display = "、".join(str(s["style"]) for s in styles)

        with st.expander(
            f"{speaker_name}  (ID: {ids_display})",
            expanded=show_all,
        ):
            table_rows = ""
            for s in styles:
                table_rows += (
                    f"<tr>"
                    f'<td><span class="id-badge">{s["id"]}</span></td>'
                    f"<td><strong>{s['name']}</strong></td>"
                    f'<td><span class="style-tag">{s["style"]}</span></td>'
                    f"</tr>"
                )

            st.markdown(
                f"""
<table class="styled-table">
    <thead>
        <tr><th>ID</th><th>話者名</th><th>スタイル</th></tr>
    </thead>
    <tbody>
        {table_rows}
    </tbody>
</table>
""",
                unsafe_allow_html=True,
            )

else:
    st.info("該当する話者が見つかりません。")

# ---------------------------------------------------------------------------
# フッター: 使い方ガイド
# ---------------------------------------------------------------------------

st.markdown(
    '<div class="section-title">使い方</div>',
    unsafe_allow_html=True,
)

st.markdown(
    """
1. 使いたい話者の **ID** をメモする
2. メインページの **TTS設定** で **VOICEVOX** を選択
3. **話者ID** に番号を入力する
4. VOICEVOXエンジンが起動していることを確認して動画を生成

> **注意**: 利用可能なIDはインストールしているVOICEVOXのバージョンと
> ダウンロード済みの音声ライブラリによって異なります。
> 上記リストは標準インストール時の一覧です。
"""
)

# ---------------------------------------------------------------------------
# ライブ取得ボタン
# ---------------------------------------------------------------------------

st.markdown(
    '<div class="section-title">VOICEVOXエンジンからライブ取得</div>',
    unsafe_allow_html=True,
)

st.markdown(
    "VOICEVOXが起動中なら、実際にインストールされている話者を取得できます。"
)

base_url = st.text_input(
    "VOICEVOX Base URL",
    value="http://localhost:50021",
    key="vv_base_url",
)

if st.button("話者を取得"):
    import requests  # noqa: E402

    try:
        resp = requests.get(f"{base_url}/speakers", timeout=5)
        resp.raise_for_status()
        speakers_live = resp.json()

        live_rows = ""
        count = 0
        for speaker in speakers_live:
            name = speaker.get("name", "?")
            for style in speaker.get("styles", []):
                style_name = style.get("name", "?")
                style_id = style.get("id", "?")
                count += 1
                live_rows += (
                    f"<tr>"
                    f'<td><span class="id-badge">{style_id}</span></td>'
                    f"<td><strong>{name}</strong></td>"
                    f'<td><span class="style-tag">{style_name}</span></td>'
                    f"</tr>"
                )

        st.success(f"VOICEVOXから {count} 件の話者スタイルを取得しました")
        st.markdown(
            f"""
<table class="styled-table">
    <thead>
        <tr><th>ID</th><th>話者名</th><th>スタイル</th></tr>
    </thead>
    <tbody>
        {live_rows}
    </tbody>
</table>
""",
            unsafe_allow_html=True,
        )

    except requests.ConnectionError:
        st.error(
            "VOICEVOXに接続できません。"
            "エンジンが起動していることを確認してください。"
        )
    except Exception as e:
        st.error(f"取得に失敗しました: {e}")
