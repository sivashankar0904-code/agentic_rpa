"""Celery task modules, split by which worker image runs them.

rpa_tasks.py (nodriver/Chromium — the "rpa" queue) and training_tasks.py
(torch/numpy/pillow — the "training" queue) are kept in separate modules,
not just separate functions, so each worker's process only ever imports the
heavy dependency it actually needs: importing this package itself pulls in
neither submodule, letting each Celery worker command opt in via its own
--include flag (see docker/entrypoint.sh) instead of both workers loading
both dependency sets at startup.
"""
