"""Stdlib-only loader and validator for the JSON routing catalogue."""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
DEFAULT_SKILL = HERE.parent / "SKILL.md"
DEFAULT_CATALOG = HERE.parent / "references" / "routing-catalog.json"

_CATALOG_CACHE: dict[tuple[str, int, int, int, int], dict[str, Any]] = {}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(65536)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def catalog_path_for(skill_path: Path | None = None, catalog_path: Path | None = None) -> Path:
    if catalog_path is not None:
        return Path(catalog_path)
    base = Path(skill_path).parent if skill_path is not None else DEFAULT_SKILL.parent
    return base / "references" / "routing-catalog.json"


def _allowed_efforts(catalog: dict[str, Any], model_key: str) -> list[str]:
    model = catalog["models"][model_key]
    if isinstance(model.get("effort_ids"), dict):
        return list(model["effort_ids"].keys())
    if isinstance(model.get("efforts"), list):
        return list(model["efforts"])
    provider = catalog["providers"][model["provider"]]
    return list(provider["efforts"])


def validate_catalog_structure(catalog: dict[str, Any]) -> None:
    providers = catalog.get("providers")
    models = catalog.get("models")
    categories = catalog.get("categories")
    if not isinstance(providers, dict) or not providers:
        raise ValueError("routing catalog requires a non-empty providers mapping")
    if not isinstance(models, dict) or not models:
        raise ValueError("routing catalog requires a non-empty models mapping")
    if not isinstance(categories, dict) or not categories:
        raise ValueError("routing catalog requires a non-empty categories mapping")
    for model_key, model in models.items():
        provider_key = model.get("provider")
        if provider_key not in providers:
            raise ValueError(f"model {model_key} names unknown provider {provider_key!r}")
        ids = model.get("effort_ids")
        if ids is not None and (
            not isinstance(ids, dict)
            or not ids
            or any(
                effort not in providers[provider_key]["efforts"]
                or not isinstance(mid, str)
                or not mid
                for effort, mid in ids.items()
            )
            or len(set(ids.values())) != len(ids)
            or model.get("id") not in ids.values()
        ):
            raise ValueError(f"invalid model effort_ids mapping for {model_key}")
    for cat_key, row in categories.items():
        if row.get("of") == "required":
            continue
        chain = row.get("chain")
        if not isinstance(chain, list) or len(chain) < 2:
            raise ValueError(f"category {cat_key} requires a fallback chain with at least two entries")
        first_provider = None
        for idx, entry in enumerate(chain):
            mkey = entry.get("model")
            effort = entry.get("effort")
            if mkey not in models:
                raise ValueError(f"category {cat_key} references unknown model {mkey!r}")
            provider_key = models[mkey]["provider"]
            provider = providers[provider_key]
            if provider.get("enabled") is False:
                raise ValueError(f"category {cat_key} routes to disabled provider {provider_key!r}")
            if provider.get("explicit_only") is True:
                raise ValueError(f"category {cat_key} routes to explicit-only provider {provider_key!r}")
            if effort not in _allowed_efforts(catalog, mkey):
                raise ValueError(f"invalid effort {effort!r} for model {mkey!r} in category {cat_key}")
            if idx == 0:
                first_provider = provider_key
            elif idx == 1 and provider_key == first_provider:
                raise ValueError(f"category {cat_key} requires a backup on another provider")


