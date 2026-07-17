from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any


def export(data: dict[str, list[dict[str, Any]]], directory: Path, formats: list[str], pretty: bool = False) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    for table, rows in data.items():
        if "json" in formats:
            (directory / f"{table}.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2 if pretty else None), encoding="utf-8")
        if "jsonl" in formats:
            with (directory / f"{table}.jsonl").open("w", encoding="utf-8", newline="\n") as f:
                for row in rows:
                    f.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
        if "csv" in formats and rows:
            fields = list(rows[0])
            with (directory / f"{table}.csv").open("w", encoding="utf-8", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=fields)
                writer.writeheader()
                for row in rows:
                    writer.writerow({k: json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else v for k, v in row.items()})


def load_json_directory(directory: Path) -> dict[str, list[dict[str, Any]]]:
    files = sorted(directory.glob("*.json"))
    return {p.stem: json.loads(p.read_text(encoding="utf-8")) for p in files if p.name != "validation-report.json"}

