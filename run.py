#!/usr/bin/env python3
"""
Media Golden Set — CLI wrapper

Quality + caption JSON'lardan cherry-pick golden set seçici.

Convention §uyumlu standart flag'ler:
  -i, --input   : Source dataset klasörü
  -o, --output  : Hedef golden-set klasörü
  --report      : quality_report.json yolu
  --count       : Toplam seçilecek dosya sayısı
  --distribution: 'close-up:30,upper-body:30,full-body:40'
  --character   : Sadece bu karakteri filtrele (caption.character)
  --face-target : Min N adet face-visible asset (swap ile)
  --force       : Hedef klasör doluysa üzerine yaz
  --dry-run     : Kopyalama yapmadan plan göster
  --selection-report: Sidecar JSON rapor yolu
  --undo PATH   : Rapor JSON'undan kopyalanan dosyaları geri al

Örnek:
  python run.py -i ./dataset -o ./golden-set \
      --report ./dataset/quality_report.json \
      --count 100 \
      --distribution close-up:30,upper-body:30,full-body:40 \
      --face-target 60
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from goldenset_core import (
    apply_selection,
    parse_distribution,
    select,
    undo_from_report,
    write_report,
)

DEFAULT_REPORT_NAME = "selection_report.json"


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Media Golden Set — quality+caption-aware cherry-pick",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("-i", "--input", help="Source dataset klasörü")
    p.add_argument("-o", "--output", help="Hedef golden-set klasörü")
    p.add_argument("--report", help="quality_report.json yolu")
    p.add_argument("--count", type=int, help="Toplam seçilecek dosya sayısı")
    p.add_argument("--distribution",
                   help="'close-up:30,upper-body:30,full-body:40' (oran veya yüzde)")
    p.add_argument("--character", help="Sadece bu karakteri seç (caption.character)")
    p.add_argument("--face-target", type=int, default=0,
                   help="Min N adet face.visible=true (swap ile)")
    p.add_argument("--force", action="store_true",
                   help="Hedef klasör doluysa üzerine yaz")
    p.add_argument("--dry-run", action="store_true",
                   help="Kopyalama yapmadan plan göster")
    p.add_argument("--selection-report",
                   help=f"Sidecar JSON rapor yolu (default: <output>/{DEFAULT_REPORT_NAME})")
    p.add_argument("--undo", help="Rapor JSON'undan kopyalanan dosyaları sil")
    return p


def _run_undo(report_path: Path) -> int:
    if not report_path.exists():
        print(f"Rapor bulunamadı: {report_path}", file=sys.stderr)
        return 1
    try:
        removed, skipped = undo_from_report(report_path)
    except ValueError as e:
        print(f"Hata: {e}", file=sys.stderr)
        return 1
    print(f"Removed: {removed}, Skipped: {skipped}")
    return 0


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()

    if args.undo:
        return _run_undo(Path(args.undo))

    # Required arg checks
    missing = [n for n, v in [
        ("--input", args.input), ("--output", args.output),
        ("--report", args.report), ("--count", args.count),
        ("--distribution", args.distribution),
    ] if not v]
    if missing:
        parser.error(f"Eksik flag'ler: {', '.join(missing)}")

    src = Path(args.input)
    out = Path(args.output)
    rep = Path(args.report)

    if not src.is_dir():
        print(f"Source dizin değil: {src}", file=sys.stderr)
        return 1
    if not rep.is_file():
        print(f"Quality rapor bulunamadı: {rep}", file=sys.stderr)
        return 1

    try:
        distribution = parse_distribution(args.distribution)
    except (ValueError, KeyError) as e:
        print(f"Distribution parse hatası: {e}", file=sys.stderr)
        return 1

    print(f"\n{'='*70}")
    print("Media Golden Set")
    print(f"{'='*70}")
    print(f"Source:       {src}")
    print(f"Output:       {out}")
    print(f"Report:       {rep}")
    print(f"Count:        {args.count}")
    print(f"Distribution: {distribution}")
    if args.character:
        print(f"Character:    {args.character}")
    if args.face_target:
        print(f"Face target:  {args.face_target}")
    print(f"Mode:         {'DRY RUN' if args.dry_run else 'apply'}")
    print(f"{'='*70}\n")

    selection = select(
        source=src,
        report=rep,
        count=args.count,
        distribution=distribution,
        character=args.character,
        face_target=args.face_target,
    )
    if not selection.selected:
        print("Seçim sonucu boş — filter sonrası asset kalmadı.", file=sys.stderr)
        return 1

    print(f"Seçilen:        {len(selection.selected)} / {args.count}")
    print(f"Avg score:      {selection.average_score:.4f}")
    print(f"Face count:     {selection.face_count}")
    print(f"Bucket dağılım: {selection.selection_stats}")

    try:
        apply_result = apply_selection(
            selection.selected,
            target_dir=out,
            force=args.force,
            dry_run=args.dry_run,
        )
    except FileExistsError as e:
        print(f"Hata: {e}", file=sys.stderr)
        return 1

    print(f"\nKopyalanan:  {sum(1 for e in apply_result.entries if e.kind == 'image')}")
    print(f"Caption:     {sum(1 for e in apply_result.entries if e.kind == 'caption')}")
    if apply_result.errors:
        print(f"Hata:        {len(apply_result.errors)}", file=sys.stderr)

    # Rapor
    report_out = Path(args.selection_report) if args.selection_report else out / DEFAULT_REPORT_NAME
    config = {
        "count": args.count,
        "distribution": distribution,
        "character": args.character,
        "face_target": args.face_target,
        "force": args.force,
        "dry_run": args.dry_run,
        "input": str(src.resolve()),
        "output": str(out.resolve()),
        "quality_report": str(rep.resolve()),
    }
    rp = write_report(
        report_path=report_out,
        source_root=src,
        config=config,
        selection=selection,
        apply_result=apply_result,
    )
    print(f"\nRapor: {rp}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
