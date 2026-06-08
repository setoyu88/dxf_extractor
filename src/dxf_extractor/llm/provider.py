"""LLMプロバイダーファクトリ（LangChain init_chat_model使用）。

OpenAI直接利用に加え、Azure AI Foundry（Azure OpenAI）にも対応する。利用環境は
`config.yaml` の `llm.provider`（openai / anthropic / azure）で選択する。Azure利用時の
認証は既定で **Azure CLI 認証**（`az login` で取得するAzure ADトークン）を用い、APIキーを
不要とする（`azure.auth_method: azure_cli`）。`azure.auth_method: api_key` を指定した場合のみ
環境変数 `AZURE_OPENAI_API_KEY` を使用する。
"""
from langchain.chat_models import init_chat_model
from langchain_core.language_models import BaseChatModel

from dxf_extractor.config import AzureConfig, LLMConfig

_DEFAULT_MODEL = "gpt-5-mini"

# Azure OpenAI / AI Foundry 向け Azure AD トークンのスコープ。
_AZURE_COGNITIVE_SCOPE = "https://cognitiveservices.azure.com/.default"


def _build_azure_kwargs(azure: AzureConfig) -> dict:
    """Azure AI Foundry 用の init_chat_model 追加引数を組み立てる。

    Args:
        azure: Azure固有設定。

    Returns:
        dict: ``init_chat_model`` へ渡す追加キーワード引数。

    Raises:
        ValueError: deployment または endpoint が未設定の場合。
    """
    if not azure.deployment:
        raise ValueError("Azure AI Foundry使用時は azure.deployment の設定が必要です")
    if not azure.endpoint:
        raise ValueError("Azure AI Foundry使用時は azure.endpoint の設定が必要です")

    kwargs: dict = {
        "azure_deployment": azure.deployment,
        "azure_endpoint": azure.endpoint,
        "api_version": azure.api_version,
    }

    if azure.auth_method == "azure_cli":
        # Azure CLI 認証（az login）でAzure ADトークンを取得する。APIキーは不要。
        # トークンは初回リクエスト時に遅延取得されるため、生成時点では az login 不要。
        from azure.identity import AzureCliCredential, get_bearer_token_provider

        kwargs["azure_ad_token_provider"] = get_bearer_token_provider(
            AzureCliCredential(), _AZURE_COGNITIVE_SCOPE
        )
    # auth_method == "api_key" の場合は環境変数 AZURE_OPENAI_API_KEY を使用する
    # （init_chat_model / AzureChatOpenAI が自動参照するため追加引数は不要）。

    return kwargs


def create_llm(config: LLMConfig) -> BaseChatModel:
    """設定に基づいてLLMインスタンスを生成する（FR-020）。

    Args:
        config: LLM設定。

    Returns:
        BaseChatModel: 初期化済みLLMインスタンス。

    Raises:
        ValueError: 未対応のプロバイダー、またはAzure設定不足の場合。
    """
    model_name = config.model or _DEFAULT_MODEL
    provider = config.provider

    extra_kwargs: dict = {}

    if provider == "azure":
        extra_kwargs = _build_azure_kwargs(config.azure)
        model_id = f"azure_openai:{model_name}"
    elif provider == "anthropic":
        model_id = f"anthropic:{model_name}"
    elif provider == "openai":
        model_id = f"openai:{model_name}"
    else:
        raise ValueError(f"未対応のプロバイダーです: {provider!r}。対応プロバイダー: openai, anthropic, azure")

    return init_chat_model(model_id, **extra_kwargs)
