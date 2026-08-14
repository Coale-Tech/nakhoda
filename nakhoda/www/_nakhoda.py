# Copyright (c) 2026, Nakhoda and contributors
# For license information, please see license.txt
"""Boot context for the Nakhoda SPA (`frontend/`, built into
`public/frontend` and copied to `_nakhoda.html`).

Mirrors the pattern the `jinjaBootData` Vite plugin expects: a `{% for key
in boot %}window["{{ key }}"] = {{ boot[key] | tojson }};{% endfor %}` block
in the built HTML (injected at build time, see `frontend/vite.config.js`),
fed by `context.boot` here. `csrf_token` is what `frappe-ui`'s `call()`
reads for `X-Frappe-CSRF-Token` on every POST - without this controller the
built page has no `boot` in its Jinja context and every whitelisted call
from the SPA is rejected with `CSRFTokenError`.
"""

import frappe

no_cache = 1


def get_context(context):
	csrf_token = frappe.sessions.get_csrf_token()
	frappe.db.commit()
	context.boot = {
		"csrf_token": csrf_token,
		"site_name": frappe.local.site,
	}
