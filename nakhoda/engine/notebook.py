# Copyright (c) 2026, Nakhoda and contributors
# For license information, please see license.txt
"""Phase 7's kernel: one disposable, Docker-isolated Python process per
notebook session, spoken to over line-delimited JSON on stdin/stdout - the
same shape as a Jupyter kernel's wire protocol, simplified to what a single
`docker run -i` pipe needs.

Every container is started with:
`--network none`        - no egress. Not "restricted"; none.
`--read-only`            - the container's own root filesystem cannot be
                           written to; only the tmpfs below can.
`--tmpfs /tmp ... noexec` - the one writable path, and code placed there
                           cannot be executed from it.
`--cap-drop ALL`, `--security-opt no-new-privileges`, `--pids-limit`,
`--memory`, `--cpus` - standard container hardening, applied here rather
                           than left to a caller who might forget one.

No `-v` / `--mount` is ever passed. That is the load-bearing fact this
module exists to keep true: the container has no path back to the host
filesystem to bind-mount into, so there is no host file for a cell's
`pandas.read_csv` to reach - not a guarded one, none. `tests/test_notebook.py`
is the §2.3 probe (`12-build-plan.md` Phase 7's gate): it plants a canary
file on the host and asserts the kernel cannot read it.

If Docker is not installed or not running, `NotebookUnavailable` is raised
rather than falling back to in-process execution. Per invariant 1 in
`12-build-plan.md` §6 ("any Python, ever, runs out-of-process or not at
all") and the Phase 7 gate text ("if it succeeds, the kernel is not
out-of-process enough ... ship nothing"), there is no degraded mode here -
the feature is either genuinely sandboxed or it does not run.
"""

from __future__ import annotations

import json
import queue
import secrets
import shutil
import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

IMAGE = "nakhoda-notebook-kernel:latest"

#: `notebook.py` lives at `nakhoda/engine/notebook.py`; the module root two
#: levels up is the Docker build context (`docker/notebook_kernel/Dockerfile`
#: `COPY`s `engine/notebook_worker.py` relative to it - see that file's
#: header comment for why they have to agree).
_MODULE_ROOT = Path(__file__).resolve().parent.parent
_DOCKERFILE = _MODULE_ROOT / "docker" / "notebook_kernel" / "Dockerfile"

DEFAULT_CELL_TIMEOUT = 20.0
DEFAULT_MEMORY = "512m"
DEFAULT_CPUS = "1"
DEFAULT_PIDS_LIMIT = "64"


class NotebookError(Exception):
	"""Base for everything this module raises."""


class NotebookUnavailable(NotebookError):
	"""Docker is missing, not running, or the kernel image would not build.
	Callers must treat this as "notebooks are off" - see module docstring."""


class NotebookCellTimeout(NotebookError):
	"""A cell did not respond within the wall-clock budget. The kernel is
	killed, not interrupted: there is no safe way to interrupt code already
	running inside another process's `exec()`, and a kernel that ignored a
	timeout is not one this module is willing to keep talking to."""


@dataclass(frozen=True)
class CellResult:
	stdout: str
	stderr: str
	result: str | None
	error: str | None
	duration: float


def _docker_available() -> bool:
	if shutil.which("docker") is None:
		return False
	try:
		subprocess.run(["docker", "info"], capture_output=True, timeout=5, check=True)
	except (subprocess.SubprocessError, OSError):
		return False
	return True


def ensure_image_built() -> None:
	"""Build the kernel image if it is missing. Idempotent - a build whose
	layers already exist is a fast no-op, which is what lets every
	`NotebookKernel()` call this unconditionally rather than requiring a
	caller to have provisioned the image out of band."""
	if not _docker_available():
		raise NotebookUnavailable("docker is not installed, or the daemon is not running")
	exists = subprocess.run(["docker", "image", "inspect", IMAGE], capture_output=True).returncode == 0
	if exists:
		return
	built = subprocess.run(
		["docker", "build", "-f", str(_DOCKERFILE), "-t", IMAGE, str(_MODULE_ROOT)],
		capture_output=True,
		text=True,
	)
	if built.returncode != 0:
		raise NotebookUnavailable(f"kernel image build failed:\n{built.stderr[-2000:]}")


