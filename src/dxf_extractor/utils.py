"""共通ユーティリティ関数。"""


def sanitize_surrogates(text: str) -> str:
    """サロゲート文字を含む文字列をサニタイズする。

    R12等の古いDXFファイルはShift-JIS等の非UTF-8エンコーディングを使用することがあり、
    ezdxfがデコードできないバイトをサロゲート文字（U+DC80〜U+DCFF）として保存する場合がある。
    PydanticのJSONシリアライズはサロゲート文字をUTF-8でエンコードできないためエラーになる。
    サロゲート文字はUnicode置換文字（U+FFFD）に変換する。

    Args:
        text: サニタイズする文字列。

    Returns:
        str: サロゲート文字を置換文字に変換した文字列。
    """
    if not any("\udc80" <= c <= "\udcff" for c in text):
        return text
    return "".join("�" if "\udc80" <= c <= "\udcff" else c for c in text)
