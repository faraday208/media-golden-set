# media-golden-set

> Quality + caption-aware cherry-pick — AI training için "golden set" seçici.
> quality_report'tan blur skoru, caption JSON'lardan bucket (close-up /
> upper-body / full-body) ve face-visible bilgisi okur, dengeli seçim yapar.

[![tests](https://github.com/faraday208/media-golden-set/actions/workflows/tests.yml/badge.svg)](https://github.com/faraday208/media-golden-set/actions/workflows/tests.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![uv](https://img.shields.io/badge/built%20with-uv-261230)](https://github.com/astral-sh/uv)

`media-dataset-prep` pipeline'ının **07. adımı** — son halka. Standalone kullanılabilir.

---

## English

**What it does.** Quality- and caption-aware cherry-picker that assembles a balanced "golden set" for AI training. It reads blur scores from the quality report and bucket / face-visible data from the caption JSONs, then selects a distribution-balanced subset.

**Install**

```bash
git clone https://github.com/faraday208/media-golden-set
cd media-golden-set
uv sync
```

**Basic usage**

```bash
uv run python run.py \
    -i ./dataset \
    -o ./golden-set \
    --report ./dataset/quality_report.json \
    --count 200 \
    --distribution close-up:30,upper-body:30,full-body:40
```

Step **07** of the [`media-dataset-prep`](https://github.com/faraday208/media-dataset-prep) pipeline; also works standalone. The detailed documentation below is in Turkish.

---

## 🎯 Ne yapıyor?

Görseller + caption JSON'lar + quality_report verildiğinde:

1. **Filter:** invalid asset'leri (quality_report.valid=false) ve karakter dışı olanları at
2. **Bucket:** caption'dan `camera.distance`/`framing`/`focus` okuyup grupla (close-up / upper-body / full-body / other)
3. **Score:** blur skoru ile sırala (yüksek skor = daha keskin = öncelikli)
4. **Distribute:** kullanıcı dağılımına göre seç (ör. `close-up:30,upper-body:30,full-body:40`)
5. **Face swap:** `--face-target N` verilirse, N adet `face.visible=true` garantilemek için low-score non-face asset'leri yüksek-score face asset'lerle değiştir
6. **Copy:** seçimi target klasöre kopyala (image + caption JSON birlikte)
7. **Report:** sidecar JSON yaz (undo için kopya kayıtları)

LoRA training için "best of dataset" alt küme oluşturur — tipik kullanım: 1500 asset → 200 adet golden set.

---

## 🚀 Kurulum

```bash
git clone https://github.com/faraday208/media-golden-set
cd media-golden-set
uv sync
```

`media-dataset-prep` workspace altında: `make install`

Bağımlılık yok — saf stdlib (Pillow/numpy gerektirmez).

---

## 🛠️ Kullanım — CLI

### Temel kullanım

```bash
uv run python run.py \
    -i ./dataset \
    -o ./golden-set \
    --report ./dataset/quality_report.json \
    --count 200 \
    --distribution close-up:30,upper-body:30,full-body:40
```

### Karakter filtresi + face target

```bash
uv run python run.py \
    -i ./dataset -o ./golden-set \
    --report ./dataset/quality_report.json \
    --count 100 \
    --distribution close-up:25,upper-body:35,full-body:40 \
    --character alpha \
    --face-target 60
```

### Dry run (kopya yapmadan plan göster)

```bash
uv run python run.py -i ./dataset -o ./golden-set \
    --report ./dataset/quality_report.json \
    --count 100 --distribution close-up:50,upper-body:50 \
    --dry-run
```

### Üzerine yaz (target dolu)

```bash
uv run python run.py ... --force
```

### Geri al (kopyalanan dosyaları sil)

```bash
uv run python run.py --undo ./golden-set/selection_report.json
```

---

## 📋 Operation modes — özet

| Mod | Komut | Etki | Undo |
|---|---|---|---|
| **Apply** (default) | `run.py -i .. -o .. ...` | Image + caption kopyala | ✓ |
| **Dry-run** | `--dry-run` | Sadece plan göster | – |
| **Force** | `--force` | Hedef dolu olsa bile yaz | ✓ |
| **Undo** | `--undo REPORT` | Kopyalanan dosyaları sil | – |

---

## 🚩 Tüm CLI flag'leri

| Flag | Tip | Default | Açıklama |
|---|---|---|---|
| `-i, --input` | str | – | Source dataset klasörü (zorunlu, `--undo` hariç) |
| `-o, --output` | str | – | Hedef golden-set klasörü (zorunlu) |
| `--report` | str | – | quality_report.json yolu (zorunlu) |
| `--count` | int | – | Toplam seçilecek asset sayısı (zorunlu) |
| `--distribution` | str | – | `close-up:30,upper-body:30,full-body:40` (zorunlu) |
| `--character` | str | – | Sadece bu karakteri seç (caption.character) |
| `--face-target` | int | 0 | Min N adet face.visible=true (swap ile) |
| `--force` | flag | False | Target dolu olsa bile yaz |
| `--dry-run` | flag | False | Kopya yapmadan plan göster |
| `--selection-report` | str | `<output>/selection_report.json` | Sidecar JSON yolu |
| `--undo` | str | – | Rapor JSON'undan kopyalanan dosyaları sil |

---

## 🔌 In-process (library) kullanım

```python
from goldenset_core import (
    select, parse_distribution, apply_selection,
    write_report, undo_from_report,
)

# 1. Seç (kopyalama yapmaz)
result = select(
    source="./dataset",
    report="./dataset/quality_report.json",
    count=100,
    distribution=parse_distribution("close-up:30,upper-body:30,full-body:40"),
    character="alpha",
    face_target=60,
)
print(f"Selected: {len(result.selected)}, avg_score: {result.average_score:.3f}")

# 2. Uygula (kopyala)
ar = apply_selection(result.selected, target_dir="./golden-set", force=True)

# 3. Rapor yaz
write_report(
    report_path="./golden-set/selection_report.json",
    source_root="./dataset",
    config={"count": 100},
    selection=result,
    apply_result=ar,
)
```

---

## 📄 Rapor formatı

```jsonc
{
  "version": "1",
  "tool": "media-golden-set",
  "source_root": "/abs/path/dataset",
  "timestamp": "2026-05-09T...",
  "config": {
    "count": 100,
    "distribution": {"close-up": 0.3, "upper-body": 0.3, "full-body": 0.4},
    "character": "alpha",
    "face_target": 60
  },
  "summary": {
    "selected": 100,
    "copied": 100,
    "captions_copied": 100,
    "errors": 0,
    "average_score": 0.8421,
    "face_count": 62
  },
  "buckets": {
    "available": {"close-up": 80, "upper-body": 75, "full-body": 90, "other": 5},
    "goals": {"close-up": 30, "upper-body": 30, "full-body": 40},
    "selected": {"close-up": 30, "upper-body": 30, "full-body": 40}
  },
  "actions": [
    {"src": "/abs/.../img1.png", "dst": "/abs/.../golden/img1.png", "kind": "image"},
    {"src": "/abs/.../img1.json", "dst": "/abs/.../golden/img1.json", "kind": "caption"}
  ],
  "results": [
    {"filename": "img1.png", "bucket": "close-up", "score": 0.95}
  ],
  "errors": []
}
```

`actions[]` `--undo` için kullanılır.

---

## 🧪 Test

```bash
uv sync --group dev
uv run pytest
```

35 test:
- `parse_distribution` — yüzde, oran, hatalı input
- `get_bucket` — close-up / upper-body / full-body / other / focus override / boş caption
- `_is_valid` + `_check_face` — bool + string varyasyonları
- `load_data` — rapor mapping + unreported skip
- `filter_assets` — invalid + character filter
- `score_assets` — blur skoru
- `select` — full pipeline (basic + distribution goals + face swap + character + empty)
- `apply_selection` — copy + dry-run + force
- `undo_from_report` — sil + tool mismatch
- `write_report` — convention §4 schema
- `run.py` — argparse + e2e dry-run + missing flags + undo invalid

---

## ⚠️ Limitations

- Caption şeması: `camera.distance`, `framing`, `camera.focus`, `face.visible`, `character` field'larını bekler — başka şemalar için `goldenset_core/selector.py:get_bucket` adapt gerekir
- Quality rapor şeması: `{results: [{filename, valid, blur: {score}}]}` veya filename-keyed dict
- `--undo` selective değil; raporda listelenen tüm `dst` dosyalarını siler
- Bucket inference deterministic ama caption JSON kalitesine bağımlı (Pass 4 = scene/camera tipik kaynak)
- `--character` strict eşleşme (case-insensitive); fuzzy matching yok
- Recursive scan opt-in (`--recursive` flag); default sadece source kökü
- Recursive mode'da target tree mirror edilir; flat mode'da `target/<filename>` (geriye uyumlu)

---

## 🏷️ Sürüm

**v1.0.1** — pipeline integrasyonu için cross-tool tutarlılık iyileştirmeleri:
- **Recursive scan** — `--recursive`/`--no-recursive` flag (default: False, geriye uyumlu). Pipeline 06 caption tree-aware sidecar pattern üretiyorsa, 07 artık alt klasörleri görebiliyor.
- **Tree-preserving copy** — `--recursive` aktifken `apply_selection` `relative_to(source_root)` ile target altında subdir hiyerarşisini mirror'lar; aynı isimli farklı subdir'lerdeki dosyalar collision'sız kopyalanır.
- **`--undo` çakışma guard'ı** — `--undo` ile `-i/-o/--report/--count/--distribution` birlikte verilirse `parser.error` (resize/watermark/caption ile UX tutarlı).
- +4 regression test (39 toplam): recursive scan, tree-preserve copy, flat fallback, undo conflict.

**v1.0.0** — clean release. `golden-set-generator` → `media-golden-set`. Convention §uyumlu refactor:
- Gradio `ui/app.py` (101 satır) silindi — review işi meta UI'da
- Tek script `src/universal_selector.py` (463 satır) → `goldenset_core/{selector,actions,reporter,__init__}.py` paketi
- `run.py` argparse wrapper (standart -i/-o + --report + --count + --distribution + --character + --face-target + --dry-run + --force + --undo)
- `apply_selection` ↔ `undo_from_report` action layer (kopyalama kayıtları + selective delete)
- Sidecar JSON convention §4 (version + tool + source_root + summary + buckets + actions + results)
- Bağımlılık `gradio>=4.0` kaldırıldı — saf stdlib
- 35 test (parse + bucket + filter + select + apply + undo + report + run.py CLI)

---

## 📜 Lisans

[MIT](LICENSE)
