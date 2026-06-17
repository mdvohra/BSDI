# BSDI (Braein AI GIS) — Models & Features Reference

Spreadsheet-style tables for planning, demos, and onboarding.  
**Weights are not in git** — paths below are where to place files locally.  
**Default API:** `http://localhost:8000` (unified backend via [`backend/main.py`](../backend/main.py)).

---

## 1. ML models inventory (installed in this workspace)

| Model file / ID | Family | Architecture | Task | API prefix | UI module | Artifact folder | Input | Default threshold | Notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `finetuned_modelnew1.pth` | UNet | Custom 3→1 UNet | Building / roof segmentation | `/unet` | Object Detection | `models/artifacts/unet/` | RGB GeoTIFF / image | 0.3 | Optional `.unet_meta.json` for ImageNet norm |
| `water_body.pth` | UNet | ResUNet-A | Water body segmentation | `/unet` | Object Detection | `models/artifacts/unet/` | RGB, 512² chips | 0.4 | Distinct from solar ResUNet path |
| `best_resunet_finetuned.pth` | UNet | ResUNet-A | Water body segmentation | `/unet` | Object Detection | `models/artifacts/unet/` | RGB, 512² chips | 0.4 | Same loader as `water_body.pth`; env `WATER_BODY_MODEL_NAMES` |
| `water_segmentation.pth` | UNet | smp.Unet (ResNet50, 4 ch) | Water segmentation | `/unet` | Object Detection | `models/artifacts/unet/` | 4-band, 224² | 0.3 | Notebook-aligned SMP model |
| `Building Detection.pth` | UNet / Mask R-CNN list | (legacy) | Building detection | `/unet` or `/maskrcnn` | Object Detection | `backend/models/` (legacy) | RGB GeoTIFF | 0.3 | Also scanned by Mask R-CNN `/models` |
| `Building Detection_temp.pth` | Mask R-CNN | Faster R-CNN–style | Instance detection | `/maskrcnn` | Object Detection | `backend/models/` | RGB GeoTIFF | 0.2 | Tiled inference + GeoJSON |
| `Tree Detection.pth` | Mask R-CNN | Instance detection | Tree crowns | `/maskrcnn` | Object Detection | `backend/models/` | RGB GeoTIFF | 0.2 | |
| `Edge Detection.pth` | Mask R-CNN | Instance detection | Edge features | `/maskrcnn` | Object Detection | `backend/models/` | RGB GeoTIFF | 0.2 | |
| `Swimming_Pool.pth` | Mask R-CNN | Instance detection | Swimming pools | `/maskrcnn` | Object Detection | `backend/models/` | RGB GeoTIFF | 0.2 | |
| `Oil Pad.pth` | Mask R-CNN | Instance detection | Oil pads | `/maskrcnn` | Object Detection | `backend/models/` | RGB GeoTIFF | 0.2 | |
| `resunet_a_checkpoint_epoch_200_old_solar.pth` | Solar panel | ResUNet-A + ASPP + attention | Solar panel footprints | `/maskrcnn` | Object Detection | `models/artifacts/solar_panel/` | RGB, 256² per tile | 0.5 | `_solar` in name → `task: solar_panel` |
| `solarpanel_new.pth` | Solar panel | ResUNet-A | Solar panel footprints | `/maskrcnn` | Object Detection | `models/artifacts/solar_panel/` | RGB GeoTIFF | 0.5 | |
| `deepak_solarpanels_new 1.pth` | Solar panel | ResUNet-A | Solar panel footprints | `/maskrcnn` | Object Detection | `models/artifacts/maskrcnn/` * | RGB GeoTIFF | 0.5 | *Listed from maskrcnn dir; weights must be under `solar_panel/` to load |
| `Oil_Pad_Detection` | Esri DLPK | Mask R-CNN (`.emd` + `.pth`) | Oil pad detection | `/maskrcnn` | Object Detection | `models/artifacts/esri/Oil_Pad_Detection/` | 224×224, Esri norm | 0.2 | Folder ID in dropdown, not `.pth` name |
| `oil_spill_seg_resnet_50_deeplab_v3+_80.pt` | Oil spill | DeepLabV3+ (ResNet50) | Oil spill segmentation | `/oil_spill` | Object Detection | `models/artifacts/oil_spill/` | GeoTIFF | 0.5 | Semantic mask overlay |
| GiD LULC (`model.safetensors`) | LULC | SigLIP / GiD classifier | Land cover classes | `/lulc` | LULC (optional UI) | `models/artifacts/lulc/` | GeoTIFF chips | N/A (class argmax) | HF fallback: `prithivMLmods/GiD-Land-Cover-Classification` |
| (SRGAN weights) | Super-resolution | SRGAN generator | Image upscale | `/srgan` | Super Resolution (optional UI) | `models/artifacts/srgan/` | Image / GeoTIFF | Scale factor 2–8 | Not present in workspace until you add `.pth` |
| (SAR flood weights) | UNet | Custom UNet | SAR flood segmentation | `/unet` | Object Detection | `models/artifacts/sar_flood/` or `SAR_Flood/` | SAR 2-band style | 0.5 | Not present until you add weights |

