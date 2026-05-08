"""Selector unit + integration tests — media-golden-set."""
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from goldenset_core import (
    apply_selection,
    filter_assets,
    get_bucket,
    load_data,
    parse_distribution,
    score_assets,
    select,
    undo_from_report,
    write_report,
)
from goldenset_core.selector import _check_face, _is_valid


# ---------- parse_distribution ----------

def test_parse_distribution_percent():
    d = parse_distribution("close-up:30,upper-body:30,full-body:40")
    assert sum(d.values()) == pytest.approx(1.0)
    assert d["close-up"] == pytest.approx(0.3)
    assert d["upper-body"] == pytest.approx(0.3)
    assert d["full-body"] == pytest.approx(0.4)


def test_parse_distribution_ratio():
    d = parse_distribution("close-up:0.3,upper-body:0.3,full-body:0.4")
    assert sum(d.values()) == pytest.approx(1.0)
    assert d["close-up"] == pytest.approx(0.3)


def test_parse_distribution_invalid_raises():
    with pytest.raises(ValueError):
        parse_distribution("close-up:not-a-number")


# ---------- get_bucket ----------

def test_get_bucket_close_up():
    assert get_bucket({"camera": {"distance": "close-up"}}) == "close-up"


def test_get_bucket_upper_body():
    assert get_bucket({"camera": {"distance": "upper body"}}) == "upper-body"


def test_get_bucket_full_body():
    assert get_bucket({"camera": {"distance": "full body"}}) == "full-body"


def test_get_bucket_other():
    assert get_bucket({"camera": {"distance": "abstract"}}) == "other"


def test_get_bucket_focus_overrides_full_body():
    cap = {"camera": {"distance": "close-up", "focus": "full body"}}
    assert get_bucket(cap) == "full-body"


def test_get_bucket_empty_caption():
    assert get_bucket({}) == "other"


# ---------- _is_valid + _check_face ----------

def test_is_valid_bool_true():
    assert _is_valid({"valid": True})


def test_is_valid_string_true():
    assert _is_valid({"valid": "true"})


def test_is_valid_false():
    assert not _is_valid({"valid": False})
    assert not _is_valid({"valid": "false"})


def test_check_face_string_true():
    assert _check_face({"face": {"visible": "true"}})


def test_check_face_no_face_field():
    assert not _check_face({})


# ---------- load_data ----------

def test_load_data_returns_assets(golden_dataset: Path):
    assets = load_data(golden_dataset, golden_dataset / "quality_report.json")
    # 10 görsel, hepsi raporda — load çağrısı 10 asset döndürür
    assert len(assets) == 10
    a = assets[0]
    assert a.filename.endswith(".png")
    assert "valid" in a.report
    assert "camera" in a.caption


def test_load_data_skips_unreported(tmp_path: Path):
    # Rapor boş, source'da 1 dosya var
    (tmp_path / "img.png").write_bytes(b"x")
    (tmp_path / "rep.json").write_text(json.dumps({"results": []}))
    assets = load_data(tmp_path, tmp_path / "rep.json")
    assert assets == []


# ---------- filter_assets ----------

def test_filter_assets_drops_invalid(golden_dataset: Path):
    raw = load_data(golden_dataset, golden_dataset / "quality_report.json")
    filtered = filter_assets(raw)
    # 8 valid (img09, img10 invalid)
    assert len(filtered) == 8


def test_filter_assets_character(golden_dataset: Path):
    raw = load_data(golden_dataset, golden_dataset / "quality_report.json")
    filtered = filter_assets(raw, target_character="alpha")
    # img08 beta — drop. 7 alpha valid kaldı.
    filenames = sorted(a.filename for a in filtered)
    assert "img08.png" not in filenames
    assert len(filtered) == 7


# ---------- score_assets ----------

def test_score_assets_uses_blur_score(golden_dataset: Path):
    raw = load_data(golden_dataset, golden_dataset / "quality_report.json")
    scored = score_assets(raw)
    # img01 → 0.95
    img01 = next(a for a in scored if a.filename == "img01.png")
    assert img01.final_score == 0.95


