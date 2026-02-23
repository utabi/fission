# Fission CADエンジン候補調査

> 調査日: 2026-02-23
> 目的: KiCad PCB → ケース設計をAIネイティブに行うための、プログラマティックCADエンジンの選定

## 選定基準

Fissionのケース設計エンジンに求める要件:

1. **コードで3Dモデルを定義できる**（= AIが読み書きできる）
2. **STEP出力対応**（製造委託に必須）
3. **ヘッドレス実行**（GUIなしでCLI/スクリプトから動作）
4. **Pythonで書ける**（KiCadブリッジとの統一、AI生成の容易さ）
5. **オープンソース**（ロックインなし）
6. **活発にメンテナンスされている**

---

## 総合比較

| ツール | 言語 | CADカーネル | STEP出力 | ヘッドレス | Stars | ライセンス | 推奨度 |
|--------|------|------------|----------|-----------|-------|-----------|--------|
| **CadQuery** | Python | OCCT | **対応** | **対応** | ~4,500 | Apache 2.0 | **A** |
| **Build123d** | Python | OCCT | **対応** | **対応** | ~1,400 | Apache 2.0 | **A** |
| **FreeCAD Python API** | Python | OCCT | **対応** | **対応** | ~22,000 | LGPL 2.1 | **B** |
| **pythonOCC** | Python | OCCT | **対応** | **対応** | ~1,300 | LGPL 3.0 | **C** |
| OpenSCAD | 独自DSL | CGAL/Manifold | 非対応 | 対応 | ~8,900 | GPLv2 | D |
| SolidPython2 | Python | CGAL (OpenSCAD経由) | 非対応 | 対応 | ~1,200 | LGPL 2.1 | D |
| ImplicitCAD | Haskell/独自DSL | 独自(暗黙関数) | 非対応 | 対応 | ~1,500 | AGPL 3.0 | D |
| JSCAD | JavaScript | 独自(CSG) | 非対応 | 対応 | ~2,700 | MIT | D |
| Trimesh | Python | なし(メッシュのみ) | 非対応 | 対応 | ~2,000 | MIT | 補助用 |

**結論: STEP出力が必須のため、OCCTカーネル系（CadQuery / Build123d / FreeCAD / pythonOCC）が実質的な候補。**

---

## A候補: CadQuery

| 項目 | 詳細 |
|------|------|
| GitHub | https://github.com/CadQuery/cadquery |
| Stars | ~4,500 |
| 最新版 | 2.7.0 (2025-02-13) |
| ライセンス | Apache 2.0 |
| Python | 3.10 - 3.12 |
| カーネル | OpenCASCADE (OCCT) via OCP |
| インストール | conda推奨 / Docker公式イメージあり |

### APIスタイル: Fluent API（メソッドチェーン）

```python
import cadquery as cq

# 80x60x10のボックスにφ22の穴
result = (
    cq.Workplane("XY")
    .box(80.0, 60.0, 10.0)
    .faces(">Z")
    .workplane()
    .hole(22.0)
)

cq.exporters.export(result, "box_with_hole.step")
```

### 出力フォーマット
STEP, STL, DXF, SVG, AMF, 3MF, VRML, VTP, glTF/GLB

### 強み
- **成熟したAPI** — v2系で安定。ドキュメント・事例が豊富
- **ヘッドレス完全対応** — Docker公式イメージあり、CI/CDに組み込み可能
- **エンクロージャ設計の実績** — パラメトリックなケースジェネレータの事例多数
- **出力フォーマットが最多** — STEP, STL, DXF, glTFなど幅広い
- **AI生成との相性** — Fluent APIはLLMのコード生成に適している。CQAsk（AI→CadQuery生成）などの先行研究あり

### 弱み
- **Fluent APIの限界** — 複雑なモデルでは逆参照が困難。Pythonのfor/ifを自然に挿入しにくい
- **インストールが煩雑** — OCP依存でpip単独では困難な場合あり（conda推奨）
- **GUIが別プロジェクト** — cq-editorが必要（ただしFissionにはGUI不要）

### KiCad連携
- STEP/DXF経由での手動連携は可能
- KiCadからSTEPエクスポート → CadQueryでimport → ケース設計のワークフロー実績あり
- 専用プラグインは存在しない（Fissionが埋めるべきギャップ）

---

## A候補: Build123d

