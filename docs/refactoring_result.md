# リファクタリング結果: 抽出・構造化CLIの統合

本書は、2本に分かれていたCLI（`dxf-extract` / `dxf-structurize`）を単一コマンドに統合した
リファクタリングの内容と結果を記録する。仕様は `specs/004-refactoring-unify-cli/` を参照。

## 1. 目的

- DXF入力から構造化JSON＋Markdownレポート生成までを**単一コマンドで一気通貫**実行する。
- 抽出・構造化にまたがる重複処理を共通化する。
- LLM使用を**全体ON/OFFの単一スイッチ**で制御し、OFF時はプログラムのみ（カテゴリA）で
  退行なく出力する。

## 2. コマンドの統合

| リファクタリング前 | リファクタリング後 |
|--------------------|--------------------|
| `dxf-extract <dxf>` … DXF→抽出JSON | `dxf-extract <dxf>` … DXF→抽出→構造化JSON＋MD（一気通貫） |
| `dxf-structurize <json>` … 抽出JSON→構造化JSON＋MD | （廃止。`dxf-extract` に統合） |

- 旧 `dxf-structurize` エントリポイントは削除し、`src/dxf_extractor/structurize_cli.py` も削除した。
- `pyproject.toml` の `[project.scripts]` は `dxf-extract` 1本に統合した。
- 抽出JSON（中間成果物）が必要な場合は `--save-intermediate` で `<stem>.json` を保存できる。

## 3. 重複処理の統合

| 重複していた処理 | 統合前 | 統合後 |
|------------------|--------|--------|
| 設定読込 | 両CLIが個別に `load_config` を呼び出し | オーケストレータ経由で1回 |
| ロギング/進捗表示 | `cli.py` は `logging`、`structurize_cli.py` は `print`+`click.echo` の混在 | `cli_support.setup_logging`（logging）に統一。`--log-level quiet` で抑制 |
| 出力パス解決 | 各CLIで個別実装 | `cli_support.resolve_output_dir` / `output_paths` に共通化 |
| LLM有効判定 | 抽出側=`config.llm.enabled`、構造化側=`--no-llm`→`llm_config=None` の2系統 | `config.llm.enabled` を唯一の真実源に一本化 |
| エラー終了処理 | 終了コード/メッセージが両CLIでばらつき | `cli_support.error_exit` ＋終了コード規約に統一 |
| パイプライン連結 | 利用者が手動で2段実行 | `orchestrator.run()` が抽出→構造化を連結 |

### 新規モジュール

- `src/dxf_extractor/cli_support.py` … ロギング設定・出力パス解決・エラー終了・終了コード定数。
- `src/dxf_extractor/orchestrator.py` … 抽出（`run_pipeline`）→構造化（`StructurizePipeline`）→
  結果（`OrchestrationResult`）の連結。LLM使用可否を抽出側・構造化側に一貫適用。

## 4. 終了コード規約（FR-016）

| コード | 意味 |
|--------|------|
| 0 | 正常終了 |
| 1 | 一般エラー（書込・処理中エラー） |
| 2 | 入力フォーマット不正（DXF読込・バージョン検証失敗、引数不正） |
| 3 | 設定ファイル不正 |

## 5. 処理の3分類（A / B / C）

LLM使用要否で各処理を分類する。**LLM無効時はカテゴリAのみ**を実行する。

| 分類 | 定義 | 該当処理（現行実装） |
|------|------|----------------------|
| **A: プログラムのみで達成** | LLM不要で完結 | `parsers/*`（形状・寸法・テキスト・表・レイヤ抽出）、`analyzers/*`（公差解析・重複解決・ブロック検出・図枠検出・メタ抽出）、`associators/rule1..rule10` のルールベース判定、`serializers/*`（JSON/MD出力） |
| **B: LLMで精度改善が見込める** | プログラムでも可だがLLMで精度向上 | `llm/labeler.py`（ブロック種別・レイヤ用途のラベリング）、`associators/llm_helper.py` を任意利用するルール（曖昧判定の補完） |
| **C: LLM必須** | プログラムのみでは困難 | 現時点で該当処理なし（将来の自然言語注記の意味解釈等を想定した**拡張枠**。分類・文書化のみ） |

> カテゴリCは本リファクタリングでは枠組みの定義に留める。該当処理が追加された際に
> LLM有効時の成果物へ反映する。

## 6. 退行防止の担保

