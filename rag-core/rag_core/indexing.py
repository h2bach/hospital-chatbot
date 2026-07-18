from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import unicodedata
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable


TOKEN_RE = re.compile(r"[\wÀ-ỹ]+", re.UNICODE)
NUMBERED_ROW_RE = re.compile(r"^\d+(?:[,.]\d+)?$")
PAGE_RE = re.compile(r"<!--\s*(?:Trang PDF|page:)\s*(\d+)", re.IGNORECASE)
BHYT_CHUNK_ID_RE = re.compile(r'^\s*"chunk_id"\s*:\s*"([^"]+)"')


def tokenize(text: str) -> list[str]:
    return TOKEN_RE.findall(unicodedata.normalize("NFC", text.lower()))


def stable_id(prefix: str, *parts: object) -> str:
    raw = "\x1f".join(str(part).strip() for part in parts)
    return f"{prefix}_{hashlib.sha256(raw.encode('utf-8')).hexdigest()[:20]}"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return f"sha256:{digest.hexdigest()}"


def normalize_inline(text: str) -> str:
    value = html.unescape(text)
    value = re.sub(r"<br\s*/?>", "\n", value, flags=re.IGNORECASE)
    value = value.replace(r"\[", "[").replace(r"\]", "]")
    value = re.sub(r"\*\*|__", "", value)
    value = re.sub(r"(?<!\w)_(.+?)_(?!\w)", r"\1", value)
    value = re.sub(r"[ \t]+", " ", value)
    value = re.sub(r"\n[ \t]+", "\n", value)
    return value.strip()


def is_process_running_header(text: str) -> bool:
    value = text.casefold()
    return (
        "qt đón tiếp bệnh nhân và khám chữa bệnh ngoại trú tại khu tn1 - cs1" in value
        and "float:right" in value
        and "qt.25.01" in value
    )


def split_markdown_row(line: str) -> list[str]:
    value = line.strip()
    if value.startswith("|"):
        value = value[1:]
    if value.endswith("|") and not value.endswith(r"\|"):
        value = value[:-1]
    cells: list[str] = []
    current: list[str] = []
    escaped = False
    for char in value:
        if char == "|" and not escaped:
            cells.append(normalize_inline("".join(current)))
            current = []
        else:
            current.append(char)
        escaped = char == "\\" and not escaped
        if char != "\\":
            escaped = False
    cells.append(normalize_inline("".join(current)))
    return cells


def split_text(text: str, max_words: int, overlap_words: int = 20) -> list[str]:
    words = text.split()
    if len(words) <= max_words:
        return [text.strip()]
    pieces = []
    start = 0
    while start < len(words):
        end = min(len(words), start + max_words)
        pieces.append(" ".join(words[start:end]))
        if end == len(words):
            break
        start = max(start + 1, end - overlap_words)
    return pieces


def make_chunk(
    *,
    document_id: str,
    version_id: str,
    section_id: str,
    chunk_index: int,
    content_type: str,
    content_text: str,
    retrieval_prefix: str,
    heading_path: list[str],
    source_file: str,
    source_line_start: int,
    source_line_end: int,
    page_start: int | None = None,
    metadata: dict | None = None,
    identity: str = "",
) -> dict:
    retrieval_text = f"{retrieval_prefix}.\n{content_text}" if retrieval_prefix else content_text
    token_count = len(tokenize(retrieval_text))
    if token_count > 384:
        raise ValueError(f"Chunk vượt 384 token tại {source_file}:{source_line_start} ({token_count})")
    chunk_id = stable_id("chk", document_id, section_id, content_type, identity or content_text)
    return {
        "chunk_id": chunk_id,
        "document_id": document_id,
        "version_id": version_id,
        "section_id": section_id,
        "chunk_index": chunk_index,
        "content_type": content_type,
        "content_text": content_text,
        "retrieval_text": retrieval_text,
        "heading_path": heading_path,
        "previous_chunk_id": None,
        "next_chunk_id": None,
        "parent_chunk_id": None,
        "page_start": page_start,
        "page_end": page_start,
        "source_file": source_file,
        "source_line_start": source_line_start,
        "source_line_end": source_line_end,
        "token_count": token_count,
        "content_hash": f"sha256:{hashlib.sha256(content_text.encode('utf-8')).hexdigest()}",
        "authority_level": 2,
        "effective_from": None,
        "effective_to": None,
        "is_active": True,
        "metadata": metadata or {},
    }


