# Fission

> 回路図 → PCB → ケース設計を、AIネイティブな環境で一気通貫に。

Fissionは、オープンでAIが参加できるハードウェア設計環境です。回路図・PCBレイアウト・ケース設計を統一データモデルでつなぎ、AIエージェントが読み書きし、推論できる設計環境を目指します。

## なぜFissionか

- すべての設計データは**プレーンテキスト**で、バージョン管理可能
- AIは後付けではなく、**最初からファーストクラスの参加者**
- データは常に**あなたのもの**
- 回路図からケース設計まで**一気通貫**で完結する

## 技術スタック

```
┌─────────────────────────────────────┐
│         Fission CLI (Python)         │
│  統一スキーマ / AIエージェント層 / 製造出力  │
└──────────────┬──────────────────────┘
               │
   ┌───────────┼───────────┐
   │           │           │
   ▼           ▼           ▼
 SKiDL       KiCad     Build123d
 回路記述    回路図+PCB   ケース設計
 (Python)    (S式)      (Python)
   │           │           │
   ▼           ▼           ▼
ネットリスト  Gerber     STEP/STL
             BOM
             STEP
               │
               ▼
          製造発注
       JLCPCB / PCBWay
       3Dプリント / CNC
```

| レイヤー | ツール | 役割 |
|---------|--------|------|
| 回路記述 | [SKiDL](https://github.com/devbisme/skidl) | Pythonで回路を記述→ネットリスト |
| 回路図 + PCB | [KiCad](https://www.kicad.org/) | 回路図エディタ / PCBレイアウト / 製造出力 |
| ケース設計 | [Build123d](https://github.com/gumyr/build123d) | Pythonで3Dモデル→STEP/STL |
| GUI補助 | [FreeCAD](https://www.freecad.org/) | 人間がGUIで微調整する時に使用（オプション） |
| 統合 | **Fission** | 統一スキーマ / CLI / AIエージェント層 |

すべてPython。すべてオープンソース。すべてヘッドレス動作可能。

## インストール

```bash
git clone https://github.com/your-org/fission.git
cd fission
pip install -e .
```

KiCad 9.0以上が別途必要。詳細は [INSTALL.md](INSTALL.md) を参照。

## 使い方

```bash
# プロジェクト初期化
fission init my-sensor-board

# KiCad PCBからスキーマ抽出（基板外形・コネクタ位置・マウントホール等）
fission extract my-sensor-board.kicad_pcb

# スキーマからケース自動生成
fission generate-case

# 製造データ一括出力（Gerber / BOM / ドリル / STEP）
fission export --all

# DRC + ERC + メッシュチェック一括実行
fission check

# 環境チェック
fission doctor
```

## Fission統一スキーマ

各レイヤーをつなぐ中間表現。KiCad PCBから自動抽出され、ケース設計のパラメータとして投入される。

```json
{
  "project": "sensor-board-v1",
  "pcb": {
    "outline": { "width": 80.0, "length": 60.0, "thickness": 1.6 },
    "mount_holes": [
      { "x": 5.0, "y": 5.0, "diameter": 3.2 },
      { "x": 75.0, "y": 55.0, "diameter": 3.2 }
    ],
    "connectors": [
      {
        "type": "USB-C",
        "position": { "x": 40.0, "y": 60.0, "z": 1.6 },
        "dimensions": { "width": 9.0, "height": 3.2 },
        "edge": "top"
      }
    ],
    "max_component_height": { "top": 12.0, "bottom": 2.5 }
  }
}
```

AIはこのスキーマを読んで「USBコネクタの開口部はここ」「基板のマウントポストはここ」と推論しながらケースを設計する。

## AIとの協働

Fissionは Claude Code / MCP / 任意のLLMと連携する。AIは：

- **SKiDL** のPythonコードを生成して回路を記述
- **Fissionスキーマ** を読み書きして設計意図を理解
- **Build123d** のPythonコードを生成してケースを設計
- **kicad-cli** を呼び出してDRC/ERCを実行・結果を解釈

```python
# AIが書く回路（SKiDL）
from skidl import *

esp32 = Part("MCU_Espressif", "ESP32-WROOM-32",
             footprint="RF_Module:ESP32-WROOM-32")
led = Part("Device", "LED", footprint="LED_SMD:LED_0603_1608Metric")
r = Part("Device", "R", value="330", footprint="Resistor_SMD:R_0402_1005Metric")

esp32["GPIO2"] += r[1]
r[2] += led["A"]
led["K"] += Net("GND")
```

```python
# AIが書くケース（Build123d）
from build123d import *

case = Box(84, 64, 20) - Pos(0, 0, 1) * Box(80, 60, 18)
usb_opening = Pos(0, 32, 5) * Box(12, 4, 8)
case = case - usb_opening

case.export_step("enclosure.step")
```

## ロードマップ

- [ ] Phase 1: Fission統一スキーマ定義 + KiCad PCBパーサー
- [ ] Phase 2: Build123dによるケース自動生成
- [ ] Phase 3: `fission` CLI（extract / generate-case / export / check）
- [ ] Phase 4: AIエージェント層（MCP Server / Claude Code統合）
- [ ] Phase 5: 製造発注フロー（JLCPCB / PCBWay直結）

## ドキュメント

- [INSTALL.md](INSTALL.md) — インストール手順
- [docs/recommended-stack.md](docs/recommended-stack.md) — 技術スタックの選定理由
- [docs/eda-tool-candidates.md](docs/eda-tool-candidates.md) — EDAツール調査
- [docs/cad-engine-candidates.md](docs/cad-engine-candidates.md) — CADエンジン調査

## ステータス

設計決定完了。Phase 1（統一スキーマ + KiCad PCBパーサー）に着手予定。

## ライセンス

MIT
