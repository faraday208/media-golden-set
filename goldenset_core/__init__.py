"""media-golden-set — public API.

Quality + caption-aware cherry-pick için golden set seçici.

In-process kullanım:
    from goldenset_core import (
        select, parse_distribution, apply_selection,
        undo_from_report, write_report,
    )
"""
from .actions import ApplyResult, CopyEntry, apply_selection, undo_from_report
from .reporter import REPORT_TOOL, write_report
from .selector import (
    Asset,
    SelectionResult,
    filter_assets,
    get_bucket,
    load_data,
    parse_distribution,
    score_assets,
    select,
)

__all__ = [
    "Asset",
    "SelectionResult",
    "ApplyResult",
    "CopyEntry",
    "REPORT_TOOL",
    "select",
    "load_data",
    "filter_assets",
    "score_assets",
    "get_bucket",
    "parse_distribution",
    "apply_selection",
    "undo_from_report",
    "write_report",
]
