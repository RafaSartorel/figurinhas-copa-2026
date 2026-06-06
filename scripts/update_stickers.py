import csv
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

DATA_DIR = Path("data")

INVENTORY_PATH = DATA_DIR / "inventory.json"
SUMMARY_PATH = DATA_DIR / "summary.json"
OWNED_PATH = DATA_DIR / "owned.json"
MISSING_PATH = DATA_DIR / "missing.json"
INDEX_PATH = DATA_DIR / "index.json"
TEAMS_SUMMARY_PATH = DATA_DIR / "teams-summary.json"
OWNED_CSV_PATH = DATA_DIR / "owned.csv"
MISSING_CSV_PATH = DATA_DIR / "missing.csv"

OPERATIONS = {"add", "remove"}


def normalize_sticker_id(value: Any) -> str:
    if not isinstance(value, str):
        raise ValueError("sticker_id must be a string")

    normalized = value.strip().upper().replace("-", "").replace(" ", "")
    team = normalized[:3]
    number = normalized[3:]

    if not team.isalpha() or len(team) != 3:
        raise ValueError(f"invalid team code in sticker_id: {value}")

    if not number.isdigit() or len(number) not in (1, 2):
        raise ValueError(f"invalid sticker number in sticker_id: {value}")

    return f"{team}{int(number):02d}"


