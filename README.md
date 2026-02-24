# Fission

> KiCad PCB → ケース自動生成 → 製造ファイル出力を、AIネイティブに一気通貫で。

Fissionは、KiCadで設計した基板から **スキーマ抽出 → ケース自動生成 → Gerber/BOM/STEP一括出力** までをCLI一本で完結させるツールです。MCPサーバーを内蔵しており、Claude CodeなどのAIエージェントが設計を解析・提案・実行できます。

## 特徴

- **KiCad PCBパーサー** — `.kicad_pcb` から外形・コネクタ・マウント穴・部品高さを自動抽出
- **統一スキーマ** — PCBとケースをつなぐPydanticベースの中間表現（JSON）
- **ケース自動生成** — Build123dによるパラメトリックなエンクロージャ（STEP/STL）
- **製造ファイル一括出力** — Gerber, ドリル, PnP, スキーマJSON, ケースを一発で
- **レイヤー整合性チェック** — スキーマ・ジオメトリ・メッシュの3レベル検証
- **MCP Server** — AIエージェントが6つのツールで設計に参加

## インストール

```bash
git clone https://github.com/your-org/fission.git
cd fission
pip install -e ".[mcp]"
```

KiCad 9.0以上が別途必要。依存確認:

```bash
fission doctor
```

## 使い方

```bash
# KiCad PCBからスキーマJSON抽出
fission extract board.kicad_pcb -o schema.json

# スキーマからケース生成
fission generate-case schema.json -o enclosure.step
fission generate-case schema.json -o enclosure.stl --split  # top/bottom分割

# レイヤー整合性チェック
fission check board.kicad_pcb
fission check schema.json --level geometry

# 製造データ一括出力（Gerber + ドリル + PnP + スキーマ + ケース）
fission export board.kicad_pcb -o fab/

# 環境チェック
fission doctor
```

## AI連携（Claude Code + MCP）

MCPサーバーを登録すると、Claude Codeが設計を対話的に解析・変更・出力できます。

```bash
claude mcp add --transport stdio fission -- \
  /path/to/Fission/.venv/bin/fission-mcp
```

### AIが使える6つのツール

| ツール | 機能 |
|--------|------|
| `extract_pcb_schema` | KiCad PCBからスキーマ抽出 |
| `generate_case` | スキーマからケースSTEP/STL生成 |
| `export_manufacturing` | 製造ファイル一括生成 |
| `run_design_checks` | レイヤー整合性チェック |
| `modify_enclosure_config` | ケース設定変更（壁厚・クリアランス・素材） |
| `check_dependencies` | 環境の依存チェック |

詳しい使い方は [README_AI.md](README_AI.md) を参照。

## 統一スキーマ

KiCad PCBから自動抽出される中間表現。ケース設計のパラメータとして使われます。

```json
{
  "schema_version": "1.0",
  "project": "sensor-board-v1",
  "pcb": {
    "outline": { "width": 80.0, "length": 60.0, "thickness": 1.6 },
    "mount_holes": [
      { "x": 5.0, "y": 5.0, "diameter": 3.2 }
    ],
    "connectors": [
      {
        "type": "USB-C",
        "reference": "J1",
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

## 技術スタック

```
┌───────────────────────────────────┐
│        Fission CLI (Python)        │
│  パーサー / スキーマ / ケース生成 / チェック │
│          MCP Server (AI連携)        │
└──────────────┬────────────────────┘
               │
   ┌───────────┼───────────┐
   │           │           │
   ▼           ▼           ▼
 KiCad     Build123d    trimesh
 PCB入力    ケース生成    メッシュ検証
 (S式)     (Python)     (Python)
```

| コンポーネント | 役割 |
|--------------|------|
| [KiCad](https://www.kicad.org/) | 回路図 + PCBレイアウト（GUI。Fissionへの入力元） |
| [Build123d](https://github.com/gumyr/build123d) | Pythonでパラメトリックなケース3Dモデルを生成 |
| [trimesh](https://trimesh.org/) | 生成メッシュの水密性・体積チェック |
| [Pydantic](https://docs.pydantic.dev/) | スキーマの型安全な定義・バリデーション |
| [Click](https://click.palletsprojects.com/) | CLI |
| [MCP](https://modelcontextprotocol.io/) | AIエージェント向けツールサーバー |

## プロジェクト構造

```
src/fission/
├── schema.py          # 統一スキーマ定義 (Pydantic)
├── kicad/parser.py    # KiCad PCBパーサー
├── case/generator.py  # Build123dケース生成
├── export.py          # 製造ファイル一括出力
├── check.py           # レイヤー整合性チェック
├── cli.py             # CLIエントリポイント
└── mcp_server.py      # MCPサーバー (6ツール)
```

## ロードマップ

- [x] Phase 1: 統一スキーマ定義 + KiCad PCBパーサー
- [x] Phase 2: Build123dによるケース自動生成
- [x] Phase 3: 製造ファイル一括出力 (`fission export`)
- [x] Phase 4: レイヤー整合性チェック (`fission check`)
- [x] Phase 5: MCP Server（AIエージェント統合）
- [ ] Phase 6: SKiDL統合（Pythonで回路記述→ネットリスト）
- [ ] Phase 7: 製造発注フロー（JLCPCB / PCBWay直結）

## ドキュメント

- [README_AI.md](README_AI.md) — AI連携の詳しい使い方（シナリオ別）
- [INSTALL.md](INSTALL.md) — インストール手順
- [docs/recommended-stack.md](docs/recommended-stack.md) — 技術スタック選定理由
- [docs/eda-tool-candidates.md](docs/eda-tool-candidates.md) — EDAツール調査
- [docs/cad-engine-candidates.md](docs/cad-engine-candidates.md) — CADエンジン調査

## ライセンス

MIT
