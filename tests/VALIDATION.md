# Validation on this Mac

Completed 2026-09-21 on Apple M1 Pro, 16 GB RAM, macOS 13.0.

- 12 unit / HTTP tests passed: HEIC decoding, EXIF orientation, resizing, original preservation, invalid input, minimum photo count, worker failure reporting, cancellation, OBJ opacity normalization, local origin/token checks, and upload/path handling.
- Actual end-to-end run through the app's HTTP interface: 48 synthetic photos at three camera heights, Draft preset, all 48 aligned, 2,469 sparse points, 249,676 dense points, 95,728 mesh vertices and 191,452 faces.
- Run time for this small synthetic scene: 132.9 seconds. This is not a prediction for full-resolution human photos.
- Export contains `head.obj`, `head.mtl`, a JPEG texture atlas, and README. ZIP integrity verified.
- Headless Chrome: file selection, visibly rendered model, rotation/reset controls, ZIP download, mobile layout without horizontal overflow, and no JavaScript exceptions.
- Desktop/mobile screenshots: `.test-data/app-desktop.png`, `.test-data/app-mobile.png`.
- Sample project: `projects/da19d838c3c256bc/`.

The test scene is a textured ellipsoid, not a human head. Human capture quality, hair, motion, background separation and watertightness remain unverified until real photos are supplied. Earlier diagnostic runs are preserved under `.test-data/`.
