# 紙芝居動画ジェネレーター

Markdown台本 + スライド画像 → ナレーション付きMP4動画を自動生成

## クイックスタート

### 1. セットアップ（初回のみ）

`install.bat` をダブルクリック

- Python・FFmpegの確認
- 仮想環境の作成とパッケージのインストール
- `config.json` の初期作成

### 2. 起動

`start.bat` をダブルクリック → ブラウザが自動で開きます

### 3. 使い方

1. 台本ファイル（`input/script.md`）を編集する
2. スライド画像を `input/images/` に配置する（ファイル名順に並べる）
3. ブラウザ上で設定を確認し「動画生成」ボタンをクリック
4. 完成した動画を `output/` フォルダから取得する

## 必要なもの

| ツール | 用途 | 入手先 |
|--------|------|--------|
| Python 3.10以上 | アプリの実行環境 | https://www.python.org/downloads/ |
| FFmpeg | 動画・音声の結合処理 | `winget install FFmpeg` または https://ffmpeg.org/download.html |
| Google Cloud TTSのAPIキー | 音声合成（Google TTS使用時） | https://cloud.google.com/ |

## フォルダ構成

```
911-plan/
├── install.bat          # セットアップ（初回のみ実行）
├── start.bat            # アプリ起動
├── app.py               # Web UI
├── generate_video.py    # 動画生成エンジン
├── requirements.txt     # Pythonパッケージ一覧
├── config.json          # 設定ファイル（install.bat が自動作成）
├── config.example.json  # 設定テンプレート
├── input/
│   ├── script.md        # 台本ファイル
│   └── images/          # スライド画像を配置するフォルダ
└── output/              # 生成された動画の保存先
```

## TTS設定

### Google Cloud TTS（デフォルト）

1. [Google Cloud Console](https://console.cloud.google.com/) でText-to-Speech APIを有効化する
2. サービスアカウントキー（JSONファイル）をダウンロードする
3. `config.json` の `tts.provider` が `"google"` になっていることを確認する
4. ブラウザUI上でJSONキーファイルのパスを設定する

### VOICEVOX（無料・ローカル）

1. [VOICEVOX](https://voicevox.hiroshiba.jp/) をインストールして起動しておく
2. `config.json` の `tts.provider` を `"voicevox"` に変更する

## 台本の書き方

```markdown
# スライドタイトル

ここに読み上げるナレーションを書きます。
1枚のスライドに対して1つのセクション（#）を書きます。

# 次のスライド

次のスライドのナレーションです。
```

スライド画像はファイル名のアルファベット・数字順に台本のセクションと対応します。