def link_chunks(chunks: list[dict]) -> None:
    for index, chunk in enumerate(chunks):
        chunk["previous_chunk_id"] = chunks[index - 1]["chunk_id"] if index else None
        chunk["next_chunk_id"] = chunks[index + 1]["chunk_id"] if index + 1 < len(chunks) else None


def parse_process(path: Path) -> tuple[dict, list[dict], list[dict]]:
    document_id = "doc_qt_25_01"
    content_hash = sha256_file(path)
    version_id = stable_id("ver", document_id, "2024-12-05", content_hash)
    title = "Quy trình đón tiếp bệnh nhân và khám chữa bệnh ngoại trú tại Khu Tự nguyện 1 Cơ sở 1"
    document = {
        "document_id": document_id,
        "version_id": version_id,
        "title": title,
        "source_file": path.name,
        "source_uri": f"docs/data_rag/{path.name}",
        "document_type": "hospital_process",
        "language": "vi",
        "access_level": "public_reference",
        "status": "active",
        "effective_from": "2024-12-05",
        "effective_to": None,
        "content_hash": content_hash,
    }

    chunks: list[dict] = []
    sections: dict[str, dict] = {}
    headings: list[str] = []
    current_page: int | None = None
    buffer: list[tuple[int, str]] = []
    last_process_step = ""
    last_process_role = ""

    def section_for_path() -> str:
        label = " > ".join(headings) if headings else title
        section_id = stable_id("sec", document_id, label)
        sections.setdefault(section_id, {
            "section_id": section_id,
            "document_id": document_id,
            "version_id": version_id,
            "heading_path": list(headings),
            "title": headings[-1] if headings else title,
        })
        return section_id

    def emit(
        text: str,
        start_line: int,
        end_line: int,
        content_type: str,
        metadata: dict | None = None,
    ) -> None:
        value = normalize_inline(text)
        if not value or value == "---":
            return
        section_id = section_for_path()
        prefix = " > ".join([title, *headings])
        prefix_tokens = len(tokenize(prefix))
        max_words = max(80, 340 - prefix_tokens)
        for part_index, part in enumerate(split_text(value, max_words=max_words)):
            chunk = make_chunk(
                document_id=document_id,
                version_id=version_id,
                section_id=section_id,
                chunk_index=len(chunks),
                content_type=content_type,
                content_text=part,
                retrieval_prefix=prefix,
                heading_path=list(headings),
                source_file=path.name,
                source_line_start=start_line,
                source_line_end=end_line,
                page_start=current_page,
                metadata={"document_code": "QT.25.01", **(metadata or {})},
                identity=f"{start_line}:{end_line}:{part_index}:{part}",
            )
            chunk["effective_from"] = "2024-12-05"
            chunks.append(chunk)

    def flush() -> None:
        if not buffer:
            return
        emit("\n".join(value for _, value in buffer), buffer[0][0], buffer[-1][0], "paragraph")
        buffer.clear()

    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if is_process_running_header(raw_line):
            flush()
            continue
        page_match = PAGE_RE.search(raw_line)
        if page_match:
            flush()
            current_page = int(page_match.group(1))
            continue
        heading_match = re.match(r"^(#{1,6})\s+(.+?)\s*$", raw_line)
        if heading_match:
            flush()
            level = len(heading_match.group(1))
            heading = normalize_inline(heading_match.group(2))
            headings[:] = headings[: level - 1]
            headings.append(heading)
            section_for_path()
            continue
        if raw_line.lstrip().startswith("|"):
            flush()
            cells = split_markdown_row(raw_line)
            if not cells or all(not cell or set(cell) <= {"-", ":"} for cell in cells):
                continue
            if any(cell.casefold() in {"trách nhiệm", "các bước thực hiện", "mô tả / tài liệu liên quan"} for cell in cells):
                continue
            row_metadata = None
            in_process_flow = bool(headings and headings[-1].startswith("5.1."))
            if in_process_flow and len(cells) >= 3:
                role = cells[0].strip()
                step = cells[1].replace("↓", "").strip()
                detail = cells[2].strip()
                is_continuation = not step and role.casefold().startswith("tiếp:") and bool(last_process_step)
                if step:
                    last_process_step = step
                    last_process_role = role
                effective_step = step or (last_process_step if is_continuation else "")
                effective_role = role or (last_process_role if is_continuation else "")
                if effective_step:
                    row_metadata = {
                        "process_step": effective_step,
                        "process_role": effective_role,
                        "process_detail": detail,
                        "is_continuation": is_continuation,
                    }
            emit(
                " — ".join(cell for cell in cells if cell),
                line_number,
                line_number,
                "process_table_row",
                row_metadata,
            )
            continue
        if not raw_line.strip():
            flush()
        elif not raw_line.strip().startswith("<!--"):
            buffer.append((line_number, raw_line))
    flush()
    link_chunks(chunks)
    return document, list(sections.values()), chunks


