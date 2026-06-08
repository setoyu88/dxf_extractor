"""LLM補完ヘルパー: カテゴリBルールのLLM呼び出し共通処理。"""
import httpx
from langchain_core.exceptions import LangChainException

from dxf_extractor.config import LLMConfig
from dxf_extractor.llm.provider import create_llm
from dxf_extractor.models.association import AssociationResult

_FALLBACK_CONFIDENCE = 0.5


def try_llm_augment(
    rule_id: str,
    source_id: str,
    prompt: str,
    llm_config: LLMConfig,
    fallback_target_ids: list[str],
    parse_response: "callable[[str], list[str]] | None" = None,
    extract_value: "callable[[str], str | None] | None" = None,
    fallback_extracted_value: "str | None" = None,
) -> AssociationResult:
    """LLM補完を試みる。失敗時はフォールバック結果を返す。

    Args:
        rule_id: ルール番号。
        source_id: 関連付け元エンティティID。
        prompt: LLMに送るプロンプト。
        llm_config: LLM設定。
        fallback_target_ids: LLM失敗時のフォールバックターゲットIDリスト。
        parse_response: LLMレスポンスをターゲットIDリストに変換する関数（省略時はfallback_target_idsを使用）。
        extract_value: LLMレスポンスからextracted_valueを抽出する関数（省略時はNone）。
        fallback_extracted_value: LLM失敗時に使用するextracted_value（省略時はNone）。

    Returns:
        AssociationResult: LLM補完済みまたはフォールバック結果。
    """
    try:
        llm = create_llm(llm_config)
        response = llm.invoke(prompt)
        content = response.content if hasattr(response, "content") else str(response)
        target_ids = parse_response(content) if parse_response else fallback_target_ids
        if not target_ids:
            target_ids = fallback_target_ids
        extracted = extract_value(content) if extract_value else None
        return AssociationResult(
            rule=rule_id,
            source_id=source_id,
            target_ids=target_ids,
            confidence=0.9,
            extracted_value=extracted,
            llm_augmented=True,
        )
    except (LangChainException, httpx.TimeoutException, httpx.ConnectError):
        return AssociationResult(
            rule=rule_id,
            source_id=source_id,
            target_ids=fallback_target_ids,
            confidence=_FALLBACK_CONFIDENCE,
            extracted_value=fallback_extracted_value,
            llm_augmented=False,
            llm_error=True,
        )
