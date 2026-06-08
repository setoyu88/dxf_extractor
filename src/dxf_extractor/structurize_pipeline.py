"""体系化パイプライン。Decision 7 の処理順序でルールを適用する。

ルールの構成（有効/無効・適用順・パラメータ）は ``associators/registry.py`` と
``associators/rule_loader.py`` を通じて外部JSON設定で制御できる（US3 / FR-014）。
ルール設定を渡さない場合はレジストリ既定＝現行ルール構成で動作する（ゴールデン不変）。
"""
import sys

from dxf_extractor.associators.registry import RuleStep, default_rule_steps
from dxf_extractor.config import LLMConfig, StructurizeConfig
from dxf_extractor.models.association import StructuredDrawing
from dxf_extractor.models.drawing import DXFDrawing

_METADATA_FIELD_MAP = {
    "metadata.title": "title",
    "metadata.drawing_number": "drawing_number",
    "metadata.scale": "scale",
    "metadata.created_by": "created_by",
    "metadata.designed_by": "designed_by",
    "metadata.checked_by": "checked_by",
    "metadata.approved_by": "approved_by",
    "metadata.material": "material",
    "metadata.revision": "revision",
}

# 各ルールの params で上書き可能な StructurizeConfig フィールドのマッピング
# （契約 rules_config.schema.json の許可キー）。
_PARAM_SETTERS: dict[str, tuple[str, ...]] = {
    "confidence_threshold": ("confidence_threshold",),
    "tolerances.delta": ("tolerances", "delta"),
    "tolerances.d_threshold": ("tolerances", "d_threshold"),
    "tolerances.delta_y_ratio": ("tolerances", "delta_y_ratio"),
}


def _apply_params(config: StructurizeConfig, params: dict) -> StructurizeConfig:
    """ルール個別の params を反映した StructurizeConfig のコピーを返す。

    Args:
        config: ベースとなる体系化設定。
        params: ルール設定の params（許可キーは rule_loader で検証済み）。

    Returns:
        StructurizeConfig: params を反映した設定（params 空なら元の config をそのまま返す）。
    """
    if not params:
        return config
    copy = config.model_copy(deep=True)
    for key, value in params.items():
        path = _PARAM_SETTERS[key]
        target = copy
        for attr in path[:-1]:
            target = getattr(target, attr)
        setattr(target, path[-1], value)
    return copy


def _apply_metadata(structured: StructuredDrawing) -> None:
    """rule=8-2/8-3/9-2 の extracted_value を structured.metadata に書き込む。

    既存値（DXF属性由来）がある場合は上書きしない。
    revision は複数存在する場合に \\n で追記する。
    scale は NTS より実値を優先する。
    """
    for assoc in structured.associations:
        if assoc.extracted_value is None:
            continue
        for target in assoc.target_ids:
            field = _METADATA_FIELD_MAP.get(target)
            if not field:
                continue
            existing = getattr(structured.metadata, field, None)
            new_val = assoc.extracted_value

            if field == "revision":
                setattr(
                    structured.metadata,
                    "revision",
                    f"{existing}\n{new_val}" if existing else new_val,
                )
            elif field == "scale":
                if existing is None:
                    setattr(structured.metadata, "scale", new_val)
                elif existing == "NTS" and new_val != "NTS":
                    # 実値でNTSを上書き
                    setattr(structured.metadata, "scale", new_val)
                # 既に実値がある場合は何もしない
            else:
                if existing is None:
                    setattr(structured.metadata, field, new_val)


class StructurizePipeline:
    """体系化パイプライン。Decision 7 の順序でルールを適用する。

    ルールステップ列を渡さない場合はレジストリ既定（現行ルール構成）を用いる。
    """

    def __init__(self, rule_steps: list[RuleStep] | None = None) -> None:
        """ルールステップ列を受け取る。

        Args:
            rule_steps: 適用するルールステップ列。Noneで既定（現行ルール構成）。
        """
        self._rule_steps = rule_steps if rule_steps is not None else default_rule_steps()

    def run(
        self,
        drawing: DXFDrawing,
        config: StructurizeConfig,
        llm_config: LLMConfig | None = None,
        quiet: bool = False,
    ) -> StructuredDrawing:
        """関連付けルールを順番に適用して体系化済み図面を生成する。

        Args:
            drawing: 入力DXF図面。
            config: 体系化処理設定。
            llm_config: LLM設定（Noneの場合LLM不使用）。
            quiet: Trueの場合進捗表示を抑制する。

        Returns:
            StructuredDrawing: 体系化済み図面。
        """
        structured = StructuredDrawing.from_drawing(drawing)
        total = len(self._rule_steps)

        for i, step in enumerate(self._rule_steps, start=1):
            if not quiet:
                print(f"[{i}/{total}] {step.label}...", file=sys.stderr)

            associator = step.rule_cls()
            rule_config = _apply_params(config, step.params)
            try:
                results = associator.run(drawing, rule_config, llm_config)
                structured.associations.extend(results)
            except Exception as e:
                if not quiet:
                    print(f"  警告: {step.label} でエラーが発生しました: {e}", file=sys.stderr)

        _apply_metadata(structured)
        return structured
