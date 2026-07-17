from __future__ import annotations

from pathlib import Path
from typing import Any
import yaml


def load_config(path: str | Path) -> dict[str, Any]:
    source = Path(path)
    if not source.is_file():
        raise ValueError(f"Không tìm thấy config: {source}")
    config = yaml.safe_load(source.read_text(encoding="utf-8"))
    for key in ("seed", "reference_date", "counts", "output"):
        if key not in config:
            raise ValueError(f"Config thiếu trường bắt buộc: {key}")
    config["_config_dir"] = str(source.resolve().parent)
    return config

