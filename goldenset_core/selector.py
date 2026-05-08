"""
Golden set selector — quality_report + caption JSON'lardan cherry-pick.

Akış:
1. Quality raporu yükle, source dir scan, caption JSON'larıyla eşle
2. Validity + character filter
3. Caption'dan bucket çıkart (close-up / upper-body / full-body / other)
4. Quality skoru ile sırala, distribution hedeflerine göre seç
5. Face-visible target için swap (gerekirse)
6. Hedef klasöre kopyala (action layer)
"""
from __future__ import annotations

import json
import shutil
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

VALID_EXTS = {".jpg", ".jpeg", ".png", ".webp"}


# ---------- Data structures ----------

@dataclass
class Asset:
    path: Path
    filename: str
    report: dict
    caption: dict
    final_score: float = 0.0


@dataclass
class SelectionResult:
    selected: list[Asset]
    buckets_available: dict[str, int]
    goals: dict[str, int]
    selection_stats: dict[str, int]
    average_score: float
    face_count: int


# ---------- Helpers ----------

def parse_distribution(dist_str: str) -> dict[str, float]:
    """Parse 'close-up:30,upper-body:30,full-body:40' → normalized dict."""
    dist: dict[str, float] = {}
    for part in dist_str.split(","):
        key, val = part.split(":")
        dist[key.strip()] = float(val)
    total = sum(dist.values())
    if total > 1.01:
        for k in dist:
            dist[k] /= total
    return dist


def _get_nested(data: dict, path: str):
    curr = data
    for k in path.split("."):
        if isinstance(curr, dict):
            curr = curr.get(k)
        else:
            return None
    return curr


def get_bucket(caption: dict) -> str:
    """Caption'dan bucket çıkar — close-up / upper-body / full-body / other."""
    dist = _get_nested(caption, "camera.distance")
    framing = _get_nested(caption, "framing")
    focus = _get_nested(caption, "camera.focus")

    val = (str(dist) if dist else (str(framing) if framing else "")).lower()
    focus_str = str(focus).lower() if focus else ""

    if "full body" in focus_str:
        return "full-body"
    if "close-up" in val or "closeup" in val or "head" in val:
        return "close-up"
    if "upper" in val or "mid" in val or "medium" in val:
        return "upper-body"
    if "full" in val or "long" in val or "wide" in val:
        return "full-body"
    return "other"


def _check_face(caption: dict) -> bool:
    fv = _get_nested(caption, "face.visible")
    return str(fv).lower() == "true" if fv is not None else False


def _is_valid(report_entry: dict) -> bool:
    v = report_entry.get("valid", False)
    if isinstance(v, str):
        return v.lower() == "true"
    return bool(v)


# ---------- Loading ----------

def load_data(source_dir: Path | str, report_path: Path | str) -> list[Asset]:
    """Quality raporu + source dir scan → Asset list."""
    source_dir = Path(source_dir)
    report_path = Path(report_path)

    with open(report_path, "r", encoding="utf-8") as f:
        report_data = json.load(f)

    if isinstance(report_data, dict) and "results" in report_data:
        report_data = report_data["results"]

    if isinstance(report_data, list):
        report_map = {item.get("filename"): item for item in report_data if item.get("filename")}
    else:
        report_map = report_data

    assets: list[Asset] = []
    for fp in source_dir.iterdir():
        if fp.suffix.lower() not in VALID_EXTS:
            continue
        entry = report_map.get(fp.name) or report_map.get(fp.stem)
        if not entry:
            continue
        caption: dict = {}
        cap_path = fp.with_suffix(".json")
        if cap_path.exists():
            try:
                with open(cap_path, "r", encoding="utf-8") as cf:
                    caption = json.load(cf)
            except json.JSONDecodeError:
                caption = {}
        assets.append(Asset(path=fp, filename=fp.name, report=entry, caption=caption))
    return assets


def filter_assets(assets: list[Asset], target_character: Optional[str] = None) -> list[Asset]:
    out: list[Asset] = []
    for a in assets:
        if not _is_valid(a.report):
            continue
        if target_character:
            char = a.caption.get("character")
            if not char:
                continue
            tgt = target_character.lower()
            if isinstance(char, list):
                if not any(c.lower() == tgt for c in char):
                    continue
            else:
                if str(char).lower() != tgt:
                    tags = [t.strip().lower() for t in str(char).split(",")]
                    if tgt not in tags:
                        continue
        out.append(a)
    return out


