import csv
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from update_stickers import DATA_DIR, INVENTORY_PATH, load_inventory, normalize_sticker_id, save_json

REPEATED_PATH = DATA_DIR / "repeated.json"
REPEATED_SUMMARY_PATH = DATA_DIR / "repeated-summary.json"
REPEATED_CSV_PATH = DATA_DIR / "repeated.csv"

OPERATIONS = {"add", "remove"}


def normalize_quantity(value: Any) -> int:
    if isinstance(value, bool):
        raise ValueError("quantity must be a positive integer")

    if isinstance(value, int):
        quantity = value
    elif isinstance(value, str) and value.strip().isdigit():
        quantity = int(value.strip())
    else:
        raise ValueError("quantity must be a positive integer")

    if quantity < 1:
        raise ValueError("quantity must be a positive integer")

    return quantity


def parse_args(argv: list[str]) -> tuple[str, str, str]:
    if len(argv) < 1:
        raise SystemExit(
            "Usage: update_repeated_stickers.py [add|remove] "
            "'[\"BEL12\", {\"sticker_id\":\"SCO10\", \"quantity\":2}]' 'source'"
        )

    requested_operation = argv[0].lower()

    if requested_operation in OPERATIONS:
        if len(argv) < 2:
            raise SystemExit(
                "Usage: update_repeated_stickers.py [add|remove] "
                "'[\"BEL12\", {\"sticker_id\":\"SCO10\", \"quantity\":2}]' 'source'"
            )

        operation = requested_operation
        raw_stickers = argv[1]
        source = argv[2] if len(argv) > 2 else "gpt"
        return operation, raw_stickers, source

    raw_stickers = argv[0]
    source = argv[1] if len(argv) > 1 else "gpt"
    return "add", raw_stickers, source


def normalize_requested(raw_stickers: str) -> tuple[Counter[str], list[dict], list[str]]:
    try:
        requested = json.loads(raw_stickers)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Sticker payload must be a JSON list: {exc}") from exc

    if not isinstance(requested, list):
        raise SystemExit("Sticker payload must be a JSON list.")

    requested_counts: Counter[str] = Counter()
    requested_units = []
    invalid = []

    for item in requested:
        sticker_input = item
        quantity_input: Any = 1

        if isinstance(item, dict):
            sticker_input = item.get("sticker_id") or item.get("id") or item.get("code")
            quantity_input = item.get("quantity", item.get("count", 1))

        try:
            sticker_id = normalize_sticker_id(sticker_input)
            quantity = normalize_quantity(quantity_input)
        except ValueError as exc:
            invalid.append({
                "input": item,
                "reason": str(exc),
            })
            continue

        requested_counts[sticker_id] += quantity
        requested_units.extend([sticker_id] * quantity)

    return Counter(dict(sorted(requested_counts.items()))), invalid, sorted(requested_units)


def load_repeated_counts() -> Counter[str]:
    if not REPEATED_PATH.exists():
        return Counter()

    with REPEATED_PATH.open("r", encoding="utf-8") as f:
        repeated = json.load(f)

    sticker_entries = repeated.get("stickers", [])

    if not isinstance(sticker_entries, list):
        raise SystemExit("data/repeated.json must contain a stickers list.")

    counts: Counter[str] = Counter()

    for item in sticker_entries:
        sticker_input = item
        quantity_input: Any = 1

        if isinstance(item, dict):
            sticker_input = item.get("sticker_id") or item.get("id") or item.get("code")
            quantity_input = item.get("quantity", item.get("repeated_quantity", 1))

        try:
            sticker_id = normalize_sticker_id(sticker_input)
            quantity = normalize_quantity(quantity_input)
        except ValueError as exc:
            raise SystemExit(f"Invalid entry in data/repeated.json: {item} ({exc})") from exc

        counts[sticker_id] += quantity

    return counts


def count_items(counts: Counter[str]) -> list[dict]:
    return [
        {
            "sticker_id": sticker_id,
            "quantity": quantity,
        }
        for sticker_id, quantity in sorted(counts.items())
        if quantity > 0
    ]


def apply_operation(
    repeated_counts: Counter[str],
    inventory: dict,
    operation: str,
    requested_counts: Counter[str],
) -> dict:
    by_id = {sticker["sticker_id"]: sticker for sticker in inventory.get("stickers", [])}

    result = {
        "requested_counts": count_items(requested_counts),
        "added": [],
        "removed": [],
        "already_not_repeated": [],
        "insufficient_quantity": [],
        "not_found": [],
    }

    for sticker_id, quantity in requested_counts.items():
        if sticker_id not in by_id:
            result["not_found"].append({
                "sticker_id": sticker_id,
                "quantity": quantity,
            })
            continue

        if operation == "add":
            repeated_counts[sticker_id] += quantity
            result["added"].append({
                "sticker_id": sticker_id,
                "quantity": quantity,
                "new_quantity": repeated_counts[sticker_id],
            })
            continue

        current_quantity = repeated_counts.get(sticker_id, 0)

        if current_quantity <= 0:
            result["already_not_repeated"].append({
                "sticker_id": sticker_id,
                "quantity": quantity,
            })
            continue

        removed_quantity = min(quantity, current_quantity)
        remaining_quantity = current_quantity - removed_quantity

        if remaining_quantity > 0:
            repeated_counts[sticker_id] = remaining_quantity
        else:
            repeated_counts.pop(sticker_id, None)

        result["removed"].append({
            "sticker_id": sticker_id,
            "quantity": removed_quantity,
            "remaining_quantity": remaining_quantity,
        })

        if quantity > current_quantity:
            result["insufficient_quantity"].append({
                "sticker_id": sticker_id,
                "requested_quantity": quantity,
                "available_quantity": current_quantity,
                "removed_quantity": removed_quantity,
            })

    return result


