"""レイアウト列挙とINSERT展開を担うエンティティ供給（US2 / FR-201〜206）。

`iter_entities()` は処理対象のエンティティを1つのリストに集約して返す。各抽出器は
この共通リストを反復し、`sheet_of()` / `source_block_of()` で帰属シート・由来ブロックを取得する。

既定設定（`expand_inserts=False` かつ `process_paperspace=False`）では、モデルスペースの
エンティティをそのまま（シート注釈なし・INSERT非展開で）返すため、従来挙動と完全に一致する
（後方互換／ゴールデン不変）。
"""
import logging

from ezdxf.document import Drawing

from dxf_extractor.config import InsertConfig

logger = logging.getLogger(__name__)

# 展開エンティティに付与する注釈属性名（ezdxf エンティティへ動的属性として付与）。
_SHEET_ATTR = "_dxfextr_sheet"
_BLOCK_ATTR = "_dxfextr_source_block"


def sheet_of(entity: object) -> str | None:
    """エンティティの帰属シート識別子を返す（未注釈は None）。"""
    return getattr(entity, _SHEET_ATTR, None)


def source_block_of(entity: object) -> str | None:
    """エンティティの由来ブロック名を返す（INSERT展開要素のみ。未注釈は None）。"""
    return getattr(entity, _BLOCK_ATTR, None)


def iter_entities(doc: Drawing, config: InsertConfig | None = None) -> list:
    """処理対象エンティティを集約したリストを返す。

    Args:
        doc: ezdxf Drawing。
        config: INSERT展開・複数シート設定。None は既定（従来挙動）。

    Returns:
        list: 反復対象エンティティのリスト（INSERT展開・シート注釈を反映）。
    """
    if config is None:
        config = InsertConfig()

    result: list = []
    # 可変の集計状態（件数・打ち切りフラグ・警告抑制）。
    state: dict = {"count": 0, "truncated": False, "warned_trunc": False, "warned_depth": False, "warned_cycle": set()}

    for sheet_id, layout in _target_layouts(doc, config):
        for entity in layout:
            _expand(entity, sheet_id, None, 0, config, state, result, frozenset())
            if state["truncated"]:
                break
        if state["truncated"]:
            break

    return result


def _target_layouts(doc: Drawing, config: InsertConfig) -> list:
    """処理対象レイアウトの (シートID, レイアウト) ペアを返す。

    既定はモデルスペースのみ（シートID=None=注釈なし）。`process_paperspace=True` の場合は
    全レイアウト（モデル＋ペーパースペース）を列挙し、シートIDにレイアウト名を用いる。
    """
    if config.process_paperspace:
        layouts: list = []
        for name in doc.layout_names():
            try:
                layouts.append((name, doc.layout(name)))
            except Exception:
                logger.warning("[WARN] レイアウト '%s' の取得に失敗したためスキップしました。", name)
        return layouts
    return [(None, doc.modelspace())]


def _expand(
    entity: object,
    sheet_id: str | None,
    source_block: str | None,
    depth: int,
    config: InsertConfig,
    state: dict,
    result: list,
    visiting: frozenset,
) -> None:
    """エンティティを（必要ならINSERT展開しつつ）result に追加する。

    深さ上限・件数上限・循環参照を検出した場合は安全に打ち切り、日本語警告を残す
    （FR-203 / 憲章V / SC-006）。サイレントには捨てない。
    """
    if state["truncated"]:
        return

    is_insert = entity.dxftype() == "INSERT"
    if is_insert and config.expand_inserts:
        try:
            block_name = entity.dxf.get("name", None)  # type: ignore[attr-defined]
        except Exception:
            block_name = None

        if depth >= config.max_depth:
            if not state["warned_depth"]:
                logger.warning(
                    "[WARN] INSERT展開が深さ上限(%d)に達したため一部を打ち切りました。",
                    config.max_depth,
                )
                state["warned_depth"] = True
            return

        if block_name is not None and block_name in visiting:
            if block_name not in state["warned_cycle"]:
                logger.warning(
                    "[WARN] INSERTブロック '%s' に循環参照を検出したため展開を打ち切りました。",
                    block_name,
                )
                state["warned_cycle"].add(block_name)
            return

        try:
            children = list(entity.virtual_entities())  # type: ignore[attr-defined]
        except Exception as e:
            logger.warning("[WARN] INSERTブロック '%s' の展開に失敗しました: %s", block_name, e)
            children = []

        new_visiting = visiting | ({block_name} if block_name else set())
        for child in children:
            _expand(child, sheet_id, block_name or source_block, depth + 1, config, state, result, new_visiting)
            if state["truncated"]:
                return
        return

    # 通常エンティティ（またはINSERT非展開）を記録する。
    if state["count"] >= config.max_entities:
        state["truncated"] = True
        if not state["warned_trunc"]:
            logger.warning(
                "[WARN] 展開後のエンティティ数が上限(%d)を超えたため打ち切りました。残りは未処理です。",
                config.max_entities,
            )
            state["warned_trunc"] = True
        return

    if sheet_id is not None:
        setattr(entity, _SHEET_ATTR, sheet_id)
    if source_block is not None:
        setattr(entity, _BLOCK_ATTR, source_block)
    result.append(entity)
    state["count"] += 1
