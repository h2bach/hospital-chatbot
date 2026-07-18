#!/usr/bin/env python3
"""Tạo mẫu và nhập lịch tuần hiện hành cho API thông tin Bệnh viện Tim Hà Nội."""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import tempfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

FIELDS = [
    "assignment_id", "week_start", "schedule_date", "facility_id", "area_id",
    "room_id", "staff_id", "staff_name", "shift_code", "start_time", "end_time",
    "assignment_scope", "assignment_status", "source_version", "source_image",
    "note", "published_status",
]
VALID_SHIFTS = {"FULL_DAY", "AM", "PM"}
VALID_SCOPES = {"ROOM", "AREA"}
VALID_STATUSES = {"WORKING", "OFF", "UNASSIGNED", "PROCEDURE", "AREA_DUTY"}


def default_data_dir() -> Path:
    return Path(__file__).resolve().parents[1] / "hospital-data"


def read_json(path: Path):
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def next_monday(today: date | None = None) -> date:
    today = today or date.today()
    days = (7 - today.weekday()) % 7
    if days == 0:
        days = 7
    return today + timedelta(days=days)


def parse_date(raw: str, label: str) -> date:
    try:
        return date.fromisoformat(raw)
    except ValueError as exc:
        raise ValueError(f"{label} phải có dạng YYYY-MM-DD: {raw!r}") from exc


def parse_week_start(raw: str | None) -> date:
    value = next_monday() if not raw or raw == "next" else parse_date(raw, "week_start")
    if value.weekday() != 0:
        raise ValueError(f"week_start phải là Thứ 2: {value.isoformat()}")
    return value


def pattern_days(text: str) -> list[int]:
    normalized = (text or "").strip()
    exact = {
        "Thứ 2-Thứ 6": [0, 1, 2, 3, 4],
        "Thứ 2-Thứ 5": [0, 1, 2, 3],
        "Thứ 2/4/6": [0, 2, 4],
        "Thứ 3/5": [1, 3],
        "Thứ 3": [1],
        "Thứ 5": [3],
        "Thứ 6": [4],
        "Thứ 7": [5],
        "Chủ nhật": [6],
    }
    return exact.get(normalized, [])


def make_suggestions(data_dir: Path, week_start: date) -> list[dict[str, str]]:
    patterns = read_json(data_dir / "assignment_patterns.json")
    rooms = {row["room_id"]: row for row in read_json(data_dir / "rooms.json")}
    doctors = {row["staff_id"]: row for row in read_json(data_dir / "doctors.json")}
    output: list[dict[str, str]] = []
    counter = 1
    for pattern in patterns:
        days = pattern_days(pattern.get("applies_on", ""))
        staff_id = pattern.get("staff_id")
        room_id = pattern.get("room_or_scope", "")
        shift = {"Cả ngày": "FULL_DAY", "Sáng": "AM", "Chiều": "PM"}.get(pattern.get("shift"))
        if not days or not staff_id or not shift or room_id not in rooms:
            continue
        room = rooms[room_id]
        doctor = doctors[staff_id]
        for day_index in days:
            row = {field: "" for field in FIELDS}
            row.update({
                "assignment_id": f"ASG-{week_start:%Y%m%d}-{counter:04d}",
                "week_start": week_start.isoformat(),
                "schedule_date": (week_start + timedelta(days=day_index)).isoformat(),
                "facility_id": room["facility_id"],
                "area_id": room["area_id"],
                "room_id": room_id,
                "staff_id": staff_id,
                "staff_name": doctor["full_name"],
                "shift_code": shift,
                "start_time": room["opens_at"] if shift == "FULL_DAY" else "",
                "end_time": room["closes_at"] if shift == "FULL_DAY" else "",
                "assignment_scope": "ROOM",
                "assignment_status": "WORKING",
                "source_version": f"PATTERN_SUGGESTION_{week_start.isoformat()}_v1",
                "note": f"Gợi ý từ {pattern['pattern_id']} ({pattern['confidence']}); phải xác minh trước khi công bố.",
                "published_status": "DRAFT",
            })
            output.append(row)
            counter += 1
    return output