def price_category(line: str, current: str) -> str:
    folded = normalize_inline(line).upper()
    if "KHÁM BỆNH VÀ NGÀY GIƯỜNG ĐIỀU TRỊ" in folded:
        return "Khám bệnh và ngày giường điều trị"
    if "DỊCH VỤ KỸ THUẬT VÀ XÉT NGHIỆM" in folded:
        return "Dịch vụ kỹ thuật và xét nghiệm"
    if "KHÁM SỨC KHỎE" in folded:
        return "Khám sức khỏe toàn diện, lái xe và định kỳ"
    if "VÔ CẢM GÂY TÊ" in folded:
        return "Dịch vụ kỹ thuật thực hiện bằng phương pháp vô cảm gây tê"
    return current


def parse_price_entries(path: Path) -> tuple[list[dict], dict]:
    entries: list[dict] = []
    current_category = "Bảng giá dịch vụ kỹ thuật"
    current_columns: list[str] = []
    orphan_continuations = 0
    malformed_numbered_rows = 0

    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not raw_line.lstrip().startswith("|"):
            current_category = price_category(raw_line, current_category)
            continue
        cells = split_markdown_row(raw_line)
        upper = [cell.upper().replace("*", "").strip() for cell in cells]
        if upper and upper[0] == "STT":
            current_columns = upper
            continue
        if not cells or all(not cell or set(cell) <= {"-", ":"} for cell in cells):
            continue
        first = cells[0].strip()
        if NUMBERED_ROW_RE.fullmatch(first):
            if len(cells) < 5:
                malformed_numbered_rows += 1
                continue
            has_code = len(current_columns) >= 6 or len(cells) >= 6
            padded = cells + [""] * (6 - len(cells))
            if has_code:
                stt, code, name, facility_1, facility_2, note = padded[:6]
            else:
                stt, name, facility_1, facility_2, note = padded[:5]
                code = ""
            entries.append({
                "category": current_category,
                "stt": stt,
                "service_code": code,
                "service_name": name,
                "facility_1_price": facility_1,
                "facility_2_price": facility_2,
                "note": note,
                "source_line_start": line_number,
                "source_line_end": line_number,
            })
            continue
        if not first and any(cells[1:]):
            if not entries:
                orphan_continuations += 1
                continue
            entry = entries[-1]
            padded = cells + [""] * (6 - len(cells))
            has_code = len(current_columns) >= 6 or len(cells) >= 6
            continuation = {
                "service_code": padded[1] if has_code else "",
                "service_name": padded[2] if has_code else padded[1],
                "facility_1_price": padded[3] if has_code else padded[2],
                "facility_2_price": padded[4] if has_code else padded[3],
                "note": padded[5] if has_code else padded[4],
            }
            for key, value in continuation.items():
                if value:
                    entry[key] = " ".join(part for part in (entry[key], value) if part).strip()
            entry["source_line_end"] = line_number
    return entries, {
        "orphan_continuations": orphan_continuations,
        "malformed_numbered_rows": malformed_numbered_rows,
    }


