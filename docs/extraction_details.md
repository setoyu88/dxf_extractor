# 抽出フェーズ詳細（DXF → 抽出データ）

担当: `src/dxf_extractor/pipeline.py` の `run_pipeline()`。
DXFを開き、要素を種類ごとに取り出して1つの `DXFDrawing`（抽出データ）にまとめる。
すべて **カテゴリA（プログラムのみ）** で完結し、最後に任意でLLMラベリング（カテゴリB）を行う。

## 実行順序

`run_pipeline()` は次の順に処理する。各抽出は `_safe_extract()` でくるまれ、
**1つが失敗しても警告を残して他は継続**する（FR-012 / 憲章I）。

| 順 | 処理 | 担当モジュール | カテゴリ | 出力 |
|----|------|----------------|----------|------|
| 0 | ファイルサイズ確認（5MB超で警告） | `pipeline._check_file_size` | A | （警告ログのみ） |
| 1 | DXF読込・バージョン検証 | `parsers/dxf_reader.py` | A | ezdxf Drawing |
| 2 | 形状抽出 | `parsers/shape_extractor.py` | A | `shapes` |
| 3 | 寸法抽出 | `parsers/dimension_extractor.py` | A | `dimensions` |
| 4 | テキスト抽出（注記/テキスト寸法に分離） | `parsers/text_extractor.py` | A | `notes`, `text_dimensions` |
| 5 | 表抽出 | `parsers/table_extractor.py` | A | `tables` |
| 6 | レイヤ抽出 | `parsers/layer_extractor.py` | A | `layers` |
| 7 | 公差解析 | `analyzers/tolerance_parser.py` | A | `tolerances` |
| 8 | テキスト寸法の重複解決 | `analyzers/duplicate_resolver.py` | A | `text_dimensions`（更新） |
| 9 | 論理ブロック検出（DBSCAN） | `analyzers/block_detector.py` | A | `blocks` |
| 10 | 図枠検出 | `analyzers/frame_detector.py` | A | 図枠ブロックの添字 |
| 11 | メタ情報抽出 | `analyzers/metadata_extractor.py` | A | 図番・尺度等 |
| 12 | LLMラベリング（任意） | `llm/labeler.py` | **B** | `blocks`/`layers` の種別・用途を上書き |

最後に `Metadata(dxf_version, ...)` と各リストを束ねて `DXFDrawing` を構築する。

> **汎用化拡張（005、オプトイン）**: 形状/寸法/テキスト/表/レイヤの各抽出は、共通の
> エンティティ供給 `parsers/entity_source.py` を反復元とする。設定 `extraction.entity_source` で
> INSERT展開（座標変換つき）・ペーパースペース/複数シート処理を有効化でき、各要素に帰属シート
> `sheet`・由来ブロック `source_block` が付く。ブロック検出の前段で `analyzers/scale_estimator.py` が
> スケール係数を推定し（`structurize.scale.auto_scale` 有効時）、DBSCAN epsilon と関連付けしきい値へ
> 乗算する。いずれも既定は無効で従来挙動と一致する。

---

## 1. DXF読込・バージョン検証（dxf_reader）

- `ezdxf.readfile()` で読み込む。読込失敗は `ValueError`、ファイル不存在は `FileNotFoundError`。
- 対応バージョン: **R12〜R2018**（`AC1009`〜`AC1032`）。範囲外は `ValueError`。
- 設定 `dxf.supported_versions.min/max` で範囲を変更可能。

## 2. 形状抽出（shape_extractor）

対応エンティティと変換先ジオメトリ:

| DXFエンティティ | ジオメトリ型 | 備考 |
|-----------------|--------------|------|
| LINE | `LineGeometry` | 始点・終点 |
| CIRCLE | `CircleGeometry` | 中心・半径 |
| ARC | `ArcGeometry` | 中心・半径・開始/終了角 |
| LWPOLYLINE / POLYLINE | `PolylineGeometry` | 頂点列・閉じフラグ |
| LEADER | `PolylineGeometry`（is_closed=False） | 引き出し線。Rule5/7で利用 |
| SPLINE | `PolylineGeometry`（制御点） | 曲線は制御点で近似 |
| HATCH | `OtherGeometry(entity_type="HATCH")` | 境界点からbbox算出。Rule7で利用 |
| ELLIPSE | `OtherGeometry(entity_type="ELLIPSE")` | 回転楕円のbboxを正確に計算 |
| TEXT/MTEXT/DIMENSION/INSERT | （None） | 形状として扱わない（別処理） |
| その他 | `OtherGeometry(entity_type=種別)` | **未対応でも捨てずに記録**（生属性付き） |

- ID採番: `shape_001`, `shape_002`, …
- 各形状に `bounding_box`（外接矩形）を付与。後段のブロック検出・関連付けの基礎になる。
- 個別エンティティのパース失敗時も `OtherGeometry` として記録（サイレントロスしない）。

## 3. 寸法抽出（dimension_extractor）

- `DIMENSION` エンティティを抽出。`dimtype` 下位4ビットで種別判定。
  - 0→linear、1→angular、2→diameter、3→radial、6→ordinate（その他はlinear扱い）。
