"""体系化ルール設定JSONの読込・検証（US3 / FR-014〜017）。

外部JSON設定からルールの有効/無効・適用順・パラメータを読み取り、実効ステップ列を生成する。
設定が未指定（None）の場合はレジストリ既定（現行ルール構成）を返す。
不正な設定は ``RuleConfigError`` を送出し、CLI層で終了コード3に写像する（FR-016）。
"""
import json
import logging
from pathlib import Path

from dxf_extractor.associators.registry import (
    RULE_REGISTRY,
    RuleStep,
    default_rule_steps,
)

logger = logging.getLogger(__name__)

# params で上書きを許可する StructurizeConfig のキー（契約 rules_config.schema.json）。
_ALLOWED_PARAM_KEYS = frozenset(
    {
        "confidence_threshold",
        "tolerances.delta",
        "tolerances.d_threshold",
        "tolerances.delta_y_ratio",
    }
)


class RuleConfigError(ValueError):
    """ルール設定JSONが不正な場合に送出する例外（日本語理由を保持）。"""


def load_rule_steps(rules_config: str | Path | None) -> list[RuleStep]:
    """ルール設定からルールステップ列を生成する。

    Args:
        rules_config: ルール設定JSONファイルのパス。Noneで既定（現行ルール構成）。

    Returns:
        list[RuleStep]: 適用順のルールステップ列（enabled=false は除外済み）。

    Raises:
        RuleConfigError: 設定が不正（読込失敗・パース不能・未知id・未許可paramsキー等）の場合。
    """
    if rules_config is None:
        return default_rule_steps()

    path = Path(rules_config)
    if not path.exists():
        raise RuleConfigError(f"ルール設定ファイルが見つかりません: {path}")

    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise RuleConfigError(f"ルール設定ファイルのJSON解析に失敗しました: {path} ({e})") from e
    except OSError as e:
        raise RuleConfigError(f"ルール設定ファイルの読み込みに失敗しました: {path} ({e})") from e

    return _build_steps(raw, path)


def _build_steps(raw: object, path: Path) -> list[RuleStep]:
    """パース済みの設定オブジェクトからルールステップ列を組み立てる。"""
    if not isinstance(raw, dict) or "rules" not in raw:
        raise RuleConfigError(f"ルール設定にトップレベルキー 'rules' がありません: {path}")
    rules = raw["rules"]
    if not isinstance(rules, list):
        raise RuleConfigError(f"'rules' は配列でなければなりません: {path}")

    seen: dict[str, int] = {}
    steps: list[RuleStep] = []
    for index, entry in enumerate(rules):
        if not isinstance(entry, dict):
            raise RuleConfigError(f"rules[{index}] はオブジェクトでなければなりません: {path}")

        rule_id = entry.get("id")
        if rule_id is None:
            raise RuleConfigError(f"rules[{index}] に必須キー 'id' がありません: {path}")
        if rule_id not in RULE_REGISTRY:
            raise RuleConfigError(
                f"未知のルールID '{rule_id}' が指定されました（rules[{index}]）。"
                f"有効なID: {sorted(RULE_REGISTRY)}"
            )

        default_label, rule_cls = RULE_REGISTRY[rule_id]
        params = _validate_params(entry.get("params", {}), rule_id, path)
        label = entry.get("label") or default_label
        enabled = entry.get("enabled", True)

        step = RuleStep(label=label, rule_cls=rule_cls, params=params)

        if rule_id in seen:
            # id 重複は後勝ち（後出の定義・順序を採用）。
            logger.warning("[WARN] ルールID '%s' が重複定義されています。後出の定義を採用します。", rule_id)
            if enabled:
                steps[seen[rule_id]] = step
            else:
                steps.pop(seen[rule_id])
                # 後続の参照位置を詰める
                seen = {k: (v - 1 if v > seen[rule_id] else v) for k, v in seen.items() if k != rule_id}
            continue

        if enabled:
            seen[rule_id] = len(steps)
            steps.append(step)

    return steps


def _validate_params(params: object, rule_id: str, path: Path) -> dict:
    """params の許可キーを検証して返す。"""
    if not isinstance(params, dict):
        raise RuleConfigError(f"rules（id={rule_id}）の 'params' はオブジェクトでなければなりません: {path}")
    for key in params:
        if key not in _ALLOWED_PARAM_KEYS:
            raise RuleConfigError(
                f"ルール '{rule_id}' の params に未許可のキー '{key}' が指定されました。"
                f"許可キー: {sorted(_ALLOWED_PARAM_KEYS)}"
            )
    return dict(params)
