"""設定モデルとYAML設定ファイルの読み込み。"""
import logging
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, field_validator, model_validator

logger = logging.getLogger(__name__)

# ============================================================
# キーワード辞書の既定値（US1 / FR-102）
# ------------------------------------------------------------
# 既定値は現行のコード内ハードコードと完全に同一にする。利用者が config.yaml で
# 追加・上書きしない限り、構造化結果は従来と変化しない（後方互換／ゴールデン不変）。
# ============================================================

# レイヤ用途 → キーワード群（旧 layer_extractor._RULE_BASED_PURPOSE を用途別に集約）
_DEFAULT_LAYER_PURPOSE: dict[str, list[str]] = {
    "外形線": ["外形線", "outline"],
    "寸法線": ["寸法線", "dim", "dimension"],
    "中心線": ["中心線", "center", "centerline"],
    "補助線": ["補助線", "hidden"],
    "注記": ["注記", "note", "text"],
    "図枠": ["図枠", "frame", "border", "titleblock"],
}
# 表ヘッダー候補（旧 rule3._HEADER_KEYWORDS）
_DEFAULT_TABLE_HEADERS: list[str] = [
    "番号", "品名", "型番", "名称", "数量", "仕様", "材料", "備考", "NO", "no",
]
# 改定キーワード（旧 rule9._REV_SIMPLE_PATTERN: REV|改定|revision）
_DEFAULT_REVISION: list[str] = ["改定", "REV", "revision"]
# 断面レイヤキーワード（旧 rule4._SECTION_LAYER_KEYWORDS、判定は小文字比較）
_DEFAULT_SECTION: list[str] = ["cross", "section"]


def _merge_list(user: list[str], default: list[str], mode: str) -> list[str]:
    """リスト型キーワードの実効値を返す（merge=和集合 / replace=置換）。"""
    if not user:
        return list(default)
    if mode == "replace":
        return list(user)
    return list(dict.fromkeys(list(default) + list(user)))


def _merge_dict(
    user: dict[str, list[str]], default: dict[str, list[str]], mode: str
) -> dict[str, list[str]]:
    """辞書型キーワードの実効値を返す。

    merge: カテゴリごとに既定＋利用者の和集合。
    replace: 利用者が指定したカテゴリのみ置換、未指定カテゴリは既定維持。
    """
    if not user:
        return {k: list(v) for k, v in default.items()}
    if mode == "replace":
        result = {k: list(v) for k, v in default.items()}
        result.update({k: list(v) for k, v in user.items()})
        return result
    result = {k: list(v) for k, v in default.items()}
    for k, v in user.items():
        result[k] = list(dict.fromkeys(result.get(k, []) + list(v)))
    return result


class KeywordConfig(BaseModel):
    """意味付け判定に用いるキーワード辞書（US1 / FR-101〜105）。

    各フィールドは利用者の追加・上書き分のみを保持し、既定値は ``effective_*`` で
    モジュール既定とマージして得る。未指定時は既定（現行と同一）が返るため後方互換。
    """

    layer_purpose: dict[str, list[str]] = {}
    title_block_labels: dict[str, list[str]] = {}
    table_headers: list[str] = []
    revision: list[str] = []
    section: list[str] = []
    merge_mode: Literal["merge", "replace"] = "merge"

    def effective_layer_purpose(self) -> dict[str, list[str]]:
        """レイヤ用途キーワードの実効辞書（用途名→キーワード群）。"""
        return _merge_dict(self.layer_purpose, _DEFAULT_LAYER_PURPOSE, self.merge_mode)

    def effective_table_headers(self) -> list[str]:
        """表ヘッダーキーワードの実効リスト。"""
        return _merge_list(self.table_headers, _DEFAULT_TABLE_HEADERS, self.merge_mode)

    def effective_revision(self) -> list[str]:
        """改定キーワードの実効リスト。"""
        return _merge_list(self.revision, _DEFAULT_REVISION, self.merge_mode)

    def effective_section(self) -> list[str]:
        """断面レイヤキーワードの実効リスト。"""
        return _merge_list(self.section, _DEFAULT_SECTION, self.merge_mode)

    def effective_title_block_labels(self) -> dict[str, list[str]]:
        """標題欄ラベル（追加分）の実効辞書。既定は空（既存正規表現を維持）。"""
        return _merge_dict(self.title_block_labels, {}, self.merge_mode)

    def resolve_layer_purpose(self, layer_name: str) -> str | None:
        """レイヤ名から用途名を一意に解決する（FR-104: 完全一致＞部分一致＞長いキーワード優先）。

        Args:
            layer_name: レイヤ名。

        Returns:
            str | None: 用途名（_DEFAULT_LAYER_PURPOSE のキー）。該当なしは None。
        """
        lower = layer_name.lower()
        purposes = self.effective_layer_purpose()
        # 完全一致を最優先
        for purpose, keywords in purposes.items():
            for kw in keywords:
                if lower == kw.lower():
                    return purpose
        # 部分一致は最長キーワード優先で一意化
        best_purpose: str | None = None
        best_len = -1
        for purpose, keywords in purposes.items():
            for kw in keywords:
                if kw.lower() in lower and len(kw) > best_len:
                    best_purpose, best_len = purpose, len(kw)
        return best_purpose