| 項目 | 詳細 |
|------|------|
| GitHub | https://github.com/gumyr/build123d |
| Stars | ~1,400 |
| 最新版 | 0.10.0 (2024-11-05) |
| ライセンス | Apache 2.0 |
| Python | 3.10 - 3.13 |
| カーネル | OpenCASCADE (OCCT) via OCP（CadQueryと同じ） |
| インストール | pip可能 |

### APIスタイル: 2つのモード

#### Algebra Mode（演算子方式） — AIに最適
```python
from build123d import *

box = Box(80, 60, 10)
hole = Cylinder(radius=11, height=10)
result = box - hole

result.export_step("box_with_hole.step")
```

#### Builder Mode（コンテキストマネージャ方式）
```python
from build123d import *

with BuildPart() as part:
    Box(80, 60, 10)
    Cylinder(radius=11, height=10, mode=Mode.SUBTRACT)

part.part.export_step("box_with_hole.step")
```

### 出力フォーマット
STEP, STL, 3MF, glTF/GLB, BREP, SVG, DXF

### 強み
- **よりPythonic** — 標準的なPythonのfor/if/変数が自然に使える（CadQueryの弱点を克服）
- **Algebra Modeが直感的** — `box - hole` のような数学的表現はAI生成に非常に向いている
- **CadQueryと相互運用可能** — 同じOCPバインディングを共有、オブジェクト相互変換可能
- **型チェック対応** — mypyサポート
- **bd_warehouse** — ネジ、ナットなど標準部品のパラメトリックライブラリ

### 弱み
- **v1.0未満** — API安定性の保証なし。破壊的変更の可能性
- **コミュニティが小さい** — CadQueryの1/3のスター数
- **Apple Silicon対応に追加手順** — M1/M2/M3 MacでOCPのインストールに手間

### CadQueryとの関係
Build123dの作者（gumyr）はCadQueryのコミュニティで活動していた人物。CadQueryのFluent APIの限界を克服するために設計された後継的プロジェクト。OCPバインディングを共有しており、段階的な移行が可能。

---

## B候補: FreeCAD Python API

| 項目 | 詳細 |
|------|------|
| GitHub | https://github.com/FreeCAD/FreeCAD |
| Stars | ~22,000 |
| 最新版 | 1.0.0 (2024-11) |
| ライセンス | LGPL 2.1 |
| カーネル | OpenCASCADE (OCCT) |

### 概要
FreeCADはGUI CADだが、Python APIでヘッドレスに操作可能。`freecad.app` モジュールをPythonからimportしてスクリプト的に3Dモデルを構築できる。

```python
import FreeCAD
import Part

doc = FreeCAD.newDocument()
box = Part.makeBox(80, 60, 10)
hole = Part.makeCylinder(11, 10)
result = box.cut(hole)

Part.export([result], "box_with_hole.step")
```

### 強み
- **最大のOSS CADプロジェクト** — コミュニティ・ドキュメントが圧倒的
- **KiCadStepUp プラグイン** — KiCad ↔ FreeCAD の連携が既に確立
- **フル機能のCADカーネル** — STEP/IGES/BREPなど全フォーマット対応
- **v1.0到達** — 成熟度が高い

### 弱み
- **重量級** — GUIアプリケーション全体をインストールする必要がある
- **Python APIが冗長** — CadQuery/Build123dに比べて記述量が多い
- **ヘッドレス運用のハードル** — 可能だが、設計思想はGUIファースト
- **AIコード生成には不向き** — APIが低レベルで、LLMが正確なコードを生成しにくい

### 評価
既にKiCadStepUpという連携の実績があり参考になるが、Fissionのエンジンとして組み込むには重すぎる。CadQuery/Build123dが内部的に同じOCCTカーネルを使っているため、FreeCADを経由する必要性は薄い。

---

## C候補: pythonOCC

| 項目 | 詳細 |
|------|------|
| GitHub | https://github.com/tpaviot/pythonocc-core |
| Stars | ~1,300 |
| 最新版 | 7.8.1 (2024) |
| ライセンス | LGPL 3.0 |
| カーネル | OpenCASCADE (OCCT) 直接バインディング |

### 概要
OCCTのPythonバインディングをほぼそのまま公開したもの。CadQueryやBuild123dの「下のレイヤー」にあたる。

### 強み
- OCCTの全機能にアクセスできる（最も低レベル）
- STEP/IGES/BREPなど全フォーマット対応

