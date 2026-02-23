# Fission EDAツール候補調査

> 調査日: 2026-02-23
> 目的: 回路図設計〜PCBレイアウトにおいて、AIネイティブに扱えるEDAツールの選定

## 選定基準

Fissionの回路図・PCB設計エンジンに求める要件:

1. **ファイルフォーマットがプレーンテキスト**（AIが読み書き・diffできる）
2. **Python API / プログラマティック操作**が可能
3. **ヘッドレス実行**（CLIで製造データ出力まで完結）
4. **Gerber / BOM / STEP出力**（製造直結）
5. **オープンソース**（ロックインなし）
6. **活発にメンテナンスされている**

---

## 総合比較

| ツール | 言語/API | ファイル形式 | ヘッドレス | 製造出力 | Stars | ライセンス | 推奨度 |
|--------|---------|------------|----------|---------|-------|-----------|--------|
| **KiCad** | Python/C++ | S式 (テキスト) | **kicad-cli** | Gerber/BOM/STEP | ~1,400(mirror) | GPL-3.0 | **S** |
| **SKiDL** | Python DSL | Python→ネットリスト | **完全** | KiCad経由 | ~1,200 | MIT | **A** |
| **atopile** | 独自言語(ato) | テキスト | 対応 | KiCad経由 | ~2,600 | MIT | **B** |
| **Horizon EDA** | C++/Python | JSON (テキスト) | 部分的 | Gerber/BOM | ~1,000 | GPL-3.0 | B |
| **LibrePCB** | C++ | S式 (テキスト) | 限定的 | Gerber | ~1,000 | GPL-3.0 | C |
| **TScircuit** | TypeScript/React | JSON | 対応 | Gerber | - | MIT | C |
| gEDA/PCB | C/Scheme | テキスト | 対応 | Gerber | - | GPL-2.0 | D (開発終了) |
| Fritzing | C++ | XML | 限定的 | Gerber | ~4,000 | GPL-3.0 | D (教育用) |

**結論: KiCadが圧倒的。議論の余地はほぼない。補助的にSKiDLを組み合わせるのが最適。**

---

## S候補: KiCad

| 項目 | 詳細 |
|------|------|
| 公式サイト | https://www.kicad.org/ |
| 開発リポジトリ | GitLab: https://gitlab.com/kicad/code/kicad |
| 最新版 | **KiCad 9.0.0** (2025-02-20) / KiCad 10 RC1テスト中 |
| ライセンス | GPL-3.0 |
| 歴史 | 1992年〜。CERNが2013年から開発貢献 |

### なぜKiCad一択か

1. **ファイルがS式プレーンテキスト** — git diff可能、LLMが直接読み書きできる
2. **kicad-cliで製造出力を完全自動化** — Gerber, BOM, STEP, DRC, ERCすべてCLIで実行可能
3. **Python APIが複数存在** — 用途に応じて選択可能
4. **MCP Serverが既に存在** — Claude等のLLMからの操作が実証済み
5. **業界標準のOSSEDA** — コミュニティ・ライブラリが圧倒的
6. **製造直結** — JLCPCB, PCBWay等への発注データを直接出力

他のOSS EDAは全て、KiCadに比べてコミュニティ・機能・エコシステムで大幅に劣る。

### ファイルフォーマット: S式（プレーンテキスト）

全ファイルがUTF-8テキスト。AIが直接パース・生成可能。

| 拡張子 | 用途 |
|--------|------|
| `.kicad_sch` | 回路図 |
| `.kicad_pcb` | PCBレイアウト |
| `.kicad_sym` | シンボルライブラリ |
| `.kicad_mod` | フットプリントライブラリ |
| `.kicad_pro` | プロジェクト設定 |

```lisp
;; .kicad_sch の例（回路図）
(kicad_sch
  (version 20231120)
  (generator "eeschema")
  (uuid "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx")
  (paper "A4")
  (symbol (lib_id "Device:R")
    (at 125 75 0)
    (property "Reference" "R1" ...)
    (property "Value" "10k" ...)
  )
  (wire (pts (xy 100 50) (xy 150 50)))
)
```

```lisp
;; .kicad_pcb の例（PCBレイアウト）
(kicad_pcb
  (version 20231014)
  (generator "pcbnew")
  (general (thickness 1.6))
  (layers
    (0 "F.Cu" signal)
    (31 "B.Cu" signal)
  )
  (footprint "Resistor_SMD:R_0402_1005Metric"
    (at 100 50)
    (pad "1" smd rect (at -0.48 0) (size 0.56 0.62)
      (layers "F.Cu" "F.Paste" "F.Mask")
      (net 1 "GND")
    )
  )
  (segment (start 100 50) (end 150 50) (width 0.25) (layer "F.Cu") (net 1))
)
```

### kicad-cli: 完全なヘッドレス製造パイプライン

