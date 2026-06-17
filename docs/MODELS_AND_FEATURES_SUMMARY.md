# Braein AI GIS — Summary for stakeholders

One-page overview of what the platform does and which AI models it supports.

**Excel (one sheet — features + models):** [`Braein_AI_GIS_Overview.xlsx`](Braein_AI_GIS_Overview.xlsx)

---

## What the app does

| Area | What users get |
| --- | --- |
| **Object Detection** | Upload satellite/aerial imagery → AI finds buildings, trees, solar panels, oil features, water, etc. → results on a map → export for GIS |
| **Super Resolution** *(optional)* | Make imagery sharper before analysis |
| **Land Cover (LULC)** *(optional)* | Classify land type (urban, water, crops, forest, …) |
| **Analysis** *(optional)* | Review past runs, compare two results, ask questions in plain English |

**Typical workflow:** Open Object Detection → pick a model → upload image → adjust sensitivity → Predict → view on map → download GeoJSON/shapefile.

---

## AI models we can run (by use case)

| Use case | Example model names | What it finds |
| --- | --- | --- |
| **Buildings** | `finetuned_modelnew1.pth`, Building Detection | Building footprints / roofs |
| **Trees & objects** | Tree Detection, Swimming Pool, Edge Detection | Individual objects as polygons |
| **Solar panels** | `resunet_a_checkpoint_epoch_200_old_solar.pth` | Solar installation footprints |
| **Oil & gas** | Oil Pad, Oil_Pad_Detection (Esri) | Oil pad sites |
| **Oil spill** | `oil_spill_seg_resnet_50_deeplab_v3+_80.pt` | Spill areas on water |
| **Water** | `water_body.pth`, `best_resunet_finetuned.pth`, `water_segmentation.pth` | Water bodies / water extent |
| **Land cover** | GiD LULC bundle | Land-use classes over the scene |
| **Image quality** | SRGAN weights *(if installed)* | Higher-resolution imagery |

Models are **files on the server** (not baked into the app). New `.pth` files in the right folder show up in the dropdown after a backend restart.

---

## How models appear in the product

```text
User opens "Object Detection"
    → chooses model from dropdown
    → uploads GeoTIFF or image
    → clicks Predict
    → map shows outlines + optional export
```

Solar models are labeled **Solar panel** in the UI. Everything else is grouped by type (building, tree, oil, etc.).

---

## Technical footprint (light)

| Item | Detail |
| --- | --- |
| **App** | Web UI (React) + one backend API (port 8000) |
| **Model storage** | `models/artifacts/` on disk (large files kept out of git) |
| **Solar model location** | `models/artifacts/solar_panel/resunet_a_checkpoint_epoch_200_old_solar.pth` |
| **Optional modules** | Turned on/off via config (super-resolution, LULC, analysis) |

---

## What’s installed in our workspace today

| Ready to use | Notes |
| --- | --- |
| Building / water UNet models | In `models/artifacts/unet/` |
| Solar ResUNet (epoch 200 name) | In `models/artifacts/solar_panel/` |
| Tree, building, pool, oil pad (legacy) | In `backend/models/` |
| Oil spill segmentation | In `models/artifacts/oil_spill/` |
| Land cover (GiD) | In `models/artifacts/lulc/` |
| Esri oil pad export | In `models/artifacts/esri/` |
| Super-resolution | Folder ready; add weights when needed |

---

## Limits worth knowing

- Large GeoTIFFs are processed in **tiles** (may take minutes; progress bar shown).
- Results are **probabilistic** — users can tune a **threshold** (higher = fewer, more confident detections).
- Model quality depends on **training data**; swapping the weight file changes behavior without redeploying the whole app.

---

*For full technical tables (API paths, env vars, all filenames), see [`MODELS_AND_FEATURES.md`](MODELS_AND_FEATURES.md).*