---

## 2. Supported model slots (add your own weights)

| Slot | Discovery | Filename rules | Loader module |
| --- | --- | --- | --- |
| Generic UNet | `GET /unet/models` scans `unet/`, `sar_flood/`, `backend/models/`, `SAR_Flood/` | Any `.pth` / `.pt` | [`backend/unetnew.py`](../backend/unetnew.py) |
| Water body | Same as UNet | `water_body.pth`, `best_resunet_finetuned.pth`, or `WATER_BODY_MODEL_NAMES` | ResUNet-A in `unetnew.py` |
| Water SMP | Same as UNet | Exact `water_segmentation.pth` | `segmentation_models_pytorch` |
| SAR flood | Same as UNet | Name contains `sar` + `flood` / `finetune` | [`backend/sar_flood.py`](../backend/sar_flood.py) |
| Mask R-CNN | `GET /maskrcnn/models` scans `maskrcnn/`, `backend/models/` | `.pth` / `.pt` (excludes SRGAN names) | [`backend/finalmain.py`](../backend/finalmain.py) |
| Solar ResUNet | Same list + `solar_panel/` folder | `*_solar*.pth`, `solarpanel*.pth`, or `SOLAR_PANEL_MODEL_NAMES` | [`backend/solar_panel_resunet.py`](../backend/solar_panel_resunet.py) |
| Esri export | `GET /maskrcnn/models` | Subfolder under `esri/` with matching `.emd` + `.pth` | [`backend/esri_dlpk_detection.py`](../backend/esri_dlpk_detection.py) |
| Oil spill | `GET /oil_spill/models` | `.pt` in `oil_spill/` | [`backend/oil_spill_api.py`](../backend/oil_spill_api.py) |
| LULC | Fixed bundle or env | `config.json` + `model.safetensors` | [`backend/lulc/server.py`](../backend/lulc/server.py) |
| SRGAN | `GET /srgan/super_resolution_model` | `.pth` in `srgan/` | [`backend/super_resolution.py`](../backend/super_resolution.py) |

**Override models root:** set `BRAEIN_MODELS_ROOT` (see [`backend/model_paths.py`](../backend/model_paths.py)).

---

## 3. Backend services & main endpoints

| Service | Mount path | Primary endpoints | Output |
| --- | --- | --- | --- |
| Unified API | `/` | `GET /`, `GET /api/ui-config`, `POST /Auth/login` | Meta, UI flags, mock JWT |
| UNet | `/unet` | `GET /models`, `POST /predict`, `POST /predict-stream`, `GET /runs`, `GET /runs/{id}/geojson`, postprocess | GeoJSON, masks, archives |
| Mask R-CNN + Solar + Esri | `/maskrcnn` | Same pattern + solar/Esri branches | GeoJSON polygons, `task: maskrcnn` or `solar_panel` |
| Oil spill | `/oil_spill` | `GET /models`, `POST /predict` | Segmentation PNG / GeoJSON |
| SRGAN | `/srgan` | `GET /super_resolution_model`, `POST /predict` | Upscaled raster |
| LULC | `/lulc` | Flask routes (classify, predict, exports) | Classified raster / stats |
| Analysis | `/api/analysis` | `GET /catalog`, `GET /prediction/{task}/{id}`, `POST /compare`, `POST /llm/chat` | Catalog, compare, LLM |
| LULC change | `/api/analysis/lulc-change` | Compare two LULC runs, transition matrix, hotspots | Change analytics |

---

## 4. Application features by UI module

| Module | Route | Visible when (`backend/.env`) | Key capabilities |
| --- | --- | --- | --- |
| Object Detection | `/app/sataliteimage` | Always (default product) | Model dropdown (UNet + Mask R-CNN + Oil spill + solar); upload GeoTIFF/image; ROI polygon; threshold slider; SSE tile/chip streaming; map overlay; export GeoJSON/SHP; saved predictions; optional LULC prediction ID attach; demo ortho sample |
| Super Resolution | `/app/superResolution` | `GEOAI_UI_SHOW_SUPER_RESOLUTION=true` | SRGAN model list; upscale factor; upload & download result |
| LULC | `/app/lulc` | `GEOAI_UI_SHOW_LULC=true` | Land-cover classification; saved runs; map/image views; large GeoTIFF streaming |
| Analysis | `/app/analysis` | `GEOAI_UI_SHOW_ANALYSIS=true` | Prediction catalog; compare runs; LLM Q&A on results; LULC change (matrix, hotspots, regions) |
| Config | `/app/config/` | `GEOAI_UI_SHOW_CONFIG_PAGE=true` | Admin-style GIS model presentation |
| Admin dashboard | `/app/admin/dashboard` | Role: admin | Admin home |
| User dashboard | `/app/userdashboard` | Role: user | User home |
| Auth | `/login`, `/signup` | Public | Login / signup / password reset |

---

## 5. Object Detection — model picker behavior