```bash
# Gerber一括エクスポート
kicad-cli pcb export gerbers --output=./gerbers/ project.kicad_pcb

# ドリルファイル
kicad-cli pcb export drill --output=./gerbers/ project.kicad_pcb

# STEP 3Dモデル（トラック含む）
kicad-cli pcb export step --output=model.step --include-tracks project.kicad_pcb

# BOM
kicad-cli sch export bom --output=bom.csv project.kicad_sch

# DRC（デザインルールチェック）
kicad-cli pcb drc --output=drc_report.json project.kicad_pcb

# ERC（電気ルールチェック）
kicad-cli sch erc --output=erc_report.json project.kicad_sch

# Jobset一括実行（KiCad 9新機能）
kicad-cli jobset run project.kicad_jobset
```

### Python API（4つのアプローチ）

| API | 種別 | 対象 | ヘッドレス | 状態 |
|-----|------|------|----------|------|
| **pcbnew SWIG** | 公式同梱 | PCB | 可能 | メンテナンスモード |
| **IPC API + kicad-python** | 公式新API | PCB | 不可（GUI必要） | ベータ（KiCad 9〜） |
| **kicad-sch-api** | サードパーティ | 回路図 | 可能 | 活発 |
| **kicad-skip** | サードパーティ | S式全般 | 可能 | 活発 |

**注意:** IPC APIは現時点でPCBエディタのみ対応。回路図エディタAPIはKiCad 10でも未実装。
回路図のプログラマティック操作は `kicad-sch-api` またはS式直接操作で対応。

### 既存のAI/LLM連携プロジェクト

| プロジェクト | 概要 |
|-------------|------|
| **KiCAD MCP Server** | MCP経由でClaude等がKiCadを直接操作。64ツール提供 |
| **KiCad MCP (lamaalrajih)** | IPC API統合版MCPサーバー |
| **Circuit-Synth** | Python→KiCadプロジェクト自動生成。Claude Code連携前提 |
| **KiC-AI** | KiCad用AIチャットIF。Ollama統合 |

### KiCadの弱み（正直な評価）

- **IPC APIが未成熟** — 回路図API未実装、ヘッドレスIPC未対応
- **S式フォーマットがバージョン間で変わる可能性** — メジャーバージョン間の互換性リスク
- **高周波設計のサポートが限定的** — 信号完全性解析は不十分
- **SPICEシミュレーション** — ngspice内蔵だが高度な解析は外部ツール必要
- **SWIG APIがメンテナンスモード** — ヘッドレスPCB操作の既存手段が将来陳腐化リスク

ただし、これらはFissionが「KiCadの上に統合レイヤーを被せる」アプローチで補える弱点であり、KiCad自体を置き換える理由にはならない。

---

## A候補: SKiDL（補助ツールとして）

| 項目 | 詳細 |
|------|------|
| GitHub | https://github.com/devbisme/skidl |
| Stars | ~1,200 |
| ライセンス | MIT |
| 言語 | Python |

### 概要

Pythonコードで回路を記述し、KiCadネットリストを生成するDSL。GUIなし、コードファースト。

```python
from skidl import *

# ESP32 + LED回路をPythonで記述
esp32 = Part("MCU_Espressif", "ESP32-WROOM-32", footprint="RF_Module:ESP32-WROOM-32")
led = Part("Device", "LED", footprint="LED_SMD:LED_0603_1608Metric")
r = Part("Device", "R", value="330", footprint="Resistor_SMD:R_0402_1005Metric")

esp32["GPIO2"] += r[1]
r[2] += led["A"]
led["K"] += Net("GND")

generate_netlist()
```

### Fissionでの位置づけ

KiCadを置き換えるものではなく、**AIが回路を記述する際のフロントエンド**として有用。

```
[AIエージェント] → SKiDL (Pythonコード) → ネットリスト → KiCad PCBレイアウト → 製造出力
```

LLMはS式を直接書くよりも、SKiDLのPython DSLを生成するほうが正確。

### 強み
- **純粋なPython** — LLMが最も得意な言語で回路記述
- **ERC内蔵** — 電気ルールチェックをコード実行時に自動検証
- **階層設計** — 関数/クラスで回路モジュールを再利用
- **MIT ライセンス**

### 弱み
- **PCBレイアウトは別途KiCad必要** — ネットリスト生成まで
- **GUIプレビューなし** — 視覚的確認はKiCadで行う
- **KiCadライブラリに依存** — パーツ名・フットプリント名の正確な指定が必要

---

## B候補: atopile

| 項目 | 詳細 |
|------|------|
| GitHub | https://github.com/atopile/atopile |
| Stars | ~2,600 |
| ライセンス | MIT |
| 言語 | 独自言語 (ato) |

### 概要

「コードで回路を書く」コンセプトの新興プロジェクト。独自言語`ato`で回路を記述し、KiCad互換のネットリストにコンパイル。

```ato
module LEDCircuit:
    led = new LED
    resistor = new Resistor
    resistor.value = 330ohm

    signal vcc
    signal gnd

    vcc ~ resistor.p1
    resistor.p2 ~ led.anode
    led.cathode ~ gnd
```

### 評価

