"""
Action layer — seçimleri hedef klasöre kopyala + undo desteği.

apply_selection: selection'daki asset'leri (image + caption JSON) target_dir'e kopyalar.
undo_from_report: rapordan kopyalanan dosyaları siler.
"""
from __future__ import annotations

import json
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

from .selector import Asset, SelectionResult


@dataclass
class CopyEntry:
    src: str
    dst: str
    kind: str  # "image" | "caption"


@dataclass
class ApplyResult:
    entries: list[CopyEntry] = field(default_factory=list)
    skipped: int = 0
    errors: list[str] = field(default_factory=list)


def apply_selection(
    selection: Iterable[Asset],
    *,
    target_dir: Path | str,
    force: bool = False,
    dry_run: bool = False,
) -> ApplyResult:
    """
    Seçimi target_dir'e kopyala. Caption JSON varsa onu da kopyala.

    - force=False ve target dolu ise FileExistsError
    - dry_run=True kopyalama yapmaz, sadece liste döndürür
    """
    target = Path(target_dir)
    if target.exists() and any(target.iterdir()) and not force and not dry_run:
        raise FileExistsError(f"Target {target} not empty. Use force=True to overwrite.")
    if not dry_run:
        target.mkdir(parents=True, exist_ok=True)

    result = ApplyResult()
    for asset in selection:
        src_img = asset.path
        dst_img = target / asset.filename
        if not dry_run:
            try:
                shutil.copy2(src_img, dst_img)
            except OSError as e:
                result.errors.append(f"{src_img}: {e}")
                continue
        result.entries.append(CopyEntry(
            src=str(src_img.resolve()),
            dst=str(dst_img.resolve()),
            kind="image",
        ))
        # Caption JSON varsa
        src_cap = src_img.with_suffix(".json")
        if src_cap.exists():
            dst_cap = target / src_cap.name
            if not dry_run:
                try:
                    shutil.copy2(src_cap, dst_cap)
                except OSError as e:
                    result.errors.append(f"{src_cap}: {e}")
                    continue
            result.entries.append(CopyEntry(
                src=str(src_cap.resolve()),
                dst=str(dst_cap.resolve()),
                kind="caption",
            ))
    return result


def undo_from_report(report_path: Path | str) -> tuple[int, int]:
    """Rapor JSON'undan kopyalanan dst dosyalarını sil. (removed, skipped) döndürür."""
    report_path = Path(report_path)
    with open(report_path, "r", encoding="utf-8") as f:
        report = json.load(f)
    if report.get("tool") != "media-golden-set":
        raise ValueError(f"Tool mismatch: {report.get('tool')!r}")

    removed = 0
    skipped = 0
    for entry in report.get("actions", []):
        dst = entry.get("dst")
        if not dst:
            skipped += 1
            continue
        p = Path(dst)
        if p.exists():
            try:
                p.unlink()
                removed += 1
            except OSError:
                skipped += 1
        else:
            skipped += 1
    return removed, skipped