def score_assets(assets: list[Asset]) -> list[Asset]:
    """blur.score'u final_score olarak ayarla."""
    for a in assets:
        blur = a.report.get("blur", {})
        if isinstance(blur, (int, float)):
            a.final_score = float(blur)
        else:
            a.final_score = float(blur.get("score", 0.0))
    return assets


# ---------- Selection ----------

def select(
    *,
    source: Path | str,
    report: Path | str,
    count: int,
    distribution: dict[str, float],
    character: Optional[str] = None,
    face_target: int = 0,
) -> SelectionResult:
    """Asıl seçim mantığı — kopyalama yapmaz, sadece SelectionResult döndürür."""
    raw = load_data(source, report)
    filtered = filter_assets(raw, character)
    if not filtered:
        return SelectionResult([], {}, {}, {}, 0.0, 0)
    score_assets(filtered)

    buckets: dict[str, list[Asset]] = defaultdict(list)
    for a in filtered:
        buckets[get_bucket(a.caption)].append(a)
    for b in buckets:
        buckets[b].sort(key=lambda x: x.final_score, reverse=True)

    # Goal hesabı
    goals = {k: int(round(count * v)) for k, v in distribution.items()}
    diff = count - sum(goals.values())
    if diff != 0 and goals:
        target_key = max(goals, key=goals.get)
        goals[target_key] += diff

    # 1. pass: bucket goal'ları
    selection: list[Asset] = []
    pool: list[Asset] = []
    for b_name in distribution.keys():
        avail = buckets.get(b_name, [])
        goal = goals.get(b_name, 0)
        selection.extend(avail[:goal])
        pool.extend(avail[goal:])
    for b_name in buckets:
        if b_name not in distribution:
            pool.extend(buckets[b_name])
    pool.sort(key=lambda x: x.final_score, reverse=True)

    # Deficit fill
    needed = count - len(selection)
    if needed > 0:
        selection.extend(pool[:needed])
        pool = pool[needed:]

    # Face target swap
    if face_target > 0:
        current_faces = sum(1 for a in selection if _check_face(a.caption))
        deficit = face_target - current_faces
        if deficit > 0:
            face_pool = [a for a in pool if _check_face(a.caption)]
            face_pool.sort(key=lambda x: x.final_score, reverse=True)

            sel_by_bucket: dict[str, list[Asset]] = defaultdict(list)
            for a in selection:
                sel_by_bucket[get_bucket(a.caption)].append(a)

            # Phase 1: same-bucket swap
            for cand in face_pool[:]:
                if deficit <= 0:
                    break
                cand_b = get_bucket(cand.caption)
                opts = [a for a in sel_by_bucket[cand_b] if not _check_face(a.caption)]
                opts.sort(key=lambda x: x.final_score)
                if opts:
                    rm = opts[0]
                    selection.remove(rm)
                    sel_by_bucket[cand_b].remove(rm)
                    selection.append(cand)
                    sel_by_bucket[cand_b].append(cand)
                    face_pool.remove(cand)
                    pool.remove(cand)
                    deficit -= 1
            # Phase 2: cross-bucket
            if deficit > 0:
                removable = [a for a in selection if not _check_face(a.caption)]
                removable.sort(key=lambda x: x.final_score)
                for cand in face_pool:
                    if deficit <= 0 or not removable:
                        break
                    rm = removable.pop(0)
                    selection.remove(rm)
                    selection.append(cand)
                    deficit -= 1

    # Stats
    selection_stats: dict[str, int] = defaultdict(int)
    for a in selection:
        selection_stats[get_bucket(a.caption)] += 1
    avg_score = (sum(a.final_score for a in selection) / len(selection)) if selection else 0.0
    face_count = sum(1 for a in selection if _check_face(a.caption))
    buckets_available = {k: len(v) for k, v in buckets.items()}

    return SelectionResult(
        selected=selection,
        buckets_available=buckets_available,
        goals=goals,
        selection_stats=dict(selection_stats),
        average_score=avg_score,
        face_count=face_count,
    )
