# Fission 推奨技術スタック

> 調査日: 2026-02-23
> 基礎資料: [eda-tool-candidates.md](eda-tool-candidates.md) / [cad-engine-candidates.md](cad-engine-candidates.md)

## Fissionとは何か

既存のハードウェア設計環境（Fusion 360, Flux.ai等）は、ユーザーを閉じたエコシステムに閉じ込める。Fissionはその鎖を断ち切る。

**回路図 → PCB → ケース設計 → 製造** を、オープンなデータ形式とAIネイティブなインターフェースで一気通貫に行う環境。

---

## 推奨スタック一覧

| レイヤー | ツール | 役割 | ライセンス |
|---------|--------|------|-----------|
| 回路記述 | **SKiDL** | Pythonで回路を記述→ネットリスト生成 | MIT |
| 回路図 + PCB | **KiCad** | 回路図エディタ / PCBレイアウト / 製造出力 | GPL-3.0 |
| ケース設計（メイン） | **Build123d** | Pythonで3Dモデルを記述→STEP/STL出力 | Apache 2.0 |
| ケース設計（GUI補助） | **FreeCAD** | 人間がGUIで微調整する時に使用 | LGPL 2.1 |
| 品質チェック | **Trimesh** | メッシュ検証・干渉チェック | MIT |
| 統合レイヤー | **Fission** | 統一スキーマ / AIエージェント層 / CLI | MIT (予定) |

すべてPython。すべてオープンソース。すべてヘッドレス動作可能。

---

## アーキテクチャ

```
                        ┌─────────────────────────┐
                        │    Fission 統一スキーマ    │
                        │        (JSON)            │
                        └────────┬────────────────┘
                                 │
                 ┌───────────────┼───────────────┐
                 │               │               │
                 ▼               ▼               ▼
        ┌────────────┐  ┌────────────┐  ┌────────────────┐
        │  回路設計層  │  │  PCB設計層  │  │  ケース設計層   │
        │            │  │            │  │                │
        │  SKiDL     │  │  KiCad     │  │  Build123d     │
        │  (Python)  │  │  (S式)     │  │  (Python)      │
        └─────┬──────┘  └─────┬──────┘  └───────┬────────┘
              │               │                 │
              ▼               ▼                 ▼
        ネットリスト     Gerber/BOM/STEP     STEP/STL
              │               │                 │
              └───────────────┼─────────────────┘
                              ▼
                     ┌────────────────┐
                     │   製造発注      │
                     │ JLCPCB/PCBWay  │
                     │ 3Dプリント/CNC  │
                     └────────────────┘

        ─── 全レイヤーを横断 ───

        ┌─────────────────────────────────┐
        │        AIエージェント層           │
        │  Claude Code / MCP / 任意のLLM   │
        └─────────────────────────────────┘

        ─── 人間が必要な時だけ ───

        ┌─────────────────────────────────┐
        │       FreeCAD (GUI補助)          │
        │  Build123d STEP → GUI微調整      │
        │  KiCadStepUp でPCB形状も確認可能  │
        └─────────────────────────────────┘
```

---

## なぜこの組み合わせか

### 回路設計: KiCad + SKiDL

**30以上のEDAツールを調査した結果、KiCadが圧倒的。議論の余地がない。**

| 判断基準 | KiCad | 次点 (Horizon EDA) | 商用最有力 (Flux.ai) |
|---------|-------|-------------------|---------------------|
| ファイル形式 | S式プレーンテキスト | JSON | 非公開・持ち出し不可 |
| ヘッドレスCLI | Gerber/BOM/STEP/DRC/ERC全対応 | 部分的 | なし |
| Python API | 4種類（公式+サードパーティ） | 限定的 | なし |
| AI連携実績 | MCP Server, Circuit-Synth等 | なし | ブラウザ内CoPilotのみ |
| コミュニティ | 30年の歴史、CERN支援 | 小規模 | VCスタートアップ |
| オフライン | 完全対応 | 完全対応 | 不可 |

**SKiDLを補助的に使う理由:**
- AIが回路を生成する場合、S式を直接書くよりPython DSLのほうが正確
- ERC（電気ルールチェック）内蔵で、生成時点でエラーを検出
- KiCadのネットリストを生成するので、既存ワークフローとシームレスに統合

```python
# AIが生成するコードのイメージ（SKiDL）
from skidl import *

esp32 = Part("MCU_Espressif", "ESP32-WROOM-32",
             footprint="RF_Module:ESP32-WROOM-32")
led = Part("Device", "LED",
           footprint="LED_SMD:LED_0603_1608Metric")
r = Part("Device", "R", value="330",
         footprint="Resistor_SMD:R_0402_1005Metric")

esp32["GPIO2"] += r[1]
r[2] += led["A"]
led["K"] += Net("GND")

generate_netlist()
```

### ケース設計: Build123d

