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
from frappe.utils import get_fullname, get_system_timezone

from nakhoda.nakhoda.doctype.nakhoda_settings.nakhoda_settings import setting_enabled

no_cache = 1


def get_context(context):
	csrf_token = frappe.sessions.get_csrf_token()
	frappe.db.commit()
	context.boot = {
		"csrf_token": csrf_token,
		"site_name": frappe.local.site,
		# `jinjaBootData` assigns every top-level key here to a `window[key]`
		# global (`frappe-ui/vite/jinjaBootData.js`), one key per global - it
		# never creates a `boot` object on its own. The SPA's session payload
		# therefore has to travel under a key literally named `boot`, which is
		# what `frontend/src/stores/session.js` has always read and, until this
		# was wired, never found: `isLoggedIn` was unconditionally false.
		"boot": {
			"user": {
				"name": frappe.session.user,
				"full_name": get_fullname(frappe.session.user),
			},
			# Whether "Open in Desk" can lead anywhere. `user_type` is what
			# Frappe itself derives from `User.has_desk_access()` on every save
			# (`core/doctype/user/user.py:415`), so reading the stored column is
			# the same answer without recomputing a role join per page render.
			# A Website User following that link gets a 403, so the honest thing
			# is not to offer it.
			"has_desk_access": frappe.get_cached_value("User", str(frappe.session.user), "user_type")
			== "System User",
			# Who may import into the warehouse and write settings. Both roles
			# already hold write on `Nakhoda Settings` and `Nakhoda Data Source`
			# (see those doctypes' `permissions`), so the UI gates on the same
			# pair rather than inventing a third notion of "admin" that could
			# drift from what the endpoints actually enforce.
			"is_admin": bool({"Nakhoda Admin", "System Manager"} & set(frappe.get_roles())),
			# Whether the Data Store is switched on, so the sidebar can drop
			# that one nav entry exactly as Insights' `AppSidebar.vue:167`
			# does (`hidden: !settings.doc.enable_data_store`). It travels in
			# boot rather than being read client-side, which is where Insights
			# reads it, for two reasons:
			#
			# - `Nakhoda Settings` grants read to `System Manager` /
			#   `Nakhoda Admin` only, while `Insights Settings` grants it to
			#   `Insights User` too - a client-side GET would 403 for an
			#   ordinary `Nakhoda User` and the link would then hang on
			#   whatever the failure defaulted to.
			# - It costs nothing here and one request per boot there.
			#
			# `setting_enabled` rather than the raw field: this is the same
			# helper `api/data_store.py:data_store_enabled` gates imports
			# with, so a hidden link and a refused import can never disagree.
			# Imported from the doctype module, not `api.data_store`, because
			# that module pulls in `connectors` and therefore `ibis` - a heavy
			# import to pay on every page render.
			"data_store_enabled": setting_enabled("enable_data_store"),
			# Every timestamp Frappe hands the SPA is naive and written in
			# *this* zone, not the reader's (`utils/data.py:388`). Read as
			# browser-local - which is what `Date` does with
			# "2026-08-16 21:33:29" - a row synced minutes ago on a
			# `Asia/Kolkata` site rendered "in 2 hours" for a reader in
			# `Africa/Nairobi`. Sent once per boot so `timeAgo` can convert
			# instead of guessing; `get_system_settings` is cached, so this
			# costs no query.
			"time_zone": get_system_timezone(),
		},
	}
