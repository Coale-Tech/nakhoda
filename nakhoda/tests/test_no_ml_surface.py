# Copyright (c) 2026, Nakhoda and contributors
# For license information, please see license.txt
"""Phase 8's design gate: no ML surface exists.

`docs/plan/12-build-plan.md` §Phase 8 states the subtraction as the gate
itself: "grep the frontend for an ML route, an ML nav item, an ML chart
component or an ML-specific origin badge, and find zero." A `forecast`
renders as an ordinary bar in an ordinary chart (`Chart.vue`'s `series[]`
shape) - if a reviewer can point at "the ML part of the UI", the 147
`api/ml` endpoints the fork exposed were moved, not deleted.

This is a tree-shape check, not a behaviour test: it runs on a bare
interpreter, no bench, no build - the same reason `clean_room.py` does.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

FRONTEND_SRC = Path(__file__).resolve().parent.parent.parent / "frontend" / "src"

#: A dedicated ML surface would name itself one of these ways. Matched
#: case-insensitively against file *names*, not content - `Chart.vue`
#: legitimately mentions "forecast" inside an ordinary series and must not
#: trip this.
ML_SURFACE_NAME = re.compile(
	r"(?:^|[^a-z])ml[_-]?(?:chart|dashboard|panel|view|route|page|badge)", re.IGNORECASE
)

#: A router entry or nav item naming an ML destination, e.g. `path: "/ml"` or
#: `to: "/forecast"` as a top-level surface rather than a query-builder step.
ML_ROUTE = re.compile(
	r"""['"]/(?:ml|forecast|anomal(?:y|ies)|segment(?:ation)?|score)(?:['"/])""", re.IGNORECASE
)


@unittest.skipUnless(FRONTEND_SRC.is_dir(), f"frontend source not found at {FRONTEND_SRC}")
class NoMLSurface(unittest.TestCase):
	def _files(self) -> list[Path]:
		return [
			p
			for p in FRONTEND_SRC.rglob("*")
			if p.suffix in (".vue", ".ts", ".js") and "node_modules" not in p.parts
		]

	def test_no_file_is_named_as_a_dedicated_ml_component(self):
		offenders = [
			str(p.relative_to(FRONTEND_SRC)) for p in self._files() if ML_SURFACE_NAME.search(p.stem)
		]
		self.assertEqual(
			offenders, [], "a dedicated ML component/route/badge file exists: " + ", ".join(offenders)
		)

	def test_no_router_or_nav_entry_names_an_ml_destination(self):
		offenders = []
		for path in self._files():
			text = path.read_text(encoding="utf-8", errors="ignore")
			if ML_ROUTE.search(text):
				offenders.append(str(path.relative_to(FRONTEND_SRC)))
		self.assertEqual(offenders, [], "an ML-specific route/nav entry exists in: " + ", ".join(offenders))

	def test_forecast_is_an_ordinary_series_flag_not_a_chart_variant(self):
		"""The one legitimate hit: `Chart.vue`'s `series[].forecast` boolean.

		Fails loudly if a second component starts referencing `forecast`,
		`detect_anomalies`, `segment` or `score` as a rendering concept - the
		one place ML syntax may appear in the render path is `Chart.vue`.
		"""
		ml_terms = re.compile(r"\b(forecast|detect_anomalies|is_anomaly|anomaly_score)\b")
		hits = {}
		for path in self._files():
			if path.name == "Chart.vue":
				continue
			text = path.read_text(encoding="utf-8", errors="ignore")
			found = set(ml_terms.findall(text))
			if found:
				hits[str(path.relative_to(FRONTEND_SRC))] = sorted(found)
		self.assertEqual(hits, {}, f"ML-specific rendering concepts leaked outside Chart.vue: {hits}")


if __name__ == "__main__":
	unittest.main()
