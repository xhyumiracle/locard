from __future__ import annotations

import json
from pathlib import Path
from typing import Any

try:
    import yaml
except ModuleNotFoundError:  # pragma: no cover
    yaml = None


class TeeOutput:
    def __init__(self, file_path: Path, original_stream):
        self.file = open(file_path, "w", encoding="utf-8")
        self.original_stream = original_stream

    def write(self, message: str):
        self.original_stream.write(message)
        self.file.write(message)
        self.file.flush()

    def flush(self):
        self.original_stream.flush()
        self.file.flush()

    def close(self):
        self.file.close()


def ensure_dir(path: Path):
    path.mkdir(parents=True, exist_ok=True)


def make_bench_id(query_id: str, query_idx: int | None = None) -> str:
    if query_idx is not None:
        return f"{query_idx:06d}_{query_id[:8]}"
    return query_id


def get_query_results_dir(results_dir: Path, query_id: str, query_idx: int | None) -> Path:
    path = results_dir / make_bench_id(query_id, query_idx)
    ensure_dir(path)
    return path


def extract_ground_truth(query_item: dict[str, Any]) -> str | None:
    gt = query_item.get("groundtruth")
    return gt.strip().upper() if isinstance(gt, str) and gt.strip() else None


def write_json(path: Path, data: Any):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def save_case_log(path: Path, lines: list[str]):
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def load_queries(yaml_path: Path) -> list[dict[str, Any]]:
    if yaml is not None:
        with open(yaml_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        queries = data.get("queries", [])
    else:
        queries = load_queries_without_pyyaml(yaml_path)

    for i, query_item in enumerate(queries):
        metadata = query_item.get("metadata", {})
        if "query_id" not in metadata:
            raise ValueError(f"Query at index {i} missing metadata.query_id")
    return queries


def load_queries_without_pyyaml(yaml_path: Path) -> list[dict[str, Any]]:
    queries: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    in_metadata = False
    pending_multiline_key: str | None = None

    def finalize():
        nonlocal current, in_metadata, pending_multiline_key
        if current is not None:
            if "metadata" not in current:
                current["metadata"] = {}
            queries.append(current)
        current = None
        in_metadata = False
        pending_multiline_key = None

    with open(yaml_path, "r", encoding="utf-8") as f:
        for raw_line in f:
            line = raw_line.rstrip("\n")
            stripped = line.strip()

            if not stripped or stripped.startswith("#") or stripped == "queries:":
                continue

            if line.startswith("- query:"):
                finalize()
                current = {"metadata": {}}
                current["query"] = line.split(":", 1)[1].strip()
                pending_multiline_key = "query"
                continue

            if current is None:
                continue

            if line.startswith("  groundtruth:"):
                current["groundtruth"] = line.split(":", 1)[1].strip()
                pending_multiline_key = None
                in_metadata = False
                continue

            if line.startswith("  metadata:"):
                in_metadata = True
                pending_multiline_key = None
                continue

            if in_metadata and line.startswith("    "):
                key, value = line.strip().split(":", 1)
                value = value.strip()
                if value.isdigit():
                    parsed: Any = int(value)
                else:
                    try:
                        parsed = float(value)
                        if parsed.is_integer():
                            parsed = int(parsed)
                    except ValueError:
                        parsed = value
                current["metadata"][key] = parsed
                continue

            if pending_multiline_key and line.startswith("    "):
                current[pending_multiline_key] += " " + stripped
                continue

            pending_multiline_key = None
            in_metadata = False

    finalize()
    return queries