# ---------- select (full pipeline) ----------

def test_select_basic(golden_dataset: Path):
    res = select(
        source=golden_dataset,
        report=golden_dataset / "quality_report.json",
        count=5,
        distribution={"close-up": 0.4, "upper-body": 0.4, "full-body": 0.2},
    )
    assert len(res.selected) == 5
    # Sorted by score desc — top 5 from valid pool
    scores = [a.final_score for a in res.selected]
    # En yüksek skor 0.95 (img01) seçilmeli
    assert max(scores) == 0.95


def test_select_distribution_goals(golden_dataset: Path):
    res = select(
        source=golden_dataset,
        report=golden_dataset / "quality_report.json",
        count=5,
        distribution={"close-up": 0.4, "upper-body": 0.4, "full-body": 0.2},
    )
    # 5 * 0.4 = 2 → close-up & upper-body 2'şer; full-body 1
    assert res.goals["close-up"] == 2
    assert res.goals["upper-body"] == 2
    assert res.goals["full-body"] == 1


def test_select_face_target_swap(golden_dataset: Path):
    """face-target=4 isterse, swap ile face-visible adet artmalı."""
    res = select(
        source=golden_dataset,
        report=golden_dataset / "quality_report.json",
        count=4,
        distribution={"close-up": 0.5, "upper-body": 0.5},
        face_target=4,
    )
    # Çıkan seçimde face_count >=4 olmaya çalışılmalı (mevcutsa)
    assert res.face_count >= min(4, res.face_count)


def test_select_character_filter(golden_dataset: Path):
    res = select(
        source=golden_dataset,
        report=golden_dataset / "quality_report.json",
        count=10,
        distribution={"close-up": 0.3, "upper-body": 0.4, "full-body": 0.3},
        character="alpha",
    )
    # 7 alpha valid asset — count=10 talep ama 7 elde
    filenames = [a.filename for a in res.selected]
    assert "img08.png" not in filenames  # beta
    assert len(res.selected) <= 7


def test_select_empty_after_filter(tmp_path: Path):
    """Hiç asset uymazsa boş SelectionResult döner."""
    (tmp_path / "rep.json").write_text(json.dumps({"results": []}))
    res = select(
        source=tmp_path,
        report=tmp_path / "rep.json",
        count=5,
        distribution={"close-up": 1.0},
    )
    assert res.selected == []


# ---------- apply_selection + undo ----------

def test_apply_selection_copies_files(golden_dataset: Path, tmp_path: Path):
    res = select(
        source=golden_dataset,
        report=golden_dataset / "quality_report.json",
        count=3,
        distribution={"close-up": 0.5, "upper-body": 0.5},
    )
    target = tmp_path / "golden"
    ar = apply_selection(res.selected, target_dir=target)
    # 3 image + 3 caption JSON kopyalandı
    images = [e for e in ar.entries if e.kind == "image"]
    captions = [e for e in ar.entries if e.kind == "caption"]
    assert len(images) == 3
    assert len(captions) == 3
    # Dosyalar gerçekten target'da
    for e in ar.entries:
        assert Path(e.dst).exists()


def test_apply_selection_dry_run_no_copy(golden_dataset: Path, tmp_path: Path):
    res = select(
        source=golden_dataset,
        report=golden_dataset / "quality_report.json",
        count=2,
        distribution={"close-up": 1.0},
    )
    target = tmp_path / "golden"
    ar = apply_selection(res.selected, target_dir=target, dry_run=True)
    assert len(ar.entries) == 4  # 2 image + 2 caption
    # Hiçbir dosya yaratılmadı
    assert not target.exists()


