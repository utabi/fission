# Fission インストールガイド

## 必要な環境

| 項目 | 要件 |
|------|------|
| Python | 3.10 以上 |
| OS | macOS / Linux / Windows |
| KiCad | 9.0 以上（`kicad-cli` が必要） |

## クイックスタート

```bash
git clone https://github.com/your-org/fission.git
cd fission
pip install -e .
```

これで `fission` コマンドが使えるようになる。

```bash
fission --version
```

## 依存関係

`pip install -e .` で以下が自動インストールされる:

| パッケージ | 用途 |
|-----------|------|
| build123d | ケース設計（3D CAD エンジン） |
| skidl | 回路記述（Python DSL → ネットリスト） |
| trimesh | メッシュ検証・干渉チェック |
| click | CLI フレームワーク |

## 外部ツール（別途インストールが必要）

### KiCad（必須）

Fission は内部で `kicad-cli` を呼び出して Gerber/BOM/STEP 等を出力する。

**macOS:**
```bash
brew install --cask kicad
```

**Linux (Ubuntu/Debian):**
```bash
sudo add-apt-repository ppa:kicad/kicad-9.0-releases
sudo apt update
sudo apt install kicad
```

**Windows:**

https://www.kicad.org/download/windows/ からインストーラをダウンロード。

**インストール確認:**
```bash
kicad-cli version
```

### FreeCAD（オプション）

ケース設計を GUI で微調整したい場合のみ必要。

**macOS:**
```bash
brew install --cask freecad
```

**Linux:**
```bash
sudo apt install freecad
```

**Windows:**

https://www.freecad.org/downloads.php からダウンロード。

### ocp_vscode（オプション・推奨）

VSCode 内で Build123d の 3D モデルをリアルタイムプレビューする拡張機能。

VSCode の拡張機能マーケットプレイスから `OCP CAD Viewer` をインストール。

## インストール確認

```bash
# Fission 本体
fission --version

# KiCad CLI
kicad-cli version

# Python 依存関係の確認
fission doctor
```

`fission doctor` は全依存関係のバージョンと状態をチェックし、不足があれば対処法を表示する。

```
$ fission doctor

✓ Python 3.12.1
✓ build123d 0.10.0
✓ skidl 8.0.0
✓ trimesh 4.0.0
✓ kicad-cli 9.0.0
○ FreeCAD 1.0.0 (オプション)
○ ocp_vscode (オプション - VSCode拡張)

All checks passed.
```

## 開発環境セットアップ

Fission 自体の開発に参加する場合:

```bash
git clone https://github.com/your-org/fission.git
cd fission
pip install -e ".[dev]"
```

`[dev]` で追加される開発ツール:

| パッケージ | 用途 |
|-----------|------|
| pytest | テスト |
| ruff | リンター・フォーマッター |
| mypy | 型チェック |

```bash
# テスト実行
pytest

# リント
ruff check .

# 型チェック
mypy src/fission
```

## トラブルシューティング

### build123d のインストールに失敗する（Apple Silicon Mac）

`cadquery-ocp` が PyPI で Apple Silicon 向けバイナリを提供していない場合がある。

```bash
# conda 経由で OCP をインストールしてから
conda install -c cadquery -c conda-forge cadquery-ocp
pip install -e .
```

### `kicad-cli` が見つからない

KiCad をインストールしたがパスが通っていない場合:

**macOS:**
```bash
# KiCad.app 内の CLI にシンボリックリンクを張る
sudo ln -s /Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli /usr/local/bin/kicad-cli
```

**Windows:**

KiCad のインストールディレクトリ（通常 `C:\Program Files\KiCad\9.0\bin`）を PATH 環境変数に追加。

### FreeCAD の Python API を使いたい

FreeCAD はスタンドアロンアプリケーションとしてインストールするだけでよい。Fission は FreeCAD の Python API を直接呼び出すのではなく、STEP ファイル経由で連携する。
