# Phase 7's out-of-process kernel image (`docs/plan/12-build-plan.md`).
#
# Build context is the `nakhoda/` module root (see `engine/notebook.py`,
# which invokes `docker build -f docker/notebook_kernel/Dockerfile .` from
# there) - that is what lets this COPY reach `engine/notebook_worker.py`,
# the same file `tests/test_notebook.py` imports directly on the host.
#
# What is deliberately absent: no bind mount, no volume, nothing that gives
# the container a path back to the host filesystem - `engine/notebook.py`
# never passes `-v`. `--network=none`, `--read-only`, `--cap-drop=ALL` and a
# non-root user are applied at `docker run` time, not baked in here, so they
# stay visible in the one file that has to keep them all true together.
FROM python:3.12-slim

# Pinned to the same scientific stack `pyproject.toml` already commits the
# engine to (Phase 8's ML operations use the same three) - a notebook cell
# and a `forecast` operation see identical library versions. No plotting
# library: charts are a Phase 5 concern (chart renderers), not shipped here.
RUN pip install --no-cache-dir \
		pandas~=2.3.3 \
		numpy~=2.1 \
		scikit-learn~=1.7 \
		statsmodels~=0.14 \
		scipy~=1.16

RUN useradd --create-home --uid 1000 kernel
WORKDIR /app
COPY engine/notebook_worker.py docker/notebook_kernel/main.py /app/
USER kernel

ENTRYPOINT ["python3", "-u", "/app/main.py"]