**12のCADツールを調査した結果、STEP出力必須でOCCTカーネル系に絞られ、その中でBuild123dが最適。**

| 判断基準 | Build123d | CadQuery (次点) | OpenSCAD | FreeCAD |
|---------|-----------|----------------|----------|---------|
| STEP出力 | 対応 | 対応 | **不可** | 対応 |
| AI生成適性 | `box - hole` が最高 | Fluent APIも良い | 独自DSL | APIが冗長 |
| Pythonic度 | for/if/変数が自然 | メソッドチェーンの制約 | - | 低レベル |
| インストール | pip | conda推奨 | - | 重量級 |
| ライセンス | Apache 2.0 | Apache 2.0 | GPLv2 | LGPL 2.1 |

**Build123dを第一候補にする理由:**
- **Algebra Mode (`result = box - hole`) はLLMが最も正確にコード生成できるAPI設計**
- CadQueryと同じOCCTカーネル（OCP）を共有、相互運用可能
- CadQueryのFluent APIの限界（for/ifの挿入しにくさ）を克服した後継プロジェクト

```python
# AIが生成するコードのイメージ（Build123d）
from build123d import *

# PCBの寸法（Fissionスキーマから取得）
pcb_width, pcb_length, pcb_height = 80, 60, 1.6
wall = 2.0
clearance = 1.0

# ケース外殻
outer = Box(pcb_width + wall*2 + clearance*2,
            pcb_length + wall*2 + clearance*2,
            pcb_height + 15 + wall)

# 内部空洞
inner = Box(pcb_width + clearance*2,
            pcb_length + clearance*2,
            pcb_height + 15)
inner = Pos(0, 0, wall) * inner

case = outer - inner

# USBコネクタ開口部（位置はスキーマから）
usb_opening = Box(12, wall*3, 8)
usb_opening = Pos(30, pcb_length/2 + wall, wall + pcb_height + 2) * usb_opening

case = case - usb_opening

case.export_step("enclosure.step")
```

**CadQueryをフォールバックとして保持する理由:**
- Build123dはv1.0未満で破壊的変更リスクあり
- CadQueryのコミュニティ・エンクロージャ設計テンプレートが豊富
- 両者は同じOCPバインディングを共有し、オブジェクト相互変換可能

### GUI補助: FreeCAD

Build123dはコードファーストでGUIを持たない。人間がマウスで形状を微調整したい場面では、**FreeCADをGUI補助ツールとして使う**。

```
AIが設計する時:
  Build123d (Python) → STEP出力 → 製造

人間がGUIで微調整したい時:
  Build123d (Python) → STEP → FreeCADで開いてGUI編集 → STEP保存 → 製造
```

**片道フロー（FreeCAD→Build123dには戻さない）。** STEPに書き出した時点でパラメトリック情報は消えるため、Build123dに戻しても「ただの固まり」にしかならない。パラメトリックな設計変更はBuild123dのPythonコード側で行う。

FreeCADを補助に据える理由:
- **v1.0到達の成熟したOSS CAD**（~22,000 stars）
- **KiCadStepUpプラグイン**でKiCad PCBの3D形状をそのまま確認可能
- **フル機能のGUI** — フィレット、面取り、穴あけ等の対話的操作
- **Python API**も持つが、Build123dに比べて冗長でAI生成には不向き（だからメインにしない）

### 品質チェック: Trimesh

- 生成されたSTL/STEPの検証・修復
- ケースとPCBの干渉チェック
- 製造可能性の基本検証

---

## データフロー詳細

### Phase 1: 回路設計

```
[ユーザー仕様 / AI生成]
         │
         ▼
    SKiDL (Python)          ← AIが書く / 人間が書く
         │
         ▼
    ネットリスト (.net)
         │
         ▼
    KiCad 回路図 (.kicad_sch)  ← kicad-sch-api で生成 or KiCad GUIで編集
         │
         ▼
    ERC (kicad-cli sch erc)
```

### Phase 2: PCB設計

```
    ネットリスト + 回路図
         │
         ▼
    KiCad PCBレイアウト (.kicad_pcb)  ← 人間がGUIで / AIが提案
         │
         ▼
    DRC (kicad-cli pcb drc)
         │
         ├──→ Gerber (kicad-cli pcb export gerbers)
         ├──→ BOM (kicad-cli sch export bom)
         ├──→ ドリル (kicad-cli pcb export drill)
         ├──→ PnP (kicad-cli pcb export pos)
         └──→ STEP 3Dモデル (kicad-cli pcb export step)
```

### Phase 3: ケース設計

