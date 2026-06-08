"""LangChain PromptTemplateによるプロンプトテンプレート。"""
from langchain_core.prompts import PromptTemplate

BLOCK_TYPE_PROMPT = PromptTemplate(
    input_variables=["block_info"],
    template="""以下の論理ブロック情報を分析して、ブロック種別を判定してください。
ブロック情報:
{block_info}

回答は以下の種別から1つだけ選んで、種別名のみを日本語で答えてください:
- part_view（図・正面図・側面図など）
- sub_view（部分図・詳細図）
- table（部品表・公差表）
- frame（図枠・タイトルブロック）
- notes（注記ブロック）

種別:""",
)

LAYER_PURPOSE_PROMPT = PromptTemplate(
    input_variables=["layer_name", "entity_types"],
    template="""以下のDXFレイヤ情報を分析して、レイヤの用途を判定してください。
レイヤ名: {layer_name}
含有エンティティ種別: {entity_types}

回答は以下の用途から1つだけ選んで、用途名のみを日本語で答えてください:
- 外形線
- 寸法線
- 中心線
- 補助線
- 注記
- 図枠
- その他

用途:""",
)

FRAME_DETECTION_PROMPT = PromptTemplate(
    input_variables=["block_info"],
    template="""以下のブロック情報を分析して、このブロックが図枠（タイトルブロック）かどうかを判定してください。
ブロック情報:
{block_info}

回答は「はい」または「いいえ」のみで答えてください。

判定:""",
)
