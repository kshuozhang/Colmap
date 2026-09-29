# Installed reconstruction tools

- OpenMVS v2.4.0: downloaded directly from `https://github.com/cdcseacave/openMVS/releases/download/v2.4.0/OpenMVS_macOS_arm64.zip`.
- Downloaded archive SHA-256: `3d4c616c97031b1ab6e2eecb0ddd5614fb99513c0782a32c9350602faf38799b` (locally recorded fingerprint, not an independent signature).
- Extracted executables: `tools/openmvs/`.
- COLMAP: official `pycolmap==3.11.1` wheel from PyPI, `cp39-cp39-macosx_11_0_arm64`, installed into `.colmap-env` with NumPy 2.0.2.
- Licenses copied from the corresponding upstream version tags into `tools/licenses/`.

Both libraries were executed on this Apple M1 Pro / macOS 13 computer during integration testing. COLMAP's standalone desktop application is not required by Head Studio.