def command_template(args: argparse.Namespace) -> None:
    data_dir = args.data_dir.resolve()
    week_start = parse_week_start(args.week_start)
    output = args.output or Path(f"schedule_{week_start.isoformat()}.csv")
    rows = make_suggestions(data_dir, week_start) if args.suggest_from_patterns else []
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    print(f"Đã tạo {output} với {len(rows)} dòng nháp cho tuần {week_start.isoformat()}.")
    if rows:
        print("Các dòng là gợi ý từ mẫu quan sát; hãy kiểm tra rồi mới import --publish.")


def validate_and_normalize(rows: list[dict[str, str]], data_dir: Path, publish: bool) -> tuple[date, list[dict]]:
    if not rows:
        raise ValueError("CSV không có dòng lịch nào")
    facilities = {row["facility_id"] for row in read_json(data_dir / "facilities.json")}
    rooms = {row["room_id"]: row for row in read_json(data_dir / "rooms.json")}
    doctors = {row["staff_id"]: row for row in read_json(data_dir / "doctors.json")}
    normalized: list[dict] = []
    seen_ids: set[str] = set()
    doctor_assignments: dict[tuple[str, str], list[tuple[str, str, str, str]]] = {}
    expected_week: date | None = None

    for number, source_row in enumerate(rows, start=2):
        row = {field: (source_row.get(field) or "").strip() for field in FIELDS}
        week_start = parse_date(row["week_start"], f"dòng {number} week_start")
        if week_start.weekday() != 0:
            raise ValueError(f"dòng {number}: week_start phải là Thứ 2")
        if expected_week is None:
            expected_week = week_start
        elif week_start != expected_week:
            raise ValueError(f"dòng {number}: chỉ được nhập một tuần trong mỗi file")
        schedule_date = parse_date(row["schedule_date"], f"dòng {number} schedule_date")
        if not week_start <= schedule_date <= week_start + timedelta(days=6):
            raise ValueError(f"dòng {number}: schedule_date nằm ngoài tuần")
        if row["facility_id"] not in facilities:
            raise ValueError(f"dòng {number}: facility_id không tồn tại: {row['facility_id']}")
        if row["shift_code"] not in VALID_SHIFTS:
            raise ValueError(f"dòng {number}: shift_code phải thuộc {sorted(VALID_SHIFTS)}")
        if row["assignment_scope"] not in VALID_SCOPES:
            raise ValueError(f"dòng {number}: assignment_scope phải thuộc {sorted(VALID_SCOPES)}")
        if row["assignment_status"] not in VALID_STATUSES:
            raise ValueError(f"dòng {number}: assignment_status phải thuộc {sorted(VALID_STATUSES)}")
        if row["assignment_scope"] == "ROOM":
            room = rooms.get(row["room_id"])
            if not room:
                raise ValueError(f"dòng {number}: room_id không tồn tại: {row['room_id']}")
            if room["facility_id"] != row["facility_id"] or room["area_id"] != row["area_id"]:
                raise ValueError(f"dòng {number}: cơ sở/khu không khớp room_id")
            if row["shift_code"] == "FULL_DAY":
                row["start_time"] = row["start_time"] or room["opens_at"]
                row["end_time"] = row["end_time"] or room["closes_at"]
        if row["assignment_status"] in {"WORKING", "AREA_DUTY"}:
            doctor = doctors.get(row["staff_id"])
            if not doctor:
                raise ValueError(f"dòng {number}: staff_id bác sĩ không tồn tại: {row['staff_id']}")
            row["staff_name"] = doctor["full_name"]
        elif row["staff_id"] and row["staff_id"] not in doctors:
            raise ValueError(f"dòng {number}: staff_id không tồn tại: {row['staff_id']}")
        if bool(row["start_time"]) != bool(row["end_time"]):
            raise ValueError(f"dòng {number}: start_time và end_time phải cùng có hoặc cùng để trống")

        assignment_id = row["assignment_id"] or f"ASG-{week_start:%Y%m%d}-{number - 1:04d}"
        if assignment_id in seen_ids:
            raise ValueError(f"dòng {number}: assignment_id bị trùng: {assignment_id}")
        seen_ids.add(assignment_id)
        row["assignment_id"] = assignment_id
        row["published_status"] = "PUBLISHED" if publish else "DRAFT"
        row["source_version"] = row["source_version"] or f"MANUAL_{week_start.isoformat()}_v1"

        if row["staff_id"] and row["assignment_status"] in {"WORKING", "AREA_DUTY"}:
            key = (row["staff_id"], row["schedule_date"])
            interval = (row["shift_code"], row["start_time"], row["end_time"], row["assignment_id"])
            for previous in doctor_assignments.setdefault(key, []):
                if shifts_overlap(previous, interval):
                    raise ValueError(
                        f"dòng {number}: bác sĩ {row['staff_id']} bị trùng ca với {previous[3]}"
                    )
            doctor_assignments[key].append(interval)
        normalized.append({key: (value if value != "" else None) for key, value in row.items()})
    assert expected_week is not None
    return expected_week, normalized