def parse_prices(path: Path) -> tuple[dict, list[dict], list[dict], dict]:
    document_id = "doc_gia_dvbv_tim_hn"
    content_hash = sha256_file(path)
    version_id = stable_id("ver", document_id, "45/2024/NQ-HĐND", content_hash)
    title = "Bảng giá dịch vụ kỹ thuật Bệnh viện Tim Hà Nội"
    document = {
        "document_id": document_id,
        "version_id": version_id,
        "title": title,
        "source_file": path.name,
        "source_uri": f"docs/data_rag/{path.name}",
        "document_type": "hospital_service_price_list",
        "language": "vi",
        "access_level": "public_reference",
        "status": "reference_only",
        "effective_from": None,
        "effective_to": None,
        "legal_basis": "Phụ lục số 06 Nghị quyết số 45/2024/NQ-HĐND Thành phố Hà Nội",
        "content_hash": content_hash,
    }
    entries, diagnostics = parse_price_entries(path)
    sections: dict[str, dict] = {}
    chunks: list[dict] = []
    occurrence: Counter[str] = Counter()

    for entry in entries:
        category = entry["category"]
        section_id = stable_id("sec", document_id, category)
        sections.setdefault(section_id, {
            "section_id": section_id,
            "document_id": document_id,
            "version_id": version_id,
            "heading_path": [title, category],
            "title": category,
        })
        code = entry["service_code"] or "Không có mã"
        facility_1 = entry["facility_1_price"] or "Không niêm yết"
        facility_2 = entry["facility_2_price"] or "Không niêm yết"
        base = (
            f"Dịch vụ: {entry['service_name']}\n"
            f"Mã tương đương: {code}\n"
            f"Giá Cơ sở 1: {facility_1} đồng\n"
            f"Giá Cơ sở 2: {facility_2} đồng"
        )
        note = entry["note"].strip()
        prefix = f"{title} > {category}. Giá chi phí viện phí dịch vụ y tế"
        base_tokens = len(tokenize(prefix)) + len(tokenize(base))
        note_parts = split_text(note, max_words=max(60, 350 - base_tokens), overlap_words=15) if note else [""]
        identity_base = "|".join((category, entry["stt"], code, entry["service_name"], facility_1, facility_2))
        occurrence[identity_base] += 1
        for part_index, note_part in enumerate(note_parts):
            content = base + (f"\nGhi chú: {note_part}" if note_part else "")
            identity = f"{identity_base}|{occurrence[identity_base]}|{part_index}"
            chunks.append(make_chunk(
                document_id=document_id,
                version_id=version_id,
                section_id=section_id,
                chunk_index=len(chunks),
                content_type="price_service",
                content_text=content,
                retrieval_prefix=prefix,
                heading_path=[title, category],
                source_file=path.name,
                source_line_start=entry["source_line_start"],
                source_line_end=entry["source_line_end"],
                metadata={
                    "stt": entry["stt"],
                    "service_code": entry["service_code"],
                    "service_name": entry["service_name"],
                    "facility_1_price": entry["facility_1_price"],
                    "facility_2_price": entry["facility_2_price"],
                    "note": entry["note"],
                    "category": category,
                    "legal_basis": document["legal_basis"],
                },
                identity=identity,
            ))
    link_chunks(chunks)
    diagnostics["parsed_entries"] = len(entries)
    diagnostics["continuation_rows_merged"] = sum(entry["source_line_end"] > entry["source_line_start"] for entry in entries)
    diagnostics["empty_service_names"] = sum(not entry["service_name"] for entry in entries)
    diagnostics["empty_both_prices"] = sum(not entry["facility_1_price"] and not entry["facility_2_price"] for entry in entries)
    return document, list(sections.values()), chunks, diagnostics


def format_vnd(value: object) -> str:
    if value is None or value == "":
        return ""
    try:
        return f"{int(value):,}".replace(",", ".")
    except (TypeError, ValueError):
        return str(value).strip()


def source_chunk_lines(path: Path) -> dict[str, int]:
    """Map source chunk identifiers to their physical JSON line for citations."""
    result: dict[str, int] = {}
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            match = BHYT_CHUNK_ID_RE.match(line)
            if match:
                result[match.group(1)] = line_number
    return result