### 弱み
- **APIが極めて低レベル** — ケースを1つ作るのに数十行必要
- **ドキュメントが乏しい** — OCCT自体のドキュメントを読む必要がある
- **AI生成には不向き** — 抽象度が低すぎてLLMが扱いにくい

### 評価
直接使うツールではなく、CadQuery/Build123dの内部で使われている基盤技術。Fissionが直接触る必要はない。

---

## 落選: STEP非対応グループ

以下は全てSTEP出力に非対応のため、製造用途には不適。3Dプリント専用であれば使えるが、Fissionの「製造直結」ビジョンには合わない。

### OpenSCAD
- Stars: ~8,900 / 独自DSL / GPLv2
- 最大のテキストベースCADコミュニティ。ライブラリ豊富（BOSL2等）
- Manifoldバックエンドで劇的な性能向上（30分→3秒の事例）
- **致命的欠点: STEP出力不可**（メッシュベースカーネル）

### SolidPython2
- Stars: ~1,200 (オリジナル) / Python / LGPL 2.1
- OpenSCADのPythonラッパー。Pythonの全機能が使える
- **OpenSCADに完全依存 → STEP不可を継承**

### ImplicitCAD
- Stars: ~1,500 / Haskell / AGPL 3.0
- 角丸CSGがネイティブサポート（ケース設計に有利）
- コミュニティが小さい。**STEP不可**

### JSCAD (OpenJSCAD)
- Stars: ~2,700 / JavaScript / MIT
- ブラウザで動作するCSG CAD
- **STEP不可**。WebベースのプレビューUIとしては検討の余地あり

---

## 補助ツール

### Trimesh
- GitHub: https://github.com/mikedh/trimesh
- Stars: ~2,000 / Python / MIT
- 3Dメッシュの読み込み・解析・変換ライブラリ
- CADエンジンではないが、STLの検証・修復・干渉チェック等に使える
- Fissionのパイプラインで品質チェック用の補助ツールとして有用

---

## AI + CAD の先行事例

| プロジェクト | 概要 |
|-------------|------|
| **CQAsk** | 自然言語 → CadQueryコード生成。LLMでCADモデルを対話的に作成 |
| **Text-to-CadQuery研究** | 学術研究。テキスト記述からCadQueryコードをLLMで生成 |
| **Zoo.dev (旧KittyCAD)** | Text-to-CAD API。商用サービス。独自CADカーネル(KCL言語) |
| **FreeCAD + LLM実験** | FreeCADのPython APIをLLMで駆動する実験的プロジェクト |

**所見:** AIによるCADコード生成は、CadQuery/Build123dのようなPythonベースの宣言的APIで最も成功している。LLMは高レベルな抽象化（`Box`, `Cylinder`, `-` 演算子）を正確に生成できるが、低レベルAPI（pythonOCC, FreeCAD Part API）では精度が落ちる。

---

## Fissionへの推奨

### 第一候補: Build123d

**理由:**
1. **Algebra Mode (`box - hole`) がAI生成に最適** — LLMが最も正確にコードを生成できるAPI設計
2. **Pythonic** — for/if/変数が自然に使え、パラメトリック設計と相性が良い
3. **CadQueryと同じOCCTカーネル** — 必要に応じてCadQueryの資産も活用可能
4. **Apache 2.0** — 商用利用・再配布に制約なし
5. **pipインストール可能** — condaに依存しない

### 第二候補: CadQuery

**理由:**
- Build123dがv1.0未満で安定性に不安がある場合のフォールバック
- コミュニティ・事例が多く、エンクロージャ設計のテンプレートが豊富
- Docker公式イメージがあり、CI/CD統合が容易

### 推奨アーキテクチャ

```
[KiCad PCB] → Fission KiCadブリッジ → [Fission統一スキーマ (JSON)]
                                              ↓
                                    [AIエージェント層]
                                    Claude Code / LLM API
                                              ↓
                                    [Build123d Pythonコード生成]
                                              ↓
                                    [STEP / STL エクスポート]
                                              ↓
                                    [Trimesh で品質チェック]
                                              ↓
                                    [製造発注 / 3Dプリント]
```

### 両方サポートする選択肢

CadQueryとBuild123dは同じOCPバインディングを共有しており、オブジェクトの相互変換が可能。Fissionの統一スキーマからどちらのAPIでもコード生成できるようにしておけば、ユーザーの好みやプロジェクトの要件に応じて切り替え可能。