def enrich_repeated_items(repeated_counts: Counter[str], inventory: dict) -> list[dict]:
    by_id = {sticker["sticker_id"]: sticker for sticker in inventory.get("stickers", [])}
    items = []

    for sticker_id, quantity in sorted(repeated_counts.items()):
        if quantity <= 0:
            continue

        sticker = by_id.get(sticker_id)

        if sticker is None:
            raise SystemExit(
                f"Repeated sticker {sticker_id} is not present in {INVENTORY_PATH}."
            )

        items.append({
            "sticker_id": sticker_id,
            "team_code": sticker.get("team_code"),
            "country": sticker.get("country"),
            "sticker_number": sticker.get("sticker_number"),
            "quantity": quantity,
        })

    return items


def write_repeated_csv(path: Path, stickers: list[dict]) -> None:
    fields = ["sticker_id", "team_code", "country", "sticker_number", "quantity"]

    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()

        for sticker in stickers:
            writer.writerow({
                "sticker_id": sticker.get("sticker_id"),
                "team_code": sticker.get("team_code"),
                "country": sticker.get("country"),
                "sticker_number": sticker.get("sticker_number"),
                "quantity": sticker.get("quantity"),
            })


def build_repeated_files(
    inventory: dict,
    repeated_counts: Counter[str],
    source: str,
    operation: str,
    result: dict,
) -> dict:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    repeated_stickers = enrich_repeated_items(repeated_counts, inventory)

    repeated_total = sum(sticker["quantity"] for sticker in repeated_stickers)
    unique_repeated_total = len(repeated_stickers)

    last_update_result = {
        "operation": operation,
        "requested_counts": result["requested_counts"],
        "added": result["added"],
        "removed": result["removed"],
        "already_not_repeated": result["already_not_repeated"],
        "insufficient_quantity": result["insufficient_quantity"],
        "not_found": result["not_found"],
        "invalid": result["invalid"],
    }

    repeated = {
        "schema_version": inventory.get("schema_version", "1.0"),
        "source": "github",
        "last_updated": now,
        "last_update_source": source,
        "totals": {
            "repeated_total": repeated_total,
            "unique_repeated_total": unique_repeated_total,
        },
        "stickers": repeated_stickers,
    }

    teams = {}

    for sticker in repeated_stickers:
        team_code = sticker.get("team_code")
        country = sticker.get("country")

        if team_code not in teams:
            teams[team_code] = {
                "team_code": team_code,
                "country": country,
                "repeated_total": 0,
                "unique_repeated_total": 0,
                "stickers": [],
            }

        teams[team_code]["repeated_total"] += sticker["quantity"]
        teams[team_code]["unique_repeated_total"] += 1
        teams[team_code]["stickers"].append({
            "sticker_id": sticker["sticker_id"],
            "sticker_number": sticker["sticker_number"],
            "quantity": sticker["quantity"],
        })

    repeated_summary = {
        "schema_version": inventory.get("schema_version", "1.0"),
        "source": "github",
        "last_updated": now,
        "last_update_source": source,
        "totals": {
            "repeated_total": repeated_total,
            "unique_repeated_total": unique_repeated_total,
        },
        "last_update_result": last_update_result,
        "teams": sorted(teams.values(), key=lambda item: item["team_code"]),
    }

    return {
        "repeated": repeated,
        "repeated_summary": repeated_summary,
        "repeated_stickers": repeated_stickers,
        "totals": repeated_summary["totals"],
    }


def save_repeated_files(files: dict) -> None:
    save_json(REPEATED_PATH, files["repeated"])
    save_json(REPEATED_SUMMARY_PATH, files["repeated_summary"])
    write_repeated_csv(REPEATED_CSV_PATH, files["repeated_stickers"])


def output_files_missing() -> bool:
    return not all(
        path.exists()
        for path in (REPEATED_PATH, REPEATED_SUMMARY_PATH, REPEATED_CSV_PATH)
    )


def run(operation: str, raw_stickers: str, source: str) -> dict:
    requested_counts, invalid, requested_units = normalize_requested(raw_stickers)

    inventory = load_inventory()
    repeated_counts = load_repeated_counts()
    result = apply_operation(repeated_counts, inventory, operation, requested_counts)
    result["invalid"] = invalid

    changed = bool(result["added"] or result["removed"])
    files = build_repeated_files(inventory, repeated_counts, source, operation, result)

    if changed or output_files_missing():
        save_repeated_files(files)

    return {
        "success": True,
        "changed": changed,
        "operation": operation,
        "requested": requested_units,
        "requested_counts": count_items(requested_counts),
        "added": result["added"],
        "removed": result["removed"],
        "already_not_repeated": result["already_not_repeated"],
        "insufficient_quantity": result["insufficient_quantity"],
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