def _sync_skill_table(catalog: dict[str, Any], skill_path: Path) -> None:
    text = skill_path.read_text(encoding="utf-8")
    start, end = "<!-- routing-table:start -->", "<!-- routing-table:end -->"
    if text.count(start) != 1 or text.count(end) != 1:
        raise ValueError("SKILL.md needs one marked routing table")
    table = text.split(start, 1)[1].split(end, 1)[0]
    display_to_key = {m["display"]: key for key, m in catalog["models"].items()}
    categories = catalog["categories"]
    seen = set()
    for line in table.splitlines():
        if not line.startswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if cells[0] == "Category" or all(set(cell) <= set("-: ") for cell in cells):
            continue
        if len(cells) != 7:
            raise ValueError("routing rows must have seven columns")
        tier, name, _use_when, first_disp, effort, backup_disp, backup_effort = cells
        if tier in seen or tier not in categories:
            raise ValueError(f"duplicate or unknown category: {tier}")
        seen.add(tier)
        row = categories[tier]
        row["metadata_name"] = row["name"]
        row["name"] = name
        if row.get("of") == "required":
            if cells[3] != "Inherit reviewed category" or cells[5] != "Exclude builder" or cells[4] not in {"-", "—"} or cells[6] not in {"-", "—"}:
                raise ValueError("review must inherit its category and exclude the builder")
            continue
        resolved_slots = []
        for disp, level in ((first_disp, effort), (backup_disp, backup_effort)):
            if disp not in display_to_key:
                raise ValueError(f"unknown model in category {tier}: {disp}")
            mkey = display_to_key[disp]
            if level not in _allowed_efforts(catalog, mkey):
                raise ValueError(f"invalid effort for {disp}: {level}")
            resolved_slots.append({"model": mkey, "effort": level})
        first_provider = catalog["models"][resolved_slots[0]["model"]]["provider"]
        backup_provider = catalog["models"][resolved_slots[1]["model"]]["provider"]
        if first_provider == backup_provider:
            raise ValueError(f"category {tier} requires a backup on another provider")
        row["first"] = resolved_slots[0]
        row["backup"] = resolved_slots[1]
        tail = [
            item
            for item in row.get("chain", [])[2:]
            if item != resolved_slots[0] and item != resolved_slots[1]
        ]
        row["chain"] = [resolved_slots[0], resolved_slots[1], *tail]
    missing = set(categories) - seen
    if missing:
        raise ValueError(f"routing table missing categories: {', '.join(sorted(missing))}")


def _populate_compat_fields(catalog: dict[str, Any]) -> None:
    categories = catalog["categories"]
    for row in categories.values():
        if row.get("of") == "required":
            continue
        chain = row.get("chain") or []
        if len(chain) >= 1 and "first" not in row:
            row["first"] = dict(chain[0])
        if len(chain) >= 2 and "backup" not in row:
            row["backup"] = dict(chain[1])
        if "metadata_name" not in row:
            row["metadata_name"] = row["name"]
    catalog["tiers"] = categories


def load_catalog(
    skill_path: Path | None = None,
    catalog_path: Path | None = None,
    *,
    require_skill_table: bool = True,
) -> dict[str, Any]:
    skill = Path(skill_path) if skill_path is not None else DEFAULT_SKILL
    cpath = catalog_path_for(skill, catalog_path)
    cache_key = None
    try:
        st_cat = cpath.stat()
        st_skill = skill.stat() if (require_skill_table and skill.is_file()) else None
        cache_key = (
            f"{cpath.resolve()}::{skill.resolve() if st_skill else ''}",
            st_cat.st_mtime_ns,
            st_cat.st_size,
            st_skill.st_mtime_ns if st_skill else 0,
            st_skill.st_size if st_skill else 0,
        )
        cached = _CATALOG_CACHE.get(cache_key)
        if cached is not None:
            return copy.deepcopy(cached)
    except OSError:
        cache_key = None
    catalog = json.loads(cpath.read_text(encoding="utf-8"))
    validate_catalog_structure(catalog)
    if require_skill_table and skill.is_file():
        text = skill.read_text(encoding="utf-8")
        if "<!-- routing-table:start -->" in text:
            _sync_skill_table(catalog, skill)
        else:
            raise ValueError("SKILL.md needs one marked routing table")
    _populate_compat_fields(catalog)
    if cache_key is not None:
        if len(_CATALOG_CACHE) >= 32:
            _CATALOG_CACHE.clear()
        _CATALOG_CACHE[cache_key] = copy.deepcopy(catalog)
    return catalog


def model_entry(catalog: dict[str, Any], key: str, effort: str | None = None) -> dict[str, Any]:
    entry = dict(catalog["models"][key])
    entry["id"] = entry.get("effort_ids", {}).get(effort, entry["id"])
    entry["key"] = key
    return entry


def find_model(catalog: dict[str, Any], model_id: str) -> dict[str, Any] | None:
    if model_id in catalog["models"]:
        return model_entry(catalog, model_id)
    for key, model in catalog["models"].items():
        aliases = model.get("aliases") or []
        family_aliases = model.get("family_aliases") or []
        variants = (model.get("effort_ids") or {}).values()
        if (
            model.get("id") == model_id
            or model_id in aliases
            or model.get("family") == model_id
            or model_id in family_aliases
            or model_id in variants
        ):
            entry = model_entry(catalog, key)
            if model_id in variants:
                entry["id"] = model_id
            return entry
    return None
