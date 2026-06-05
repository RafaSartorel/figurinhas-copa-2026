import csv
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

DATA_DIR = Path("data")

INVENTORY_PATH = DATA_DIR / "inventory.json"
SUMMARY_PATH = DATA_DIR / "summary.json"
OWNED_PATH = DATA_DIR / "owned.json"
MISSING_PATH = DATA_DIR / "missing.json"
INDEX_PATH = DATA_DIR / "index.json"
TEAMS_SUMMARY_PATH = DATA_DIR / "teams-summary.json"
OWNED_CSV_PATH = DATA_DIR / "owned.csv"
MISSING_CSV_PATH = DATA_DIR / "missing.csv"


def normalize_sticker_id(value: str) -> str:
    value = value.strip().upper().replace("-", "").replace(" ", "")
    team = value[:3]
    number = value[3:]

    if not team.isalpha() or len(team) != 3:
        raise ValueError(f"Invalid team code in sticker_id: {value}")

    if not number.isdigit():
        raise ValueError(f"Invalid sticker number in sticker_id: {value}")

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


def main() -> None:
    if len(sys.argv) < 2:
        raise SystemExit("Usage: update_stickers.py '[\"BEL12\",\"SCO10\"]' 'source'")

    raw_stickers = sys.argv[1]
    source = sys.argv[2] if len(sys.argv) > 2 else "gpt"

    requested_ids = json.loads(raw_stickers)
    requested_ids = [normalize_sticker_id(item) for item in requested_ids]
    requested_ids = sorted(set(requested_ids))

    inventory = load_inventory()
    stickers = inventory.get("stickers", [])

    by_id = {sticker["sticker_id"]: sticker for sticker in stickers}

    added = []
    already_owned = []
    not_found = []

    for sticker_id in requested_ids:
        sticker = by_id.get(sticker_id)

        if sticker is None:
            not_found.append(sticker_id)
            continue

        if sticker.get("owned") is True:
            already_owned.append(sticker_id)
            continue

        sticker["owned"] = True
        added.append(sticker_id)

    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    inventory["last_updated"] = now
    inventory["last_update_source"] = source
    inventory["last_added"] = added

    owned_stickers = [s for s in stickers if s.get("owned") is True]
    missing_stickers = [s for s in stickers if s.get("owned") is not True]

    owned_ids = sorted(s["sticker_id"] for s in owned_stickers)
    missing_ids = sorted(s["sticker_id"] for s in missing_stickers)

    total = len(stickers)
    owned_total = len(owned_stickers)
    missing_total = len(missing_stickers)
    progress = round((owned_total / total) * 100, 2) if total else 0

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
        "last_update_result": {
            "requested": requested_ids,
            "added": added,
            "already_owned": already_owned,
            "not_found": not_found,
        },
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

    save_json(INVENTORY_PATH, inventory)
    save_json(SUMMARY_PATH, summary)
    save_json(OWNED_PATH, owned)
    save_json(MISSING_PATH, missing)
    save_json(INDEX_PATH, index)
    save_json(TEAMS_SUMMARY_PATH, teams_summary)

    write_csv(OWNED_CSV_PATH, owned_stickers)
    write_csv(MISSING_CSV_PATH, missing_stickers)

    print(json.dumps({
        "success": True,
        "requested": requested_ids,
        "added": added,
        "already_owned": already_owned,
        "not_found": not_found,
        "totals": summary["totals"],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()