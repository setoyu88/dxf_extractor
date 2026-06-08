"""AssociatorBase 抽象クラス（Template Methodパターン）。"""
from abc import ABC, abstractmethod

from dxf_extractor.config import LLMConfig, StructurizeConfig
from dxf_extractor.models.association import AssociationResult
from dxf_extractor.models.drawing import DXFDrawing


class AssociatorBase(ABC):
    """各ルールクラスの基底クラス。信頼スコアフィルタリングとエラーハンドリングを共通化する。"""

    RULE_ID: str

    def run(
        self,
        drawing: DXFDrawing,
        config: StructurizeConfig,
        llm_config: LLMConfig | None = None,
    ) -> list[AssociationResult]:
        """テンプレートメソッド: フィルタリングと例外処理を共通化する。

        Args:
            drawing: 入力DXF図面。
            config: 体系化処理設定。
            llm_config: LLM設定（Noneの場合LLM不使用）。

        Returns:
            list[AssociationResult]: フィルタリング済みの関連付け結果リスト。
        """
        results = self.associate(drawing, config, llm_config)
        threshold = config.confidence_threshold
        return [r for r in results if r.confidence >= threshold]

    @abstractmethod
    def associate(
        self,
        drawing: DXFDrawing,
        config: StructurizeConfig,
        llm_config: LLMConfig | None = None,
    ) -> list[AssociationResult]:
        """関連付けロジックの実装（サブクラスで定義）。

        Args:
            drawing: 入力DXF図面。
            config: 体系化処理設定。
            llm_config: LLM設定（Noneの場合LLM不使用）。

        Returns:
            list[AssociationResult]: 関連付け結果リスト（フィルタリング前）。
        """
