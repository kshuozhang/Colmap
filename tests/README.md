Run unit and local HTTP tests using `.venv/bin/python -m unittest discover -s tests -v`.

The integration sample is an artificially textured ellipsoid with 48 camera views at three heights. Generate it with `.colmap-env/bin/python tests/synthetic_capture.py`, then import `.test-data/capture/*.png` in the app with Draft quality. It tests real COLMAP feature matching, camera recovery, undistortion, OpenMVS dense reconstruction, meshing, and OBJ/texture export. It is not a human head, and passing this test does not establish reconstruction quality for skin, hair, or moving subjects.
