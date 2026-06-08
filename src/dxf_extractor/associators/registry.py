"""体系化ルールのレジストリ（US3 / FR-014〜017）。

``rule_id`` → ``(既定ラベル, ルールクラス)`` の単一の真実源と、既定適用順序を定義する。
既定順序は旧 ``structurize_pipeline._RULE_STEPS`` と一字一句同一であり、ルール設定JSONを
指定しない場合は従来挙動・ゴールデン不変を保証する。
"""
from dataclasses import dataclass, field
from typing import Type

from dxf_extractor.associators.base import AssociatorBase
from dxf_extractor.associators.rule1_dimension_shape import Rule1DimensionShape
from dxf_extractor.associators.rule2_tdim_classifier import Rule2TdimClassifier
from dxf_extractor.associators.rule3_table_structure import Rule3TableStructure
from dxf_extractor.associators.rule4_cross_section import Rule4CrossSection
from dxf_extractor.associators.rule5_note_shape import Rule5NoteShape
from dxf_extractor.associators.rule6_view_projection import Rule6ViewProjection
from dxf_extractor.associators.rule7_hatch import Rule7Hatch
from dxf_extractor.associators.rule8_title_block import Rule8TitleBlock
from dxf_extractor.associators.rule9_revision import Rule9Revision
from dxf_extractor.associators.rule10_part_number import Rule10PartNumber


@dataclass
class RuleStep:
    """体系化パイプラインが消費する実行単位。

    Attributes:
        label: 進捗表示ラベル。
        rule_cls: ルールクラス。
        params: 当該ルールに適用する StructurizeConfig 上書き（空可）。
    """

    label: str
    rule_cls: Type[AssociatorBase]
    params: dict = field(default_factory=dict)


# rule_id → (既定ラベル, ルールクラス)。既定順序は DEFAULT_ORDER で表す。
RULE_REGISTRY: dict[str, tuple[str, Type[AssociatorBase]]] = {
    "rule3": ("ルール3-0: テーブル境界識別", Rule3TableStructure),
    "rule8": ("ルール8: 標題欄構造化", Rule8TitleBlock),
    "rule9": ("ルール9: 改定情報抽出", Rule9Revision),
    "rule4": ("ルール4: 断面表示特定", Rule4CrossSection),
    "rule7": ("ルール7: ハッチング関連付け", Rule7Hatch),
    "rule1": ("ルール1: 寸法線↔形状マッチング", Rule1DimensionShape),
    "rule6": ("ルール6: 視図グループ化", Rule6ViewProjection),
    "rule10": ("ルール10: 部品番号紐づけ", Rule10PartNumber),
    "rule2": ("ルール2: テキスト寸法分類", Rule2TdimClassifier),
    "rule5": ("ルール5: 注記帰属決定", Rule5NoteShape),
}

# 既定適用順序（旧 _RULE_STEPS と同一）。
DEFAULT_ORDER: list[str] = [
    "rule3", "rule8", "rule9", "rule4", "rule7",
    "rule1", "rule6", "rule10", "rule2", "rule5",
]


def default_rule_steps() -> list[RuleStep]:
    """既定のルールステップ列を返す（現行 _RULE_STEPS と同一）。

    Returns:
        list[RuleStep]: 既定順序のルールステップ列（params なし）。
    """
    steps: list[RuleStep] = []
    for rule_id in DEFAULT_ORDER:
        label, rule_cls = RULE_REGISTRY[rule_id]
        steps.append(RuleStep(label=label, rule_cls=rule_cls))
    return steps