- リファクタリング前に `--no-llm` で生成した成果物を `tests/fixtures/golden/` にゴールデンとして保存。
- 統合CLIの `--no-llm` 出力（構造化JSON＝完全一致、Markdown＝タイトル/生成日時を除く本文一致）が
  ゴールデンと一致することを `tests/integration/test_no_llm_regression.py` で検証している。

## 7. 主な変更ファイル

| ファイル | 区分 | 内容 |
|----------|------|------|
| `src/dxf_extractor/cli.py` | 改修 | 統合CLIエントリポイント |
| `src/dxf_extractor/cli_support.py` | 新規 | 共通CLIユーティリティ |
| `src/dxf_extractor/orchestrator.py` | 新規 | 抽出→構造化の連結 |
| `src/dxf_extractor/structurize_cli.py` | 削除 | 旧構造化CLI |
| `pyproject.toml` | 改修 | スクリプトを `dxf-extract` 1本に統合 |
| `tests/integration/test_cli_end_to_end.py` 他 | 新規 | 統合CLIのE2E・LLMスイッチ・退行・汎用性テスト |

## 8. 追補（006）: 抽出・体系化の2フェーズ分割とルール外部化

> 仕様 `specs/006-split-extract-structurize/`。004の単一コマンドを土台に、内部を2フェーズへ再編する。

- **2フェーズ分割**: `dxf-extract` を `extract`（(a)抽出）/ `structurize`（(b)体系化）/ `run`（連続）の3サブコマンドへ。`cli.py` を `click.Group` 化し、先頭がサブコマンドでなければ既定コマンドへフォールバックして `config.execution.mode`（既定 `run`）でディスパッチ（後方互換: `dxf-extract <file>` は従来どおり）。
- **抽出JSONの往復**: `serializers/json_serializer.py` に `deserialize_from_json` / `load_drawing` を追加。(a)出力＝(b)入力（`DXFDrawing` と同一スキーマ、ロスレス）。
- **オーケストレータ分割**: `orchestrator.py` を `run_extract` / `run_structurize` / `run_all`（旧 `run` はエイリアスとして温存）に分割。スケール係数適用は `run_structurize` に内包。
- **ルール外部化**: `associators/registry.py`（id→クラス＋既定順）と `associators/rule_loader.py`（JSON読込・検証）を新設。`structurize_pipeline.py` はハードコード `_RULE_STEPS` を廃し、レジストリ/ローダ駆動に。`structurize.rules_config` 未指定なら現行構成と同一。
- **フェーズ別LLM**: `extraction.llm` / `structurize.llm`（`PhaseLLMConfig`）を追加。実効値は `AppConfig.effective_extraction_llm` / `effective_structurize_llm` が解決（未指定はトップ `llm.enabled` 継承）。既定は両フェーズ無効。
- **退行防止**: `extract`→`structurize` ＝ `run` の同値（`tests/integration/test_phase_split.py`）、`--no-llm` ゴールデン不変（`test_no_llm_regression.py`、`run` サブコマンドも検証）を維持。LLMテストは全モック・実API不使用。

### 追加・変更ファイル（006）

| ファイル | 区分 | 内容 |
|----------|------|------|
| `src/dxf_extractor/cli.py` | 改修 | Group化・3サブコマンド・既定ディスパッチ・共通委譲 |
| `src/dxf_extractor/orchestrator.py` | 改修 | `run_extract`/`run_structurize`/`run_all` 分割・フェーズ別LLM |
| `src/dxf_extractor/config.py` | 改修 | `ExecutionConfig`・`PhaseLLMConfig`・`rules_config`・実効LLM解決 |
| `src/dxf_extractor/structurize_pipeline.py` | 改修 | レジストリ/ローダ駆動・ルール別params上書き |
| `src/dxf_extractor/associators/registry.py` | 新規 | ルールレジストリ（id→クラス・既定順） |
| `src/dxf_extractor/associators/rule_loader.py` | 新規 | ルール設定JSONの読込・検証 |
| `src/dxf_extractor/serializers/json_serializer.py` | 改修 | 抽出JSONの読み戻し（`load_drawing`） |
| `src/dxf_extractor/pipeline.py` | 改修 | 抽出フェーズLLMの上書き引数 |
| `config.yaml` / `rules.default.json` | 改修/新規 | 実行モード・フェーズ別LLM・ルール設定の例 |
| `tests/unit/test_json_roundtrip.py` 他 | 新規 | 往復・ルールローダ・実行モード・フェーズ別LLM・委譲・分割同値の各テスト |
