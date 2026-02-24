# Fission + AI: 使い方ガイド

Fissionは **KiCad PCB → ケース自動生成 → 製造ファイル出力** を一気通貫で行うツールです。
CLIだけでも使えますが、AI（Claude Code + MCP）を組み合わせると対話的にハードウェア設計ができます。

---

## セットアップ

```bash
# 1. インストール
cd /path/to/Fission
pip install -e .

# 2. 依存チェック（KiCad 9.0+, build123d, trimesh）
fission doctor

# 3. MCP接続（Claude CodeからAIツールを使えるようにする）
claude mcp add --transport stdio fission -- \
  /path/to/Fission/.venv/bin/fission-mcp
```

---

## シナリオ1: CLIだけで使う（AIなし）

```bash
# KiCadで基板を設計 → board.kicad_pcb ができる

# 設計の健全性チェック
fission check board.kicad_pcb

# 問題なければ製造ファイル一括生成
fission export board.kicad_pcb -o fab/
# → fab/ に Gerber, ドリル, PnP, スキーマJSON, ケースSTEP/STL が揃う

# fab/ をJLCPCBやPCBWayにアップロード、STLを3Dプリント
```

個別に使うこともできます:

```bash
# スキーマ抽出だけ
fission extract board.kicad_pcb -o schema.json

# ケース生成だけ
fission generate-case schema.json -o enclosure.step
fission generate-case schema.json -o enclosure.stl --split  # top/bottom分割
```

---

## シナリオ2: Claude Code + Fission MCP（本命）

MCPセットアップ後、Claude Codeを起動してプロジェクトディレクトリで会話するだけ。

### AIが使える6つのMCPツール

| ツール | 機能 |
|--------|------|
| `extract_pcb_schema` | KiCad PCBからスキーマJSON抽出 |
| `generate_case` | スキーマからケースSTEP/STL生成 |
| `export_manufacturing` | 製造ファイル一括生成 |
| `run_design_checks` | レイヤー整合性チェック |
| `modify_enclosure_config` | ケース設定変更（壁厚、クリアランス、素材） |
| `check_dependencies` | 環境の依存チェック |

### 会話例

```
あなた: 「board.kicad_pcb を解析して、ケースの設計をレビューしてくれ」
```

AIは内部で:

1. **`extract_pcb_schema("board.kicad_pcb")`** を呼ぶ
   → 基板の構造を完全に理解（外形、コネクタ位置、マウント穴、部品高さ...）

2. **`run_design_checks("board.kicad_pcb")`** を呼ぶ
   → 問題点を発見・報告

```
AI: 「80x60mmの基板にUSB-Cコネクタ1個、マウントホール4個の構成です。
     1つ警告: J2のピンヘッダにedge設定がありません。
     ケースの開口部が作られません。J2は外部接続用ですか？」
```

```
あなた: 「J2は内部接続だから開口不要。壁をもう少し厚くして3mmにしたい」
```

AIは内部で:

3. **`modify_enclosure_config(schema_json, wall_thickness=3.0)`** でスキーマ更新
4. **`run_design_checks`** で再チェック → 全PASS確認
5. **`generate_case(updated_schema, "enclosure.step")`** でケース生成

```
AI: 「壁厚3.0mmに変更、全チェックPASS。enclosure.step を生成しました。
     外形 92x72x12.1mm。製造ファイルも一括生成しますか？」
```

```
あなた: 「お願い」
```

6. **`export_manufacturing("board.kicad_pcb", "fab/")`** で一括出力

### ポイント

- あなたがやるのは **KiCadのGUI設計** と **Claude Codeとの会話** だけ
- AIがスキーマ解析→チェック→ケース生成→製造出力を全部やってくれる
- パラメータの微調整も会話で指示するだけ

---

## シナリオ3: AIに設計を任せる（将来の発展形）

```
あなた: 「ESP32-S3でWiFi温湿度センサーを作りたい。
         DHT22センサー、USB-C給電、3Dプリントケース付きで」
```

将来的にSKiDL（回路設計）が統合されれば:

```
AI: 回路設計 → PCBレイアウト → ケース自動生成 → 整合性チェック → 製造ファイル出力
```

を一気通貫で実行できるようになる。現在のMCPサーバーはそのための土台。

---

## CLIコマンド一覧

| コマンド | 説明 |
|----------|------|
| `fission doctor` | 依存関係チェック |
| `fission extract <pcb>` | PCBからスキーマJSON抽出 |
| `fission generate-case <json>` | スキーマからケース生成 |
| `fission export <pcb> -o <dir>` | 製造ファイル一括生成 |
| `fission check <pcb or json>` | レイヤー整合性チェック |

---

## 設計の流れ（全体図）

```
KiCad GUI          Fission             AI (Claude Code)
─────────          ───────             ────────────────
基板設計
  │
  ├─ .kicad_pcb ──→ extract ──→ スキーマJSON
  │                                    │
  │                              AIが解析・提案
  │                                    │
  │                check ←──── チェック実行
  │                  │
  │               generate-case ←── パラメータ指示
  │                  │
  │               export ──→ Gerber/Drill/PnP/STEP/STL
  │                              │
  └──────────────────────────────┘
                             製造発注
```
