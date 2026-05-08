"""Test fixture'ları — media-golden-set."""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def _png_bytes() -> bytes:
    """Minimal valid PNG (1x1)."""
    # 8-byte sig + IHDR + IDAT + IEND (önceden hazırlanmış)
    return bytes([
        0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a,
        0x00, 0x00, 0x00, 0x0d, 0x49, 0x48, 0x44, 0x52,
        0x00, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00, 0x01,
        0x08, 0x06, 0x00, 0x00, 0x00, 0x1f, 0x15, 0xc4,
        0x89, 0x00, 0x00, 0x00, 0x0d, 0x49, 0x44, 0x41,
        0x54, 0x78, 0x9c, 0x62, 0x00, 0x01, 0x00, 0x00,
        0x05, 0x00, 0x01, 0x0d, 0x0a, 0x2d, 0xb4, 0x00,
        0x00, 0x00, 0x00, 0x49, 0x45, 0x4e, 0x44, 0xae,
        0x42, 0x60, 0x82,
    ])


@pytest.fixture
def golden_dataset(tmp_path: Path) -> Path:
    """
    Sahte dataset:
    - 8 görsel (.png) + caption JSON'lar
    - quality_report.json (5 valid, 3 invalid)
    - Bucket dağılımı: 2 close-up, 3 upper-body, 3 full-body
    - Face: 4 visible, 4 not
    """
    img_data = _png_bytes()

    items = [
        # filename, valid, blur_score, distance, face_visible, character
        ("img01.png", True, 0.95, "close-up", True, "alpha"),
        ("img02.png", True, 0.90, "close-up", True, "alpha"),
        ("img03.png", True, 0.85, "upper body", False, "alpha"),
        ("img04.png", True, 0.80, "upper body", True, "alpha"),
        ("img05.png", True, 0.75, "upper body", False, "alpha"),
        ("img06.png", True, 0.70, "full body", True, "alpha"),
        ("img07.png", True, 0.65, "full body", False, "alpha"),
        ("img08.png", True, 0.60, "full body", False, "beta"),
        ("img09.png", False, 0.50, "close-up", False, "alpha"),  # invalid
        ("img10.png", False, 0.40, "upper body", False, "alpha"),  # invalid
    ]

    report_results = []
    for fname, valid, blur, dist, face, char in items:
        (tmp_path / fname).write_bytes(img_data)
        # Caption JSON
        cap = {
            "camera": {"distance": dist},
            "face": {"visible": "true" if face else "false"},
            "character": char,
        }
        (tmp_path / fname).with_suffix(".json").write_text(json.dumps(cap))
        report_results.append({
            "filename": fname,
            "valid": valid,
            "blur": {"score": blur},
        })

    quality_report = tmp_path / "quality_report.json"
    quality_report.write_text(json.dumps({"results": report_results}))
    return tmp_path