def parse_bhyt_json(path: Path) -> tuple[dict, list[dict], list[dict], dict]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    source_chunks = raw.get("knowledge_chunks")
    if not isinstance(source_chunks, list):
        raise ValueError(f"knowledge_chunks không phải array tại {path}")

    document_id = "doc_bhyt_benh_vien_tim_hn"
    content_hash = sha256_file(path)
    dataset_id = str(raw.get("dataset_id") or path.stem)
    as_of = str(raw.get("as_of") or "")
    version_id = stable_id("ver", document_id, dataset_id, as_of, content_hash)
    title = str(raw.get("title") or "BHYT tại Bệnh viện Tim Hà Nội")
    document = {
        "document_id": document_id,
        "version_id": version_id,
        "title": title,
        "source_file": path.name,
        "source_uri": f"docs/data_rag/{path.name}",
        "document_type": "bhyt_policy_and_hanoi_technical_price_reference",
        "language": str(raw.get("language") or "vi"),
        "access_level": "public_reference",
        "status": "active",
        "effective_from": as_of or None,
        "effective_to": None,
        "dataset_id": dataset_id,
        "schema_version": raw.get("schema_version"),
        "content_hash": content_hash,
        "known_limitations": raw.get("known_limitations", []),
        "safety_and_answering_rules": raw.get("safety_and_answering_rules", []),
    }

    line_by_source_id = source_chunk_lines(path)
    sections: dict[str, dict] = {}
    chunks: list[dict] = []
    counts: Counter[str] = Counter()
    missing_line_count = 0
    inactive_count = 0

    type_labels = {
        "policy": "Chính sách và quyền lợi BHYT",
        "price": "Biểu giá kỹ thuật BHYT và dịch vụ tại Hà Nội",
        "update_alert": "Cảnh báo cập nhật văn bản",
    }
    content_types = {
        "policy": "bhyt_policy",
        "price": "bhyt_price_service",
        "update_alert": "bhyt_update_alert",
    }

    for source_index, item in enumerate(source_chunks):
        if not isinstance(item, dict):
            raise ValueError(f"knowledge_chunks[{source_index}] không phải object")
        source_chunk_id = str(item.get("chunk_id") or f"source_{source_index}")
        chunk_type = str(item.get("chunk_type") or "policy")
        topic = str(item.get("topic") or "khac")
        facts = item.get("facts") if isinstance(item.get("facts"), dict) else {}
        appendix_section = str(facts.get("appendix_section") or "")
        section_label = " / ".join(part for part in (type_labels.get(chunk_type, chunk_type), topic, appendix_section) if part)
        section_id = stable_id("sec", document_id, section_label)
        heading_path = [title, type_labels.get(chunk_type, chunk_type), topic]
        if appendix_section:
            heading_path.append(f"Phụ lục 06 mục {appendix_section}")
        sections.setdefault(section_id, {
            "section_id": section_id,
            "document_id": document_id,
            "version_id": version_id,
            "heading_path": heading_path,
            "title": section_label,
        })

        item_title = normalize_inline(str(item.get("title") or source_chunk_id))
        answer = normalize_inline(str(item.get("answer") or item.get("content_for_embedding") or ""))
        question_variants = [normalize_inline(str(value)) for value in item.get("question_variants", []) if str(value).strip()]
        keywords = [normalize_inline(str(value)) for value in item.get("keywords", []) if str(value).strip()]
        caveats = [normalize_inline(str(value)) for value in item.get("caveats", []) if str(value).strip()]

        content_lines = [item_title, answer]
        if chunk_type == "price":
            service_name = normalize_inline(str(
                facts.get("approved_price_name") or facts.get("tt23_service_name") or item_title
            ))
            code = normalize_inline(str(facts.get("equivalent_code") or ""))
            price = format_vnd(facts.get("price_vnd"))
            if service_name and service_name not in answer:
                content_lines.append(f"Dịch vụ: {service_name}")
            if code:
                content_lines.append(f"Mã tương đương: {code}")
            if price:
                content_lines.append(f"Mức giá tham chiếu tại Hà Nội: {price} đồng")
            if facts.get("coverage_category"):
                content_lines.append(f"Phân loại BHYT: {normalize_inline(str(facts['coverage_category']))}")
            if facts.get("price_note"):
                content_lines.append(f"Ghi chú giá: {normalize_inline(str(facts['price_note']))}")
            if not facts.get("hospital_current_availability_confirmed", False):
                content_lines.append(
                    "Chưa xác nhận kỹ thuật này hiện được Bệnh viện Tim Hà Nội cung cấp; cần kiểm tra phạm vi được phê duyệt và tình trạng thực tế."
                )
        elif caveats:
            content_lines.extend(f"Lưu ý: {value}" for value in caveats[:2])

        retrieval_parts = [item_title, *question_variants[:3], *keywords[:12]]
        retrieval_prefix = ". ".join(dict.fromkeys(part for part in retrieval_parts if part))
        content_text = "\n".join(dict.fromkeys(part for part in content_lines if part))
        # Source records are already atomic. Reduce optional retrieval aliases
        # before ever splitting a legal/policy statement across chunks.
        while len(tokenize(f"{retrieval_prefix}.\n{content_text}")) > 384 and retrieval_parts:
            retrieval_parts.pop()
            retrieval_prefix = ". ".join(dict.fromkeys(part for part in retrieval_parts if part))
        if len(tokenize(f"{retrieval_prefix}.\n{content_text}")) > 384:
            content_text = "\n".join(content_lines[:2])

        source_line = line_by_source_id.get(source_chunk_id)
        if source_line is None:
            missing_line_count += 1
            source_line = source_index + 1
        validity = item.get("validity") if isinstance(item.get("validity"), dict) else {}
        is_active = validity.get("status", "current") == "current"
        if not is_active:
            inactive_count += 1

        metadata = {
            **facts,
            "source_chunk_id": source_chunk_id,
            "title": item_title,
            "topic": topic,
            "question_variants": question_variants,
            "keywords": keywords,
            "answer": answer,
            "applicability": item.get("applicability", {}),
            "validity": validity,
            "legal_basis": item.get("legal_basis", []),
            "verification": item.get("verification", {}),
            "caveats": caveats,
        }
        if chunk_type == "price":
            metadata.update({
                "service_code": str(facts.get("equivalent_code") or ""),
                "service_name": str(facts.get("approved_price_name") or facts.get("tt23_service_name") or item_title),
                "price_vnd": facts.get("price_vnd"),
            })

        chunk = make_chunk(
            document_id=document_id,
            version_id=version_id,
            section_id=section_id,
            chunk_index=len(chunks),
            content_type=content_types.get(chunk_type, f"bhyt_{chunk_type}"),
            content_text=content_text,
            retrieval_prefix=retrieval_prefix,
            heading_path=heading_path,
            source_file=path.name,
            source_line_start=source_line,
            source_line_end=source_line,
            page_start=facts.get("source_pdf_page"),
            metadata=metadata,
            identity=source_chunk_id,
        )
        chunk["authority_level"] = 3 if (item.get("verification") or {}).get("status") == "verified_official" else 2
        chunk["effective_from"] = validity.get("valid_from")
        chunk["effective_to"] = validity.get("valid_to")
        chunk["is_active"] = is_active
        chunks.append(chunk)
        counts[chunk_type] += 1

    link_chunks(chunks)
    expected = (raw.get("statistics") or {}).get("knowledge_chunk_count")
    if expected is not None and int(expected) != len(chunks):
        raise ValueError(f"BHYT chunk count {len(chunks)} khác statistics {expected}")
    diagnostics = {
        "source_schema_version": raw.get("schema_version"),
        "source_dataset_id": dataset_id,
        "parsed_chunks": len(chunks),
        "chunks_by_source_type": dict(counts),
        "missing_source_line_count": missing_line_count,
        "inactive_chunk_count": inactive_count,
    }
    return document, list(sections.values()), chunks, diagnostics