class DxfVersionRange(BaseModel):
    """DXFサポートバージョン範囲。"""

    min: str = "R12"
    max: str = "R2018"


class DxfConfig(BaseModel):
    """DXF処理設定。"""

    supported_versions: DxfVersionRange = DxfVersionRange()
    coordinate_normalization: bool = False


class AzureConfig(BaseModel):
    """Azure AI Foundry固有設定。

    認証は既定で Azure CLI 認証（`az login` のトークン）を用い、APIキーを不要とする。
    `auth_method: api_key` を指定した場合のみ環境変数 `AZURE_OPENAI_API_KEY` を使用する。
    """

    deployment: str = ""
    endpoint: str = ""
    api_version: str = "2024-10-21"
    auth_method: Literal["azure_cli", "api_key"] = "azure_cli"


class LLMConfig(BaseModel):
    """LLM連携設定。"""

    enabled: bool = True
    provider: str = "openai"
    model: str = "gpt-5-mini"
    mode: str = "global"
    priority: str = "accuracy"
    azure: AzureConfig = AzureConfig()

    @field_validator("provider")
    @classmethod
    def validate_provider(cls, v: str) -> str:
        """プロバイダー名を検証する。"""
        allowed = {"openai", "anthropic", "azure"}
        if v not in allowed:
            raise ValueError(f"provider は {allowed} のいずれかでなければなりません。指定値: {v!r}")
        return v

    @field_validator("mode")
    @classmethod
    def validate_mode(cls, v: str) -> str:
        """モードを検証する。"""
        allowed = {"global", "local"}
        if v not in allowed:
            raise ValueError(f"mode は {allowed} のいずれかでなければなりません。指定値: {v!r}")
        return v

    @field_validator("priority")
    @classmethod
    def validate_priority(cls, v: str) -> str:
        """優先度を検証する。"""
        allowed = {"accuracy", "token"}
        if v not in allowed:
            raise ValueError(f"priority は {allowed} のいずれかでなければなりません。指定値: {v!r}")
        return v


class PhaseLLMConfig(BaseModel):
    """フェーズ個別のLLM使用有無の上書き設定（US4 / FR-009〜011）。

    接続情報（provider/model/azure 等）は保持せず、トップレベル ``llm`` を使用する。
    ``enabled`` が ``None`` の場合はトップレベル ``llm.enabled`` を継承する。
    """

    enabled: bool | None = None


class ExecutionConfig(BaseModel):
    """実行モードの既定（US2 / FR-006〜007）。

    サブコマンド未指定時にどのフェーズを実行するかを決める。既定 ``run`` は
    抽出→体系化の連続実行（現行挙動と同等）。
    """

    mode: Literal["extract", "structurize", "run"] = "run"


class TextDimensionConfig(BaseModel):
    """テキスト寸法設定。"""

    duplicate_threshold: float = 5.0


class ClusteringConfig(BaseModel):
    """DBSCANクラスタリング設定。"""

    epsilon: float = 20.0
    min_samples: int = 2

    @field_validator("epsilon")
    @classmethod
    def epsilon_positive(cls, v: float) -> float:
        """epsilonは正の値でなければならない。"""
        if v <= 0:
            raise ValueError(f"epsilon は正の値でなければなりません。指定値: {v}")
        return v

    @field_validator("min_samples")
    @classmethod
    def min_samples_gte_one(cls, v: int) -> int:
        """min_samplesは1以上でなければならない。"""
        if v < 1:
            raise ValueError(f"min_samples は1以上でなければなりません。指定値: {v}")
        return v


class InsertConfig(BaseModel):
    """INSERT展開・複数シート処理の設定（US2 / FR-201〜206）。

    既定はすべて無効で、モデルスペースのみ・INSERT無視（従来挙動）を維持する。
    """

    expand_inserts: bool = False
    max_depth: int = 5
    max_entities: int = 100000
    process_paperspace: bool = False

    @field_validator("max_depth")
    @classmethod
    def max_depth_positive(cls, v: int) -> int:
        """max_depthは1以上でなければならない。"""
        if v < 1:
            raise ValueError(f"max_depth は1以上でなければなりません。指定値: {v}")
        return v

    @field_validator("max_entities")
    @classmethod
    def max_entities_positive(cls, v: int) -> int:
        """max_entitiesは1以上でなければならない。"""
        if v < 1:
            raise ValueError(f"max_entities は1以上でなければなりません。指定値: {v}")
        return v


class ExtractionConfig(BaseModel):
    """抽出処理設定。"""

    text_dimension: TextDimensionConfig = TextDimensionConfig()
    clustering: ClusteringConfig = ClusteringConfig()
    keywords: KeywordConfig = KeywordConfig()
    entity_source: InsertConfig = InsertConfig()
    # 抽出フェーズのLLM使用上書き（US4）。Noneでトップレベル llm.enabled を継承。
    llm: PhaseLLMConfig | None = None
    rules: list = []