- **方向判定**（linear/aligned）: `dxf.angle` または引出点ベクトルの角度から `x` / `y` / `parallel` を判定（許容 `_ANGLE_TOLERANCE_DEG=0.5°`）。
- 値: `text`（`<>` 除去）優先、無ければ `actual_measurement`。
- 引出点 `extension_point_1/2`（defpoint2/3）を保持 → Rule1 の端点マッチングに使用。
- ID採番: `dim_001`, …

## 4. テキスト抽出（text_extractor）

`TEXT` / `MTEXT` を走査し、**注記（Note）** と **テキスト寸法（TextDimension）** に振り分ける。

- 数値のみ（正規表現 `^\s*[+\-]?\d+(\.\d+)?\s*$`）→ テキスト寸法 `tdim_001`, …
- それ以外 → 注記 `note_001`, …
- MTEXTは書式コードを除去し、段落区切り `\P` を改行へ変換。
- バウンディングボックスは文字数×文字高から推定（全角=高さ、半角=高さ×`0.6`）。

## 5. 表抽出（table_extractor）

2種類の方法でテーブル領域を検出し、中のテキストを行列セルに割り付ける。

- **閉じたLWPOLYLINE矩形**（4点以上、幅・高さ>1.0）。
- **LINE群の格子**: 水平線・垂直線の交差が `_MIN_GRID_INTERSECTIONS=4` 以上の領域。
- 矩形内テキストが `_MIN_CELLS=2` 個以上ある場合のみ採用。
- 行割り当て: y座標を許容 `_CELL_Y_TOLERANCE=2.0` でクラスタリング→同一行、x座標昇順で列。
- ID採番: `table_001`, …。各セルは `TableCell(row, col, text, position)`。

## 6. レイヤ抽出（layer_extractor）

- モデルスペースを走査し、レイヤごとに **含有エンティティ種別・エンティティ数** を集計。
- レイヤ名から用途を**ルールベース**推定（`外形線/寸法線/中心線/補助線/注記/図枠/その他`）。
  日本語名・英語名（outline/dim/center/hidden/note/frame…）に対応。
- `llm_labeled=False`（LLM有効時に `labeler` が上書きする場合あり）。

## 7. 公差解析（tolerance_parser）

注記テキストから公差を正規表現で抽出する。

| 種別 | パターン例 | フィールド |
|------|-----------|-----------|
| はめあい記号（grade） | `H7/g6` | `grade`, `fit` |
| 上下異値（bilateral） | `+0.1/-0.2` | `upper`, `lower` |
| 対称（symmetric） | `±0.05` | `upper=+v`, `lower=-v` |

- ID採番: `tol_001`, …。
- 注記のみを対象（記号寸法 `dimensions` は引数で受け取るが現状未使用 → [拡張余地](./extensibility_and_issues.md)）。

## 8. テキスト寸法の重複解決（duplicate_resolver）

- テキスト寸法が、**同じ値**かつ **`duplicate_threshold`（既定5.0）以内**の記号寸法と一致する場合、`is_duplicate=True` を付与。
- Rule10（部品番号）は `is_duplicate=False` のものだけを対象にする。

## 9. 論理ブロック検出（block_detector）

- 形状・寸法・注記の**重心座標**を `DBSCAN`（`epsilon`=20.0, `min_samples`=2）でクラスタリング。
- 各クラスタを1つの `LogicalBlock`（`block_001`, …）とし、含む `shape_ids/dimension_ids/note_ids` とbboxを保持。
- **重要**: この段階では全ブロックの `type` は `part_view` 固定。
  `table` / `notes` / `frame` / `sub_view` への分類は **LLMラベリング（カテゴリB）でのみ**行われる
  （詳細は [LLM利用](./llm_usage.md)）。
- 座標を持たない形状（bbox面積0）は原点誤混入を防ぐため除外。

## 10. 図枠検出（frame_detector）

- レイヤ用途 `図枠` の形状を含み、注記 `_MIN_NOTE_COUNT=2` 以上のブロックを図枠候補とする。
- 図枠レイヤが特定できない場合は**面積比ヒューリスティック**（全体の `_MIN_AREA_RATIO=0.3` 以上）にフォールバック。
- 戻り値は図枠候補ブロックの添字リスト（メタ情報抽出の絞り込みに使用）。

## 11. メタ情報抽出（metadata_extractor）

図枠内の注記から、図番・タイトル・改訂・尺度・作成/確認/承認者を抽出する。

- **パス1**: ラベルと値が同一テキスト内（例「図番: ABC-001」）→ 正規表現で抽出。
- **パス2**: ラベルのみのテキスト（例「図番」）→ 右隣の近接テキスト（`_PROXIMITY_MAX_DIST=30`, `_PROXIMITY_MAX_DY=10`）を値として採用。
- 図枠候補が無ければ全注記を対象にフォールバック。

---

次に進む: [構造化ルール詳細](./structurization_rules.md) / [LLM利用](./llm_usage.md) / [出力形式](./output_format.md)