def write_jsonl(path: Path, values: Iterable[dict]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for value in values:
            handle.write(json.dumps(value, ensure_ascii=False, sort_keys=True) + "\n")


def markdown_cell(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip().replace("|", r"\|")


def write_normalized_price_markdown(path: Path, entries: list[dict]) -> None:
    """Write exactly one physical Markdown row for every logical service."""
    with path.open("w", encoding="utf-8") as handle:
        handle.write("# Bảng giá dịch vụ kỹ thuật Bệnh viện Tim Hà Nội — bản chuẩn hoá\n\n")
        handle.write(
            "| Danh mục | STT | Mã tương đương | Dịch vụ kỹ thuật | Cơ sở 1 | Cơ sở 2 | Ghi chú | Dòng nguồn |\n"
        )
        handle.write("|---|---:|---|---|---:|---:|---|---:|\n")
        for entry in entries:
            values = [
                entry["category"], entry["stt"], entry["service_code"], entry["service_name"],
                entry["facility_1_price"], entry["facility_2_price"], entry["note"],
                (str(entry["source_line_start"]) if entry["source_line_start"] == entry["source_line_end"]
                 else f"{entry['source_line_start']}-{entry['source_line_end']}")
            ]
            handle.write("| " + " | ".join(markdown_cell(value) for value in values) + " |\n")


def build_index(source_dir: Path, output_dir: Path) -> dict:
    process_path = source_dir / "quy-trinh-don-tiep-benh-nhan.md"
    price_path = source_dir / "GiaDVBV_tim_HN.md"
    bhyt_path = source_dir / "bhyt_benh_vien_tim_ha_noi_rag.json"
    for required in (process_path, price_path, bhyt_path):
        if not required.is_file():
            raise FileNotFoundError(required)

    process_document, process_sections, process_chunks = parse_process(process_path)
    price_document, price_sections, price_chunks, price_diagnostics = parse_prices(price_path)
    bhyt_document, bhyt_sections, bhyt_chunks, bhyt_diagnostics = parse_bhyt_json(bhyt_path)
    normalized_price_entries, _ = parse_price_entries(price_path)
    documents = [process_document, price_document, bhyt_document]
    sections = process_sections + price_sections + bhyt_sections
    chunks = process_chunks + price_chunks + bhyt_chunks
    ids = [chunk["chunk_id"] for chunk in chunks]
    if len(ids) != len(set(ids)):
        raise ValueError("Chunk IDs không duy nhất")
    if max(chunk["token_count"] for chunk in chunks) > 384:
        raise ValueError("Có chunk vượt giới hạn 384 token")

    output_dir.mkdir(parents=True, exist_ok=True)
    write_jsonl(output_dir / "documents.jsonl", documents)
    write_jsonl(output_dir / "sections.jsonl", sections)
    write_jsonl(output_dir / "chunks.jsonl", chunks)
    write_normalized_price_markdown(output_dir / "normalized-price-list.md", normalized_price_entries)
    write_jsonl(output_dir / "citations.jsonl", ({
        "chunk_id": chunk["chunk_id"],
        "document_id": chunk["document_id"],
        "source_file": chunk["source_file"],
        "source_line_start": chunk["source_line_start"],
        "source_line_end": chunk["source_line_end"],
        "page_start": chunk["page_start"],
        "heading_path": chunk["heading_path"],
    } for chunk in chunks))
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_dir": str(source_dir),
        "document_count": len(documents),
        "section_count": len(sections),
        "chunk_count": len(chunks),
        "chunks_by_document": dict(Counter(chunk["document_id"] for chunk in chunks)),
        "chunks_by_type": dict(Counter(chunk["content_type"] for chunk in chunks)),
        "max_token_count": max(chunk["token_count"] for chunk in chunks),
        "duplicate_chunk_ids": len(ids) - len(set(ids)),
        "normalized_price_rows": len(normalized_price_entries),
        "price_diagnostics": price_diagnostics,
        "bhyt_diagnostics": bhyt_diagnostics,
        "source_hashes": {document["source_file"]: document["content_hash"] for document in documents},
    }
    (output_dir / "index_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Build canonical HeartCare multi-document RAG index")
    parser.add_argument("--source-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    report = build_index(args.source_dir, args.output_dir)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
