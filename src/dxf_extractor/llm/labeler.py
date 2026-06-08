"""ブロック種別・レイヤ用途・図枠判定LLMラベラー（FR-011）。"""
import logging

from langchain_core.messages import HumanMessage

from dxf_extractor.config import LLMConfig
from dxf_extractor.llm.prompts import BLOCK_TYPE_PROMPT, LAYER_PURPOSE_PROMPT
from dxf_extractor.llm.provider import create_llm
from dxf_extractor.models.block import BlockType, LogicalBlock
from dxf_extractor.models.layer import Layer, LayerPurpose

logger = logging.getLogger(__name__)

_BLOCK_TYPE_MAP = {
    "part_view": BlockType.part_view,
    "sub_view": BlockType.sub_view,
    "table": BlockType.table,
    "frame": BlockType.frame,
    "notes": BlockType.notes,
    "図": BlockType.part_view,
    "部分図": BlockType.sub_view,
    "部品表": BlockType.table,
    "図枠": BlockType.frame,
    "注記": BlockType.notes,
}

_LAYER_PURPOSE_MAP = {
    "外形線": LayerPurpose.外形線,
    "寸法線": LayerPurpose.寸法線,
    "中心線": LayerPurpose.中心線,
    "補助線": LayerPurpose.補助線,
    "注記": LayerPurpose.注記,
    "図枠": LayerPurpose.図枠,
    "その他": LayerPurpose.その他,
}


def label_with_llm(
    blocks: list[LogicalBlock],
    layers: list[Layer],
    config: LLMConfig,
) -> tuple[list[LogicalBlock], list[Layer]]:
    """LLMを使ってブロック種別とレイヤ用途を意味付けする（FR-011）。

    Args:
        blocks: 論理ブロックリスト。
        layers: レイヤリスト。
        config: LLM設定。

    Returns:
        tuple[list[LogicalBlock], list[Layer]]: 更新後の(ブロックリスト, レイヤリスト)。

    Raises:
        Exception: LLMのAPI呼び出しに失敗した場合。呼び出し側でフォールバックを処理する。
    """
    llm = create_llm(config)

    labeled_blocks = _label_blocks(blocks, llm, config)
    labeled_layers = _label_layers(layers, llm, config)

    return labeled_blocks, labeled_layers


def _label_blocks(
    blocks: list[LogicalBlock],
    llm: object,
    config: LLMConfig,
) -> list[LogicalBlock]:
    """LLMでブロック種別を判定する。

    Args:
        blocks: 論理ブロックリスト。
        llm: LLMインスタンス。
        config: LLM設定。

    Returns:
        list[LogicalBlock]: 種別が更新されたブロックリスト。
    """
    labeled: list[LogicalBlock] = []
    for block in blocks:
        try:
            block_info = _format_block_info(block)
            if config.mode == "global":
                prompt_text = BLOCK_TYPE_PROMPT.format(block_info=block_info)
                response = llm.invoke([HumanMessage(content=prompt_text)])  # type: ignore[attr-defined]
                answer = response.content.strip().lower()
            else:
                prompt_text = BLOCK_TYPE_PROMPT.format(block_info=block_info)
                response = llm.invoke([HumanMessage(content=prompt_text)])  # type: ignore[attr-defined]
                answer = response.content.strip().lower()

            block_type = _parse_block_type(answer)
            labeled.append(block.model_copy(update={"type": block_type, "llm_labeled": True}))
        except Exception as e:
            logger.warning("ブロック %s のLLMラベリングに失敗しました: %s", block.id, e)
            labeled.append(block)
    return labeled


def _label_layers(
    layers: list[Layer],
    llm: object,
    config: LLMConfig,
) -> list[Layer]:
    """LLMでレイヤ用途を判定する。

    Args:
        layers: レイヤリスト。
        llm: LLMインスタンス。
        config: LLM設定。

    Returns:
        list[Layer]: 用途が更新されたレイヤリスト。
    """
    labeled: list[Layer] = []
    for layer in layers:
        try:
            entity_types_str = ", ".join(layer.entity_types)
            prompt_text = LAYER_PURPOSE_PROMPT.format(
                layer_name=layer.name,
                entity_types=entity_types_str,
            )
            response = llm.invoke([HumanMessage(content=prompt_text)])  # type: ignore[attr-defined]
            answer = response.content.strip()
            purpose = _LAYER_PURPOSE_MAP.get(answer, LayerPurpose.その他)
            labeled.append(layer.model_copy(update={"purpose": purpose, "llm_labeled": True}))
        except Exception as e:
            logger.warning("レイヤ %s のLLMラベリングに失敗しました: %s", layer.name, e)
            labeled.append(layer)
    return labeled


def _format_block_info(block: LogicalBlock) -> str:
    """ブロック情報をLLMプロンプト用の文字列に変換する。

    Args:
        block: 論理ブロック。

    Returns:
        str: プロンプト用ブロック情報文字列。
    """
    bb = block.bounding_box
    return (
        f"ID: {block.id}\n"
        f"位置: ({bb.min_x:.1f}, {bb.min_y:.1f}) 〜 ({bb.max_x:.1f}, {bb.max_y:.1f})\n"
        f"形状数: {len(block.shape_ids)}\n"
        f"寸法数: {len(block.dimension_ids)}\n"
        f"注記数: {len(block.note_ids)}\n"
    )


def _parse_block_type(answer: str) -> BlockType:
    """LLM応答文字列をBlockTypeに変換する。

    Args:
        answer: LLM応答テキスト（小文字化済み）。

    Returns:
        BlockType: 対応するBlockType。不明な場合は part_view を返す。
    """
    for key, block_type in _BLOCK_TYPE_MAP.items():
        if key in answer:
            return block_type
    return BlockType.part_view