思想は面白いが、独自言語である点がFissionにはマイナス。LLMはPythonのほうが正確にコード生成できるため、SKiDLのほうがAI統合には向いている。

---

## 参考: 商用EDAのAI動向

Fissionの設計判断に影響しうる商用ツールのAI対応状況。

| ツール | AI機能 | ファイル形式 | 価格 |
|--------|--------|------------|------|
| **Flux.ai** | CoPilot（自然言語→回路設計） | 非公開 | Freemium |
| **Allegro X AI** | 強化学習ベースの配置・ルーティング自動化 | 独自バイナリ（閉鎖的） | ~$4,000/年〜 |
| **Quilter AI** | 物理ベースAIによるPCBレイアウト完全自動化 | KiCad/Altium経由 | 個人無料 |
| **CELUS** | テキスト/画像→システムアーキテクチャ自動生成 | 既存ツール経由 | 要問合せ |
| **Siemens EDA AI** | エージェンティックAI（NVIDIA NIM統合） | 独自 | エンタープライズ |
| **AllSpice** | Git + AI Agent（設計レビュー自動化） | CADアグノスティック | 要問合せ |
| Altium Designer | AI機能なし。Nexar GraphQL APIあり | 独自バイナリ | ~$3,000/年 |
| EasyEDA | AI機能なし。JSONフォーマット | JSON（オープン） | 無料 |
| EAGLE | **2026年6月サポート終了** | XML | Fusion内 |

### Flux.ai 詳細調査

クラウドベースのAI搭載EDA。Fissionとのスコープ比較のために詳細を調査した。

#### 対応機能

| 機能 | 対応状況 |
|------|---------|
| 回路図設計 | 対応 |
| PCBレイアウト | 対応 |
| AI CoPilot（部品選定・レビュー） | 対応 |
| AI CoPilot（回路自動生成） | 対応（精度は発展途上） |
| Gerber / BOM / PnP出力 | 対応 |
| ケース設計（3D CAD） | 基本的な自動エンクロージャのみ |
| 編集可能な設計ソースのエクスポート | 非対応（Gerber/BOMのみ） |
| オフライン動作 | 非対応（クラウド専用） |
| 外部API / プログラマティック操作 | 非対応 |
| 外部ツールからのインポート（KiCad/Altium等） | 非対応 |
| AIエンジンの選択 | Flux独自のみ |

#### Fissionとのスコープ比較

| 項目 | Flux.ai | Fission |
|------|---------|---------|
| データ形式 | クラウド上に保持 | プレーンテキスト（ローカル） |
| AI統合 | 内蔵CoPilot | 任意のLLM（Claude / GPT / Ollama等） |
| 設計範囲 | 回路図 + PCB | 回路図 → PCB → ケース → 製造 |
| オフライン | 非対応 | 対応 |
| 資金状況 | 2021年シード$12M |  OSS（KiCad / Build123d等の既存エコシステム上に構築） |

#### 所見

Flux.aiは「自然言語→回路設計」のUX面で先進的であり、AIとEDAの統合アプローチとして参考になる。一方、設計データのエクスポート制限、オフライン非対応、ケース設計の範囲外という点で、Fissionとはスコープが異なる。

### 商用から学ぶべきこと

- **Flux.ai**: 自然言語→回路設計のUXが先進的。AI統合のアプローチとして参考になる
- **Quilter AI**: PCBレイアウトのAI自動化は実用段階に入りつつある。KiCadとの統合もある
- **AllSpice**: ハードウェアのGitベースワークフロー（設計レビュー、CI/CD）は参考になる
- **共通点**: どの商用ツールも「AIが全自動で設計する」のではなく「AIが提案し、人間がレビューする」モデル

---

## Fissionへの推奨構成

```
[回路設計層]
  AIエージェント → SKiDL (Python DSL) → ネットリスト生成
                                            ↓
[PCB設計層]
  KiCad PCBエディタ（人間 + AI提案）← Fission統一スキーマ (JSON)
                                            ↓
[製造出力層]
  kicad-cli → Gerber / BOM / STEP / DRC / ERC
                                            ↓
[ケース設計層]
  STEP読み込み → Build123d (Python) → ケースSTEP/STL出力
                                            ↓
[品質チェック層]
  Trimesh → 干渉チェック → 製造発注
```

### KiCadでいいのか？

**はい、KiCadで間違いない。** 理由:

1. **唯一の成熟したOSS EDA** — 他の選択肢は機能・コミュニティで比較にならない
2. **ファイルがテキスト** — S式はLLMが読み書きできる。商用ツールのバイナリ形式では不可能
3. **CLIが完全** — 製造出力の自動化がGUI不要で可能
4. **AI連携が既に始まっている** — MCP Server, Circuit-Synth等の実証済みプロジェクトがある
5. **STEP出力** — PCBの3D形状をそのままケース設計（Build123d）に渡せる

**唯一の課題**は回路図のプログラマティック操作APIが公式に未整備な点だが、これはkicad-sch-apiやSKiDLで回避可能であり、Fissionが統合レイヤーとして補う領域でもある。