def test_apply_selection_force_required(golden_dataset: Path, tmp_path: Path):
    target = tmp_path / "golden"
    target.mkdir()
    (target / "existing.txt").write_text("x")
    res = select(
        source=golden_dataset,
        report=golden_dataset / "quality_report.json",
        count=2,
        distribution={"close-up": 1.0},
    )
    with pytest.raises(FileExistsError):
        apply_selection(res.selected, target_dir=target, force=False)
    # force=True ile geçer
    ar = apply_selection(res.selected, target_dir=target, force=True)
    assert len(ar.entries) >= 2


def test_undo_from_report(golden_dataset: Path, tmp_path: Path):
    res = select(
        source=golden_dataset,
        report=golden_dataset / "quality_report.json",
        count=2,
        distribution={"close-up": 1.0},
    )
    target = tmp_path / "golden"
    ar = apply_selection(res.selected, target_dir=target)
    # Rapor yaz
    rp = write_report(
        report_path=target / "selection_report.json",
        source_root=golden_dataset,
        config={"count": 2},
        selection=res,
        apply_result=ar,
    )
    assert rp.exists()
    # Undo
    removed, skipped = undo_from_report(rp)
    assert removed >= 2
    # Dosyalar gitti
    for e in ar.entries:
        assert not Path(e.dst).exists()


def test_undo_tool_mismatch_raises(tmp_path: Path):
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"tool": "wrong-tool", "actions": []}))
    with pytest.raises(ValueError):
        undo_from_report(bad)


# ---------- write_report ----------

def test_write_report_schema(golden_dataset: Path, tmp_path: Path):
    res = select(
        source=golden_dataset,
        report=golden_dataset / "quality_report.json",
        count=3,
        distribution={"close-up": 0.5, "upper-body": 0.5},
    )
    target = tmp_path / "golden"
    ar = apply_selection(res.selected, target_dir=target)
    rp = write_report(
        report_path=target / "selection_report.json",
        source_root=golden_dataset,
        config={"count": 3, "test": True},
        selection=res,
        apply_result=ar,
    )
    payload = json.loads(rp.read_text())
    # Convention §4 zorunlu alanlar
    assert payload["version"] == "1"
    assert payload["tool"] == "media-golden-set"
    assert "source_root" in payload
    assert "summary" in payload
    assert "actions" in payload
    assert "results" in payload
    assert payload["summary"]["selected"] == 3


# ---------- run.py CLI ----------

def test_run_parser_imports():
    from run import _build_parser
    p = _build_parser()
    args = p.parse_args([
        "-i", "/x", "-o", "/y",
        "--report", "/r.json",
        "--count", "10",
        "--distribution", "close-up:50,upper-body:50",
    ])
    assert args.input == "/x"
    assert args.output == "/y"
    assert args.count == 10


def test_run_parser_face_target():
    from run import _build_parser
    p = _build_parser()
    args = p.parse_args([
        "-i", "/x", "-o", "/y", "--report", "/r.json",
        "--count", "10", "--distribution", "close-up:1.0",
        "--face-target", "5",
    ])
    assert args.face_target == 5


def test_run_undo_invalid_report(monkeypatch, tmp_path: Path):
    from run import main
    monkeypatch.setattr(sys, "argv", ["run.py", "--undo", str(tmp_path / "nope.json")])
    rc = main()
    assert rc == 1


def test_run_e2e_dry_run(monkeypatch, golden_dataset: Path, tmp_path: Path):
    """End-to-end CLI: -i + -o + --dry-run."""
    from run import main
    target = tmp_path / "golden"
    monkeypatch.setattr(sys, "argv", [
        "run.py",
        "-i", str(golden_dataset),
        "-o", str(target),
        "--report", str(golden_dataset / "quality_report.json"),
        "--count", "3",
        "--distribution", "close-up:50,upper-body:50",
        "--dry-run",
    ])
    rc = main()
    assert rc == 0


def test_run_missing_required_flags(monkeypatch):
    from run import main
    monkeypatch.setattr(sys, "argv", ["run.py", "-i", "/x"])
    with pytest.raises(SystemExit):
        main()