def shifts_overlap(left: tuple[str, str, str, str], right: tuple[str, str, str, str]) -> bool:
    if left[0] == right[0]:
        return True
    if left[1] and left[2] and right[1] and right[2]:
        return max(left[1], right[1]) < min(left[2], right[2])
    return left[0] == "FULL_DAY" or right[0] == "FULL_DAY"


def command_import(args: argparse.Namespace) -> None:
    data_dir = args.data_dir.resolve()
    with args.csv.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        missing = [field for field in FIELDS if field not in (reader.fieldnames or [])]
        if missing:
            raise ValueError(f"CSV thiếu cột: {', '.join(missing)}")
        rows = list(reader)
    week_start, assignments = validate_and_normalize(rows, data_dir, args.publish)
    status = "PUBLISHED" if args.publish else "DRAFT"
    if args.source_version:
        for assignment in assignments:
            assignment["source_version"] = args.source_version
    payload = {
        "schema_version": "1.0",
        "week_start": week_start.isoformat(),
        "week_end": (week_start + timedelta(days=6)).isoformat(),
        "published_status": status,
        "source_version": args.source_version or f"MANUAL_{week_start.isoformat()}_v1",
        "imported_at": datetime.now(timezone.utc).isoformat(),
        "assignments": assignments,
    }
    target = data_dir / "current_schedule.json"
    data_dir.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix="current_schedule_", suffix=".json", dir=data_dir)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        os.replace(temporary, target)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    print(f"Đã thay lịch hiện hành bằng {len(assignments)} phân công tuần {week_start.isoformat()} ({status}).")
    print("Lịch cũ không được lưu lại.")


def command_status(args: argparse.Namespace) -> None:
    schedule = read_json(args.data_dir.resolve() / "current_schedule.json")
    print(json.dumps({
        "week_start": schedule.get("week_start"),
        "week_end": schedule.get("week_end"),
        "published_status": schedule.get("published_status"),
        "source_version": schedule.get("source_version"),
        "imported_at": schedule.get("imported_at"),
        "assignment_count": len(schedule.get("assignments", [])),
    }, ensure_ascii=False, indent=2))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=default_data_dir())
    subparsers = parser.add_subparsers(dest="command", required=True)

    template = subparsers.add_parser("template", help="Tạo CSV lịch tuần kế tiếp")
    template.add_argument("--week-start", default="next", help="YYYY-MM-DD hoặc next")
    template.add_argument("--output", type=Path)
    template.add_argument("--suggest-from-patterns", action="store_true", help="Điền gợi ý DRAFT từ mẫu quan sát có thể ánh xạ chắc chắn")
    template.set_defaults(handler=command_template)

    importer = subparsers.add_parser("import", help="Kiểm tra và thay current_schedule.json")
    importer.add_argument("csv", type=Path)
    importer.add_argument("--publish", action="store_true", help="Công bố để API/MCP dùng; mặc định chỉ DRAFT")
    importer.add_argument("--source-version")
    importer.set_defaults(handler=command_import)

    status = subparsers.add_parser("status", help="Xem lịch hiện hành")
    status.set_defaults(handler=command_status)
    return parser


def main() -> int:
    try:
        args = build_parser().parse_args()
        args.handler(args)
        return 0
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"Lỗi: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