class NotebookKernel:
	"""One container, one kernel. Variables set in one `run_cell` call are
	visible to the next - state lives in the container process's memory for
	as long as the kernel is open, and nowhere else; closing it (or the
	process dying) drops it all. Use as a context manager so the container
	is always torn down:

	    with NotebookKernel() as kernel:
	        kernel.run_cell("x = 21")
	        kernel.run_cell("x * 2")  # result="42"
	"""

	def __init__(
		self,
		*,
		timeout: float = DEFAULT_CELL_TIMEOUT,
		memory: str = DEFAULT_MEMORY,
		cpus: str = DEFAULT_CPUS,
	) -> None:
		ensure_image_built()
		self._timeout = timeout
		self._name = f"nakhoda-notebook-{secrets.token_hex(8)}"
		self._proc = subprocess.Popen(
			[
				"docker",
				"run",
				"--rm",
				"-i",
				"--name",
				self._name,
				"--network",
				"none",
				"--memory",
				memory,
				"--cpus",
				cpus,
				"--pids-limit",
				DEFAULT_PIDS_LIMIT,
				"--read-only",
				"--tmpfs",
				"/tmp:rw,size=64m,noexec,nosuid",
				"--cap-drop",
				"ALL",
				"--security-opt",
				"no-new-privileges",
				IMAGE,
			],
			stdin=subprocess.PIPE,
			stdout=subprocess.PIPE,
			stderr=subprocess.PIPE,
			text=True,
			bufsize=1,
		)
		self._lines: queue.Queue[str | None] = queue.Queue()
		self._reader = threading.Thread(target=self._read_stdout, daemon=True)
		self._reader.start()
		self._closed = False

	def _read_stdout(self) -> None:
		assert self._proc.stdout is not None
		for line in self._proc.stdout:
			self._lines.put(line)
		self._lines.put(None)  # EOF sentinel: the container process exited

	def run_cell(self, code: str) -> CellResult:
		"""Run one cell. Raises `NotebookCellTimeout` (killing the
		container) if the kernel does not respond within the configured
		budget, and `NotebookError` if the kernel has already exited."""
		if self._closed or self._proc.poll() is not None:
			raise NotebookError("kernel process is not running")
		assert self._proc.stdin is not None
		started = time.monotonic()
		self._proc.stdin.write(json.dumps({"code": code}) + "\n")
		self._proc.stdin.flush()
		try:
			line = self._lines.get(timeout=self._timeout)
		except queue.Empty:
			self.close(force=True)
			raise NotebookCellTimeout(f"cell exceeded {self._timeout}s and was killed") from None
		if line is None:
			raise NotebookError("kernel exited before responding to this cell")
		payload: dict[str, Any] = json.loads(line)
		return CellResult(
			stdout=payload.get("stdout", ""),
			stderr=payload.get("stderr", ""),
			result=payload.get("result"),
			error=payload.get("error"),
			duration=time.monotonic() - started,
		)

	def close(self, *, force: bool = False) -> None:
		if self._closed:
			return
		self._closed = True
		if self._proc.poll() is None:
			if force:
				subprocess.run(["docker", "kill", self._name], capture_output=True)
			elif self._proc.stdin is not None:
				try:
					self._proc.stdin.close()
				except OSError:
					pass
			try:
				self._proc.wait(timeout=5)
			except subprocess.TimeoutExpired:
				subprocess.run(["docker", "kill", self._name], capture_output=True)
				self._proc.wait(timeout=5)
		self._reader.join(timeout=5)
		for pipe in (self._proc.stdin, self._proc.stdout, self._proc.stderr):
			if pipe is not None:
				try:
					pipe.close()
				except OSError:
					pass

	def __enter__(self) -> NotebookKernel:
		return self

	def __exit__(self, *exc_info: object) -> None:
		self.close()


__all__ = [
	"CellResult",
	"NotebookCellTimeout",
	"NotebookError",
	"NotebookKernel",
	"NotebookUnavailable",
	"ensure_image_built",
]
