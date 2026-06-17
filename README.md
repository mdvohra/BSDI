# BSDI

Braein satellite / geospatial detection and inference stack (backend APIs, LULC, frontend UI).

## Quick start

See [README_RUN.md](README_RUN.md) for local setup and running services.

## Model weights

Large checkpoints (`.pth`, `.pt`, `.safetensors`, GeoTIFF samples, etc.) are **not** in this repo. Place them under `models/artifacts/` and related paths as described in `models/**/WHAT_GOES_HERE.txt` files.

Solar panel ResUNet-A checkpoints (e.g. `resunet_a_checkpoint_epoch_200_old_solar.pth`) go in [`models/artifacts/solar_panel/`](models/artifacts/solar_panel/).
