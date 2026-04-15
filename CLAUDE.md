# lev-topog — GCP Refinement Tool

## What it does
Refines Ground Control Points (GCPs) from drone surveys. Maintains a 3D world state and propagates manual camera corrections via PnP solving.

## Run
```bash
.venv/bin/python main.py
# prompts: r=refinar (keep existing), c=recalcular (reprocess from CSV)
# then open http://localhost:5000
```

## Structure
| Path | Role |
|------|------|
| `main.py` | Orchestrator — CSV pipeline + Flask server launch |
| `config.py` | All constants: paths, GPS offsets, camera params, limits |
| `calc/server.py` | Flask server + `RefineState` (world state, PnP, save/load) |
| `calc/converter.py` | CSV → GCP list (topographic survey parsing) |
| `calc/find_points_in_photos.py` | Projects 3D GCPs onto drone images |
| `calc/camera.py` | Pinhole camera model |
| `calc/exif.py` | EXIF GPS/orientation extraction |
| `calc/visualize_points.py` | Generates output conference images |
| `static/` | Frontend (HTML5 Canvas) |
| `input/relatorio_levantamento.csv` | Raw survey input |
| `output/gcp_list_im.txt` | Main GCP file (loaded by server on refine) |
| `output/refine_state.json` | Persisted refinement state (JSON) |
| `output/world.json` | 3D world state (camera poses + GCP positions) |

## GCP File Format (`gcp_list_im.txt`)
```
EPSG:31982
<E> <N> <Z> <u> <v> <filename> <gcp_id>
```
- Line 1: projection string
- Lines 2+: space-separated; **filename may contain spaces** (e.g. `DJI_000 (744).JPG`)
- Parse with: `e,n,z,u,v = parts[:5]`, `gcp_id = parts[-1]`, `filename = ' '.join(parts[5:-1])`

## Engineering Mandates
1. **GCP coords (E, N, Z) are sacred** — from topographic survey, never modified
2. Only camera extrinsics and projected (u, v) pixel positions change
3. On 'V' (Accept): camera pose recalculated via PnP; GPS bias propagated to all unverified cameras
4. PnP uses `SOLVEPNP_SQPNP` + iterative guess for stability with 3+ points

## Key Config (`config.py`)
- `PHOTO_DIR = 'input/drone'` — drone photos
- `RADIUS_METERS = 150.0` — search radius for point projection
- `MAX_POINTS_PER_PHOTO = 10` — cap per image in gcp_list_im.txt
- `GPS_OFFSET_NORTH/EAST/Z` — systematic GPS correction (meters)

## Known Pitfalls
- Filenames with spaces (e.g. `DJI_000 (744).JPG`) break naive `split()` — always parse first 5 cols and last col, join middle for filename
- PnP fails with < 3 points — guarded in server
- `refine_state.json` persists between runs; delete it to force clean state on next refine
