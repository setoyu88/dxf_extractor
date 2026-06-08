"""レイヤPydanticモデル。"""
from enum import Enum

from pydantic import BaseModel


class LayerPurpose(str, Enum):
    """レイヤ用途分類。"""

    外形線 = "外形線"
    寸法線 = "寸法線"
    中心線 = "中心線"
    補助線 = "補助線"
    注記 = "注記"
    図枠 = "図枠"
    その他 = "その他"


class Layer(BaseModel):
    """DXFレイヤ情報。"""

    name: str
    entity_types: list[str]
    entity_count: int
    purpose: LayerPurpose | None = None
    llm_labeled: bool = False
