"""
Center-crop a GeoTIFF to a fixed pixel size while preserving georeferencing.

The output is a valid GeoTIFF subset: same CRS, same pixel size (transform scale),
and an updated origin so each pixel still maps to the same ground coordinates
as in the source file.

Usage:
  python crop_geotiff_center.py "D:\\GIS datasets\\new dataset\\bahrain_sentinel_new.tif"

  python crop_geotiff_center.py input.tif -o out.tif --size 512

Requires: pip install rasterio
"""

from __future__ import annotations

import argparse
from pathlib import Path

import rasterio
from rasterio.windows import Window
from rasterio.windows import transform as window_transform


def center_window(width: int, height: int, win_w: int, win_h: int) -> Window:
    col_off = max(0, (width - win_w) // 2)
    row_off = max(0, (height - win_h) // 2)
    # Clamp if raster is smaller than window
    w = min(win_w, width - col_off)
    h = min(win_h, height - row_off)
    return Window(col_off, row_off, w, h)


def main() -> None:
    p = argparse.ArgumentParser(description="Center-crop GeoTIFF to NxN pixels, keep CRS/transform semantics.")
    p.add_argument("input", type=Path, help="Input GeoTIFF path")
    p.add_argument(
        "-o",
        "--output",
        type=Path,
        default=None,
        help="Output path (default: <input_stem>_512_center.tif next to input)",
    )
    p.add_argument("--size", type=int, default=512, help="Square window size in pixels (default: 512)")
    args = p.parse_args()

    inp = args.input.resolve()
    if not inp.is_file():
        raise SystemExit(f"Input not found: {inp}")

    out = args.output
    if out is None:
        out = inp.parent / f"{inp.stem}_{args.size}_center.tif"
    else:
        out = out.resolve()

    win_size = args.size
    with rasterio.open(inp) as src:
        w, h = src.width, src.height
        if w < win_size or h < win_size:
            raise SystemExit(
                f"Raster is {w}x{h} pixels; need at least {win_size}x{win_size} for a full square crop."
            )
        window = center_window(w, h, win_size, win_size)
        new_transform = window_transform(window, src.transform)

        profile = src.profile.copy()
        profile.update(
            height=int(window.height),
            width=int(window.width),
            transform=new_transform,
        )

        data = src.read(window=window)

        with rasterio.open(out, "w", **profile) as dst:
            dst.write(data)
            # Copy color interpretation / tags where helpful
            if src.colorinterp:
                try:
                    dst.colorinterp = src.colorinterp
                except (ValueError, rasterio.errors.RasterioIOError):
                    pass
            for i in range(1, src.count + 1):
                tags = src.tags(i)
                if tags:
                    dst.update_tags(i, **tags)
            root_tags = src.tags()
            if root_tags:
                dst.update_tags(**root_tags)

    print(f"Wrote {out}")
    print(f"  Window: col_off={window.col_off:.0f}, row_off={window.row_off:.0f}, {window.width}x{window.height}")
    with rasterio.open(out) as chk:
        print(f"  CRS: {chk.crs}")
        print(f"  Bounds (file CRS): {chk.bounds}")


if __name__ == "__main__":
    main()