def load_inventory() -> dict:
    with INVENTORY_PATH.open("r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path: Path, data: dict) -> None:
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")


def write_csv(path: Path, stickers: list[dict]) -> None:
    fields = ["sticker_id", "team_code", "country", "sticker_number", "owned"]

    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()

        for sticker in stickers:
            writer.writerow({
                "sticker_id": sticker.get("sticker_id"),
                "team_code": sticker.get("team_code"),
                "country": sticker.get("country"),
                "sticker_number": sticker.get("sticker_number"),
                "owned": sticker.get("owned"),
            })


def parse_args(argv: list[str]) -> tuple[str, str, str]:
    if len(argv) < 1:
        raise SystemExit(
            "Usage: update_stickers.py [add|remove] '[\"BEL12\",\"SCO10\"]' 'source'"
        )

    requested_operation = argv[0].lower()

    if requested_operation in OPERATIONS:
        if len(argv) < 2:
            raise SystemExit(
                "Usage: update_stickers.py [add|remove] '[\"BEL12\",\"SCO10\"]' 'source'"
            )

        operation = requested_operation
        raw_stickers = argv[1]
        source = argv[2] if len(argv) > 2 else "gpt"
        return operation, raw_stickers, source

    raw_stickers = argv[0]
    source = argv[1] if len(argv) > 1 else "gpt"
    return "add", raw_stickers, source


def normalize_requested(raw_stickers: str) -> tuple[list[str], list[dict]]:
    try:
        requested = json.loads(raw_stickers)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Sticker payload must be a JSON list: {exc}") from exc

    if not isinstance(requested, list):
        raise SystemExit("Sticker payload must be a JSON list.")

    normalized_ids = []
    invalid = []

    for item in requested:
        try:
            normalized_ids.append(normalize_sticker_id(item))
        except ValueError as exc:
            invalid.append({
                "input": item,
                "reason": str(exc),
            })

    return sorted(set(normalized_ids)), invalid


def apply_operation(stickers: list[dict], operation: str, requested_ids: list[str]) -> dict:
    by_id = {sticker["sticker_id"]: sticker for sticker in stickers}

    result = {
        "requested": requested_ids,
        "added": [],
        "removed": [],
        "already_owned": [],
        "already_missing": [],
        "not_found": [],
    }

    for sticker_id in requested_ids:
        sticker = by_id.get(sticker_id)

        if sticker is None:
            result["not_found"].append(sticker_id)
            continue

        has_sticker = sticker.get("owned") is True

        if operation == "add":
            if has_sticker:
                result["already_owned"].append(sticker_id)
                continue

            sticker["owned"] = True
            result["added"].append(sticker_id)
            continue

        if not has_sticker:
            result["already_missing"].append(sticker_id)
            continue

        sticker["owned"] = False
        result["removed"].append(sticker_id)

    return result


def build_derived_files(inventory: dict, source: str, operation: str, result: dict) -> dict:
    stickers = inventory.get("stickers", [])
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    owned_stickers = [s for s in stickers if s.get("owned") is True]
    missing_stickers = [s for s in stickers if s.get("owned") is not True]

    owned_ids = sorted(s["sticker_id"] for s in owned_stickers)
    missing_ids = sorted(s["sticker_id"] for s in missing_stickers)

    total = len(stickers)
    owned_total = len(owned_stickers)
    missing_total = len(missing_stickers)
    progress = round((owned_total / total) * 100, 2) if total else 0

    inventory["total_stickers"] = total
    inventory["owned_count"] = owned_total
    inventory["missing_count"] = missing_total
    inventory["last_updated"] = now
    inventory["last_update_source"] = source
    inventory["last_added"] = result["added"]
    inventory["last_removed"] = result["removed"]

    last_update_result = {
        "operation": operation,
        "requested": result["requested"],
        "added": result["added"],
        "removed": result["removed"],
        "already_owned": result["already_owned"],
        "already_missing": result["already_missing"],
        "not_found": result["not_found"],
        "invalid": result["invalid"],
    }

    summary = {
        "schema_version": inventory.get("schema_version", "1.0"),
        "source": "github",
        "last_updated": now,
        "last_update_source": source,
        "totals": {
            "stickers_total": total,
            "owned_total": owned_total,
            "missing_total": missing_total,
            "progress_percent": progress,
        },
        "last_update_result": last_update_result,
    }

    owned = {
        "schema_version": inventory.get("schema_version", "1.0"),
        "source": "github",
        "last_updated": now,
        "stickers": owned_ids,
    }

    missing = {
        "schema_version": inventory.get("schema_version", "1.0"),
        "source": "github",
        "last_updated": now,
        "stickers": missing_ids,
    }

    index = {
        "schema_version": inventory.get("schema_version", "1.0"),
        "source": "github",
        "last_updated": now,
        "stickers": {
            sticker["sticker_id"]: {
                "team_code": sticker.get("team_code"),
                "country": sticker.get("country"),
                "sticker_number": sticker.get("sticker_number"),
                "owned": sticker.get("owned"),
            }
            for sticker in stickers
        },
    }

    teams = {}

    for sticker in stickers:
        team_code = sticker.get("team_code")
        country = sticker.get("country")

        if team_code not in teams:
            teams[team_code] = {
                "team_code": team_code,
                "country": country,
                "stickers_total": 0,
                "owned_total": 0,
                "missing_total": 0,
                "owned": [],
                "missing": [],
            }

        teams[team_code]["stickers_total"] += 1

        if sticker.get("owned") is True:
            teams[team_code]["owned_total"] += 1
            teams[team_code]["owned"].append(sticker["sticker_id"])
        else:
            teams[team_code]["missing_total"] += 1
            teams[team_code]["missing"].append(sticker["sticker_id"])

    teams_summary = {
        "schema_version": inventory.get("schema_version", "1.0"),
        "source": "github",
        "last_updated": now,
        "teams": sorted(teams.values(), key=lambda x: x["team_code"]),
    }

    return {
        "inventory": inventory,
        "summary": summary,
        "owned": owned,
        "missing": missing,
        "index": index,
        "teams_summary": teams_summary,
        "owned_stickers": owned_stickers,
        "missing_stickers": missing_stickers,
        "totals": summary["totals"],
    }


def save_derived_files(files: dict) -> None:
    save_json(INVENTORY_PATH, files["inventory"])
    save_json(SUMMARY_PATH, files["summary"])
    save_json(OWNED_PATH, files["owned"])
    save_json(MISSING_PATH, files["missing"])
    save_json(INDEX_PATH, files["index"])
    save_json(TEAMS_SUMMARY_PATH, files["teams_summary"])

    write_csv(OWNED_CSV_PATH, files["owned_stickers"])
    write_csv(MISSING_CSV_PATH, files["missing_stickers"])


def run(operation: str, raw_stickers: str, source: str) -> dict:
    requested_ids, invalid = normalize_requested(raw_stickers)

    inventory = load_inventory()
    stickers = inventory.get("stickers", [])
    result = apply_operation(stickers, operation, requested_ids)
    result["invalid"] = invalid

    changed = bool(result["added"] or result["removed"])
    files = build_derived_files(inventory, source, operation, result)

    if changed:
        save_derived_files(files)

    return {
        "success": True,
        "changed": changed,
        "operation": operation,
        "requested": requested_ids,
        "added": result["added"],
        "removed": result["removed"],
        "already_owned": result["already_owned"],
        "already_missing": result["already_missing"],
        "not_found": result["not_found"],
        "invalid": invalid,
        "totals": files["totals"],
    }


def main(argv: Optional[list[str]] = None) -> None:
    operation, raw_stickers, source = parse_args(sys.argv[1:] if argv is None else argv)
    output = run(operation, raw_stickers, source)
    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