class ToleranceConfig(BaseModel):
    """関連付け処理の許容誤差設定。"""

    delta: float = 2.0
    d_threshold: float = 5.0
    delta_y_ratio: float = 0.5


class ScaleConfig(BaseModel):
    """単位・尺度の自動スケール設定（US3 / FR-301〜304）。

    既定 `auto_scale=False` では係数1.0（現行の絶対値しきい値を維持）。
    """

    auto_scale: bool = False
    base_unit: str = "mm"
    reference_size: float | None = None


# 既定の断面記号パターン（現行 rule4 と同一: "A-A" または単一英字）。
_DEFAULT_SECTION_SYMBOL_PATTERN = r"^([A-Z])-\1$|^[A-Z]$"


class DrawingProfileConfig(BaseModel):
    """作図規約プロファイル（US4 / FR-401〜403）。

    既定値は現行挙動と完全一致（下部標題欄・A-A断面・整数テキスト部品番号）。
    """

    title_block_region: Literal["bottom", "top", "top_right", "bottom_right", "auto"] = "bottom"
    title_block_ratio: float = 0.2
    section_symbol_pattern: str = _DEFAULT_SECTION_SYMBOL_PATTERN
    part_number_style: Literal["integer_text", "balloon", "both"] = "integer_text"

    def compiled_section_pattern(self):
        """断面記号の正規表現をコンパイルして返す。不正な式は既定にフォールバックする（C-CFG-8）。"""
        import re as _re
        try:
            return _re.compile(self.section_symbol_pattern)
        except _re.error:
            logger.warning(
                "[WARN] section_symbol_pattern が不正なため既定パターンにフォールバックします: %r",
                self.section_symbol_pattern,
            )
            return _re.compile(_DEFAULT_SECTION_SYMBOL_PATTERN)


class StructurizeConfig(BaseModel):
    """体系化処理設定。"""

    confidence_threshold: float = 0.0
    tolerances: ToleranceConfig = ToleranceConfig()
    # 各ルールがキーワード辞書を参照できるよう、AppConfig が extraction から橋渡しする（research R8）。
    keywords: KeywordConfig = KeywordConfig()
    scale: ScaleConfig = ScaleConfig()
    profile: DrawingProfileConfig = DrawingProfileConfig()
    # 体系化フェーズのLLM使用上書き（US4）。Noneでトップレベル llm.enabled を継承。
    llm: PhaseLLMConfig | None = None
    # 体系化ルール設定JSONファイルのパス（US3 / FR-014）。Noneで既定（現行ルール構成）。
    rules_config: str | None = None


class AppConfig(BaseModel):
    """アプリケーション全体設定。"""

    dxf: DxfConfig = DxfConfig()
    llm: LLMConfig = LLMConfig()
    execution: ExecutionConfig = ExecutionConfig()
    extraction: ExtractionConfig = ExtractionConfig()
    structurize: StructurizeConfig = StructurizeConfig()

    def effective_extraction_llm(self, override: bool | None = None) -> bool:
        """抽出フェーズの実効LLM有無を解決する（US4 / FR-009〜010）。

        Args:
            override: CLI ``--llm/--no-llm`` の上書き。Noneで設定に従う。

        Returns:
            bool: 抽出フェーズでLLMを使用するか。
        """
        if override is not None:
            return override
        if self.extraction.llm is not None and self.extraction.llm.enabled is not None:
            return self.extraction.llm.enabled
        return self.llm.enabled

    def effective_structurize_llm(self, override: bool | None = None) -> bool:
        """体系化フェーズの実効LLM有無を解決する（US4 / FR-009〜010）。

        Args:
            override: CLI ``--llm/--no-llm`` の上書き。Noneで設定に従う。

        Returns:
            bool: 体系化フェーズでLLMを使用するか。
        """
        if override is not None:
            return override
        if self.structurize.llm is not None and self.structurize.llm.enabled is not None:
            return self.structurize.llm.enabled
        return self.llm.enabled

    @model_validator(mode="after")
    def _bridge_keywords(self) -> "AppConfig":
        """外部契約 `extraction.keywords` をルール参照用に `structurize.keywords` へ橋渡しする。

        利用者が `structurize.keywords` を明示指定していない（既定の）場合のみ、
        `extraction.keywords` を反映する。これにより辞書の真実源を extraction 側に一本化する。
        """
        if self.structurize.keywords == KeywordConfig():
            self.structurize.keywords = self.extraction.keywords
        return self


def load_config(config_path: Path | None = None) -> AppConfig:
    """YAMLファイルから設定を読み込む。

    Args:
        config_path: 設定ファイルパス。Noneの場合はデフォルト値を使用する。

    Returns:
        AppConfig: 読み込んだ設定。

    Raises:
        ValueError: 設定ファイルの内容が不正な場合。
    """
    if config_path is None:
        default_path = Path("config.yaml")
        if default_path.exists():
            config_path = default_path
        else:
            return AppConfig()

    with config_path.open(encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}

    return AppConfig.model_validate(raw)