```
    PCBのSTEP 3Dモデル
         │
         ▼
    Fission統一スキーマ (JSON)
    ├── PCB外形 (幅・奥行・厚さ)
    ├── マウントホール位置
    ├── コネクタ位置・寸法
    ├── 部品の最大高さ
    └── 基板端からのクリアランス
         │
         ▼
    Build123d (Python)        ← AIが書く / テンプレートから生成
         │
         ├──→ ケースSTEP (CNC加工 / 射出成型)
         └──→ ケースSTL (3Dプリント)
         │
         ├──→ [オプション] FreeCADでGUI微調整 → STEP保存
         │
         ▼
    Trimesh 品質チェック
    ├── メッシュ整合性
    ├── ケース↔PCB干渉チェック
    └── 壁厚の最小値検証
```

---

## Fission統一スキーマ（構想）

各レイヤーをつなぐ中間表現。KiCadのS式でもBuild123dのPythonでもない、Fission独自のJSON。

```json
{
  "project": "sensor-board-v1",
  "pcb": {
    "outline": { "width": 80.0, "length": 60.0, "thickness": 1.6 },
    "mount_holes": [
      { "x": 5.0, "y": 5.0, "diameter": 3.2 },
      { "x": 75.0, "y": 5.0, "diameter": 3.2 },
      { "x": 5.0, "y": 55.0, "diameter": 3.2 },
      { "x": 75.0, "y": 55.0, "diameter": 3.2 }
    ],
    "connectors": [
      {
        "type": "USB-C",
        "position": { "x": 40.0, "y": 60.0, "z": 1.6 },
        "dimensions": { "width": 9.0, "height": 3.2, "depth": 7.5 },
        "edge": "top"
      }
    ],
    "max_component_height": { "top": 12.0, "bottom": 2.5 }
  },
  "enclosure": {
    "wall_thickness": 2.0,
    "clearance": 1.0,
    "material": "PLA",
    "split": "horizontal"
  }
}
```

このスキーマが:
- **KiCad側**: PCBファイルから自動抽出（kicad-cli + S式パーサー）
- **Build123d側**: ケース設計のパラメータとして自動投入
- **AI側**: 読み書きして設計意図を理解・修正

---

## なぜ商用ツールではだめか

### vs Fusion 360
- ソフトとしてポンコツ（ユーザー実体験）
- 回路設計→PCB→ケースは一応できるがUXが悪い
- サブスクリプション依存、オフライン制限あり
- AIネイティブではない

### vs Flux.ai
- **データロックイン**: 設計ソースの持ち出し不可。Flux倒産=データ消滅
- **ケース設計不可**: 回路図+PCBまでしかない
- **API/プログラマティック操作なし**: ブラウザ内完結、外部AIと連携不可
- **オフライン不可**: クラウド専用
- **VC資金リスク**: 2021年シード$12Mのみ、追加調達情報なし
- Fissionが反抗する「閉じたエコシステム」そのもの

### vs Altium Designer
- 独自バイナリ形式（閉鎖的）
- ~$3,000/年のサブスクリプション
- AI機能なし
- ケース設計は別途必要

### vs Allegro X AI
- AIによる配置・ルーティングは最先端だが、~$4,000/年〜
- 独自バイナリ形式（最も閉鎖的）
- エンタープライズ専用

**共通する問題**: 閉じたフォーマット、ベンダーロックイン、AIの後付け感。
**Fissionの答え**: オープンなデータ、ユーザーが所有、AIがファーストクラス。

---

## リスクと課題

### 技術的リスク

| リスク | 影響 | 対策 |
|--------|------|------|
| Build123dがv1.0前で不安定 | API破壊的変更 | CadQueryをフォールバックに。両者はOCP共有で相互運用可 |
| KiCad IPC APIが未成熟 | 回路図のプログラマティック操作に制約 | kicad-sch-api / S式直接操作で回避 |
| KiCad S式がバージョン間で変更 | スキーマ抽出の互換性 | バージョン検出+アダプタパターン |
| PCBレイアウトのAI自動化は超難問 | 完全自動は非現実的 | 「AIが提案、人間がレビュー」モデル |

### スコープのリスク

| リスク | 対策 |
|--------|------|
| 全部作ろうとして何も完成しない | Phase 1（統一スキーマ）に集中。最小限のKiCad→Build123dパイプラインをまず動かす |
| 「AIが全自動で設計」を期待されすぎる | 商用ツールも含め、業界全体が「AI提案+人間レビュー」モデル。Fissionもそこを目指す |

---

## 次のステップ

### Phase 1: 統一スキーマ + 最小パイプライン

1. KiCadのPCBファイル（.kicad_pcb）をパースして基板外形・コネクタ位置を抽出
2. Fission統一スキーマ（JSON）を定義
3. スキーマからBuild123dのPythonコードを生成してケースSTEPを出力

**これだけで「KiCad PCB → ケース設計」のMVPが動く。**

### Phase 2: AI統合

4. Claude Code / MCPでスキーマを読み書きするエージェント層
5. SKiDLでの回路記述→KiCadプロジェクト生成

### Phase 3: 製造直結

6. kicad-cliでGerber/BOM一括出力
7. JLCPCB/PCBWay発注データの自動生成