| User sees (example) | Routed backend | Stream on GeoTIFF? | Result type |
| --- | --- | --- | --- |
| `finetuned_modelnew1.pth` | `http://localhost:8000/unet` | Yes (`predict-stream`) | Segmentation → vectors |
| `resunet_a_checkpoint_epoch_200_old_solar.pth (Solar panel)` | `http://localhost:8000/maskrcnn` | Yes | Solar footprints (`solar_panel`) |
| `Tree Detection.pth` | `/maskrcnn` | Yes | Instance boxes/polygons |
| `Oil_Pad_Detection (Esri)` | `/maskrcnn` | Yes | Esri-style detections |
| `oil_spill_seg_resnet_50_deeplab_v3+_80.pt` | `/oil_spill` | No (batch `/predict`) | Semantic spill mask |

---

## 6. Feature flags & tuning (environment)

| Variable | Default | Affects |
| --- | --- | --- |
| `GEOAI_UI_SHOW_SUPER_RESOLUTION` | false | Super Resolution menu |
| `GEOAI_UI_SHOW_LULC` | false | LULC menu |
| `GEOAI_UI_SHOW_ANALYSIS` | false | Analysis menu |
| `GEOAI_UI_SHOW_LULC_FIELDS` | false | LULC ID field on detection upload |
| `GEOAI_UI_SHOW_DETECTION_THRESHOLD` | true | Threshold slider on detection |
| `GEOAI_DEFAULT_INFERENCE_THRESHOLD` | 0.3 | Threshold when slider hidden |
| `BRAEIN_MODELS_ROOT` | `<repo>/models` | All artifact paths |
| `SOLAR_PANEL_MODEL_NAMES` | (auto `_solar`) | Force solar routing by filename |
| `SOLAR_PANEL_BINARY_THRESHOLD` | 0.5 | Solar mask cutoff |
| `SOLAR_TILE_SIZE` / `SOLAR_TILE_OVERLAP` | 1024 / 128 | Solar GeoTIFF tiling |
| `TILE_SIZE` / `TILE_OVERLAP` | 1024 / 128 | Mask R-CNN tiling |
| `UNET_OVERLAP_FUSION` | max | Chip overlap fusion for UNet |
| `LULC_MODEL_PATH` | artifacts/lulc or HF | LULC weights location |

---

## 7. Analysis hub features (when enabled)

| Feature | API | Description |
| --- | --- | --- |
| Prediction catalog | `GET /api/analysis/catalog` | Lists archived UNet, Mask R-CNN, solar, LULC runs |
| Run detail | `GET /api/analysis/prediction/{task}/{pred_id}` | Metadata + derived GeoJSON stats |
| Compare two runs | `POST /api/analysis/compare` | Pairwise metrics (detection / LULC) |
| Delete all runs | `POST /api/analysis/predictions/delete-all` | Clears archives |
| AI chat | `POST /api/analysis/llm/chat` | GPT-style Q&A over prediction JSON |
| Grounded query | `POST /api/analysis/llm/query` | Structured follow-up |
| LULC change | `/api/analysis/lulc-change/*` | Transition matrix, hotspots, regional change |

---

## 8. Exports & saved runs

| Capability | UNet | Mask R-CNN / Solar | Oil spill | LULC |
| --- | --- | --- | --- | --- |
| GeoJSON download | Yes | Yes | Yes | Yes |
| Shapefile download | Yes | Yes | — | Varies |
| Saved run manifests | `GET /unet/runs` | `GET /maskrcnn/runs` | — | LULC predictions folder |
| Post-process lab | `POST /unet/postprocess/*` | `POST /maskrcnn/postprocess/*` | — | — |
| Re-threshold GeoJSON (UNet) | `GET /unet/runs/{id}/geojson?threshold=` | Filter by score on client | — | — |

---

## 9. Quick reference — where to put new weights

| You trained… | Copy to… | Appears in UI as… |
| --- | --- | --- |
| Building UNet | `models/artifacts/unet/*.pth` | Object Detection → UNet backend |
| Solar ResUNet-A | `models/artifacts/solar_panel/*_solar.pth` | Object Detection → Solar panel |
| Tree / object Mask R-CNN | `models/artifacts/maskrcnn/` or `backend/models/` | Object Detection → MaskRCNN |
| Esri export | `models/artifacts/esri/<ModelId>/` (.emd + .pth) | Object Detection → Esri |
| Oil spill DeepLab | `models/artifacts/oil_spill/*.pt` | Object Detection → Oil spill |
| Land cover GiD | `models/artifacts/lulc/` | LULC page |
| SRGAN | `models/artifacts/srgan/*.pth` | Super Resolution |

---

## Related docs

| File | Purpose |
| --- | --- |
| [`README.md`](../README.md) | Repo overview & weights policy |
| [`README_RUN.md`](../README_RUN.md) | How to start backend & frontend |
| [`models/**/WHAT_GOES_HERE.txt`](../models/artifacts/) | Per-folder weight instructions |
| [`docs/Braein_AI_GIS_feature_inventory.csv`](Braein_AI_GIS_feature_inventory.csv) | Feature list (CSV for Excel import) |

*Generated for BSDI workspace layout. Re-scan artifact folders after adding new checkpoints.*
