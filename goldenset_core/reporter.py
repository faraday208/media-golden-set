"""
Sidecar JSON rapor — convention §4 uyumlu.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from .actions import ApplyResult
from .selector import SelectionResult, get_bucket

REPORT_TOOL = "media-golden-set"


def write_report(
    *,
    report_path: Path | str,
    source_root: Path | str,
    config: dict[str, Any],
    selection: SelectionResult,
    apply_result: ApplyResult,
) -> Path:
    payload = {
        "version": "1",
        "tool": REPORT_TOOL,
        "source_root": str(Path(source_root).resolve()),
        "timestamp": datetime.now().isoformat(),
        "config": config,
        "summary": {
            "selected": len(selection.selected),
            "copied": sum(1 for e in apply_result.entries if e.kind == "image"),
            "captions_copied": sum(1 for e in apply_result.entries if e.kind == "caption"),
            "errors": len(apply_result.errors),
            "average_score": round(selection.average_score, 4),
            "face_count": selection.face_count,
        },
        "buckets": {
            "available": selection.buckets_available,
            "goals": selection.goals,
            "selected": selection.selection_stats,
        },
        "actions": [
            {"src": e.src, "dst": e.dst, "kind": e.kind}
            for e in apply_result.entries
        ],
        "results": [
            {
                "filename": a.filename,
                "bucket": get_bucket(a.caption),
                "score": round(a.final_score, 4),
            }
            for a in selection.selected
        ],
        "errors": apply_result.errors,
    }
    rp = Path(report_path)
    rp.parent.mkdir(parents=True, exist_ok=True)
    with open(rp, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
    return rp
