# Head Studio

A local photo-to-mesh app for Apple Silicon Macs. Import phone photos, reconstruct with COLMAP + OpenMVS, rotate the textured result, and download an OBJ bundle. No photos are sent to a cloud service. The browser connects only to a server on your own Mac.

## Open the app

Double-click **Start Head Studio.command**, then open <http://127.0.0.1:8765>. Keep the Terminal window open until processing finishes. Alternatively:

```sh
.venv/bin/python app.py
```

1. Choose 12–200 photos (80–150 recommended for a full head).
2. Use **Draft** for an initial check or **Balanced** for more detail.
3. Click **Create 3D model**. Keep the computer awake and plugged in.
4. Inspect the 360° preview, then download the ZIP. Keep the OBJ, MTL and image files together when opening them in Blender or MeshLab.

All originals, working files, logs and outputs are stored in `projects/<project-id>/`. The output folder is displayed in the app. A cancelled or failed project retains its files; create a fresh project to retry. Only one reconstruction runs at a time. The app does not automatically resume interrupted work.

## Capture

- Keep the person still, with a neutral expression; move the phone around them.
- Capture overlapping views at eye level, above and below. Include crown, ears, back and chin.
- Fill most of each photo with the head; avoid a busy background.
- Use the same lens, even lighting, sharp images, no portrait blur/beauty filters, no glasses.
- Hair, shiny surfaces, blinking and movement can cause missing or distorted geometry.

This is photogrammetry, not a learned head generator. It reconstructs visible, consistent surfaces and can include shoulders/background. It does not automatically isolate the head, invent unseen surfaces, recover individual hairs, guarantee 360° coverage, or produce a watertight 3D-printable model. Crop and repair in a mesh editor as needed. Scale/orientation are arbitrary. Successful alignment alone does not establish head accuracy.

## 16 GB defaults

| Preset | Imported image long edge | Dense long edge | Threads |
| --- | --- | --- | --- |
| Draft | 1600 px | 1000 px | 3 |
| Balanced | 2400 px | 1600 px | 4 |

CPU processing can take tens of minutes to hours depending on photos and scene complexity. These settings reduce memory use; they cannot guarantee a fixed RAM ceiling. Keep at least 10 GB free and close memory-heavy apps. Feature matching compares every photo pair, so large collections take longer.

Equal-size photos share camera intrinsics, assuming the same phone lens throughout capture. Color seam correction and sharpening are disabled because the tested OpenMVS binary produced severe color artifacts with these enabled. Even lighting/exposure is therefore especially helpful. Exported materials are normalized to opaque OBJ materials so they display correctly in standard viewers.

## Installed components

- [COLMAP / PyCOLMAP](https://github.com/colmap/colmap), PyCOLMAP 3.11.1 in `.colmap-env`, using the Python 3.9 Apple Silicon wheel compatible with macOS 13. No desktop COLMAP GUI is needed. BSD license.
- [OpenMVS](https://github.com/cdcseacave/openMVS), official v2.4.0 Apple Silicon release in `tools/openmvs`. AGPL-3.0 license.
- Pillow 12.3.0 and pillow-heif 1.7.0 in `.venv` (Python 3.14), for image decoding and EXIF orientation normalization.
- Three.js 0.170.0, vendored in `static/vendor` for offline viewing. MIT license included there.

The macOS 13 environment cannot use current Homebrew bottles for COLMAP; this app uses its Python library instead. The downloaded OpenMVS executables run directly on Apple Silicon without CUDA.

## Recreate the environment

On the same Mac configuration (Homebrew Python 3.14 plus `/usr/bin/python3` 3.9):

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
/usr/bin/python3 -m venv .colmap-env
.colmap-env/bin/python -m pip install pycolmap==3.11.1 numpy==2.0.2
```

Download `OpenMVS_macOS_arm64.zip` from the [v2.4.0 release](https://github.com/cdcseacave/openMVS/releases/tag/v2.4.0) and extract its executables directly into `tools/openmvs/`. Run `.venv/bin/python app.py --check` to check paths. If using a newer macOS/Xcode, use a separate Python 3.9 environment for `.colmap-env`, or deliberately update/test the worker API before changing the pinned COLMAP version.

## Troubleshooting

- **Too few photos align:** add overlap, ensure the person stayed still, avoid featureless/blurred photos. The app stops if fewer than 60% align and reports partial alignment otherwise.
- **No visible head / background reconstructed:** the head needs to fill most of the frame and remain still. Crop the output in a mesh editor; background segmentation is not included.
- **Server already running:** reuse the existing browser tab at port 8765; do not start a second copy.
- **Processing fails:** expand the processing log. Full logs are in the project directory.
- **Preview unavailable:** the model ZIP remains downloadable even if the browser does not support WebGL.

## Development checks

```sh
.venv/bin/python -m unittest discover -s tests -v
```

The synthetic smoke test described in `tests/README.md` validates tool integration, not reconstruction quality on a real human head.
