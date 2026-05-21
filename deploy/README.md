# GeoAI Docker deployment

Stack: **backend** (FastAPI on `:8000` internally), **frontend** (nginx static on `:80` internally), **caddy** (published host ports **80**/**443**, TLS + routing).

## Prerequisites

- Docker Engine + Compose v2 (supports `env_file` with `required: false`).
- ML weights under `./models` on the host (see layout below). The compose file mounts `./models` → `/models` and sets **`BRAEIN_MODELS_ROOT=/models`**.
- Optional: copy [`backend/.env.example`](../backend/.env.example) to `backend/.env` for `GEOAI_UI_*` flags and other backend settings.

## Quick start

1. Copy [`.env.example`](../.env.example) to `.env` at the repository root. Set **`PUBLIC_DOMAIN`**. Leave **`VITE_API_BASE_URL`** unset unless the API is on a different host than the SPA — when unset, the built app uses **`window.location.origin`** so **`http://localhost`** vs **`https://localhost`** both work behind Caddy.

2. Ensure model artifacts exist under `./models` (see [`backend/model_paths.py`](../backend/model_paths.py)). Example layout:

   - `models/artifacts/unet/`
   - `models/artifacts/maskrcnn/`
   - `models/artifacts/srgan/`
   - `models/artifacts/oil_spill/`
   - `models/artifacts/lulc/` (optional local SigLIP bundle), or rely on Hugging Face download with cache volume **`hf_cache`**.

3. Build and run:

   ```bash
   docker compose build
   docker compose up -d
   ```

4. Open the site at **`http://localhost`** (default) or **`https://<PUBLIC_DOMAIN>`** when using a public DNS name.

### Changing the public URL or split API host

If **`VITE_API_BASE_URL`** is unset, the SPA resolves the API at **same origin** at runtime (no rebuild when switching between HTTP and HTTPS on localhost).

If you set **`VITE_API_BASE_URL`** explicitly (different API host), rebuild the frontend after `.env` changes:

```bash
docker compose build --no-cache frontend
docker compose up -d
```

## Volumes

| Mount | Purpose |
|-------|---------|
| `./models` → `/models` | Torch / HF weights (`BRAEIN_MODELS_ROOT`) |
| `./backend/uploads` | Upload scratch space |
| `./backend/outputs` | Generated outputs |
| `hf_cache` | Hugging Face / transformers cache |

Override the models root in compose if needed: set **`BRAEIN_MODELS_ROOT`** to another path and adjust the volume mapping.

## Caddy routing

[`deploy/Caddyfile`](Caddyfile) sends listed API prefixes to **`backend:8000`** and all other paths (including `/`) to **`frontend:80`**. If you add a new top-level route in [`backend/main.py`](../backend/main.py), extend the `@api path …` matcher in the Caddyfile.

## CPU vs GPU

The default [`backend/Dockerfile`](../backend/Dockerfile) uses **CPU** PyTorch wheels from PyPI. Inference uses CUDA only when the container has NVIDIA GPU devices **and** you install CUDA-enabled PyTorch (typically a **custom image** or compose override with `nvidia/cuda` base + matching `torch` index URL). Document any override in your own `docker-compose.override.yml` (not committed here).

## Troubleshooting

- **502 from Caddy on `/Auth` or `/api/*`**: Usually the backend container is not healthy. Run `docker compose logs backend`. If you see `ImportError: libGL.so.1` when importing `cv2`, rebuild the backend image (the Dockerfile installs `libgl1` for OpenCV on slim Debian).
- **First start is slow**: imports load all sub-apps; Hugging Face may download LULC weights into `hf_cache`.
- **Caddy / TLS**: For a real domain, point DNS to the host and ensure ports **80** and **443** reach Caddy. For **localhost**, Caddy serves HTTP without requiring certificates.
