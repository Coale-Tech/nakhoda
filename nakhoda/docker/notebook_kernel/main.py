#!/usr/bin/env python3
"""Notebook kernel entrypoint. Runs *inside* the isolated container only -
never imported by the Frappe process. Reads one JSON object per line from
stdin (`{"code": "<python source>"}`), execs it against a namespace that
persists for the container's lifetime (one kernel = one notebook session's
worth of state), writes one JSON object per line to stdout.

See `nakhoda/engine/notebook.py` for the host-side driver that spawns this
as `docker run -i` and speaks this same line-delimited-JSON protocol over
the pipe, and `nakhoda/engine/notebook_worker.py` for the (host-testable,
Docker-free) exec logic this file just wires to stdio.
"""

import json
import sys

from notebook_worker import run_cell_in_namespace


def main() -> None:
	namespace: dict = {}
	for raw_line in sys.stdin:
		line = raw_line.strip()
		if not line:
			continue
		try:
			request = json.loads(line)
		except json.JSONDecodeError as exc:
			sys.stdout.write(
				json.dumps({"stdout": "", "stderr": "", "result": None, "error": f"bad request: {exc}"})
				+ "\n"
			)
			sys.stdout.flush()
			continue
		result = run_cell_in_namespace(request.get("code", ""), namespace)
		sys.stdout.write(json.dumps(result) + "\n")
		sys.stdout.flush()


if __name__ == "__main__":
	main()
