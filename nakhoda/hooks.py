app_name = "nakhoda"
app_title = "Nakhoda"
app_publisher = "Nakhoda"
app_description = "AI-native analytics platform for Frappe and ERPNext"
app_email = "sajmustafa@hotmail.com"
app_license = "agpl-3.0"

# Intelligence Templates
# ----------------------
# Any installed app, including this one, may declare this hook to contribute
# domain dashboards. Each `{rel_path}/{folder}/` under the app carries a
# `manifest.json` + `template.json` (+ optional `preview.png`); discovery is
# live off `frappe.get_installed_apps()`, keyed `{app}/{folder}` - no migrate
# step, no registry doctype. See `api/templates.py` and build-plan Phase 9.

nakhoda_intelligence_templates = "intelligence_templates"

# Apps
# ------------------

# required_apps = []

# Each item in the list will be shown as an app in the apps page
add_to_apps_screen = [
	{
		"name": "nakhoda",
		"logo": "/assets/nakhoda/nakhoda-logo.png",
		"title": "Nakhoda",
		"route": "/nakhoda",
	}
]

# Website Route Rules
# --------------------
# `www/_nakhoda.html` is the underscore-prefixed convention (mirrors Insights'
# `_insights.html`); without this mapping frappe only serves it at literal
# `/_nakhoda`, not the public `/nakhoda` route the app-switcher tile and
# workspace shortcut link to.

website_route_rules = [
	{"from_route": "/nakhoda", "to_route": "_nakhoda"},
	{"from_route": "/nakhoda/<path:app_path>", "to_route": "_nakhoda"},
]

# Includes in <head>
# ------------------

# include js, css files in header of desk.html
# app_include_css = "/assets/nakhoda/css/nakhoda.css"
# app_include_js = "/assets/nakhoda/js/nakhoda.js"

# include js, css files in header of web template
# web_include_css = "/assets/nakhoda/css/nakhoda.css"
# web_include_js = "/assets/nakhoda/js/nakhoda.js"

# include custom scss in every website theme (without file extension ".scss")
# website_theme_scss = "nakhoda/public/scss/website"

# include js, css files in header of web form
# webform_include_js = {"doctype": "public/js/doctype.js"}
# webform_include_css = {"doctype": "public/css/doctype.css"}

# include js in page
# page_js = {"page" : "public/js/file.js"}

# include js in doctype views
# doctype_js = {"doctype" : "public/js/doctype.js"}
# doctype_list_js = {"doctype" : "public/js/doctype_list.js"}
# doctype_tree_js = {"doctype" : "public/js/doctype_tree.js"}
# doctype_calendar_js = {"doctype" : "public/js/doctype_calendar.js"}

# Svg Icons
# ------------------
# include app icons in desk
# app_include_icons = "nakhoda/public/icons.svg"

# Home Pages
# ----------

# application home page (will override Website Settings)
# home_page = "login"

# website user home page (by Role)
# role_home_page = {
# 	"Role": "home_page"
# }

# Generators
# ----------

# automatically create page for each record of this doctype
# website_generators = ["Web Page"]

# Jinja
# ----------

# add methods and filters to jinja environment
# jinja = {
# 	"methods": "nakhoda.utils.jinja_methods",
# 	"filters": "nakhoda.utils.jinja_filters"
# }

# Installation
# ------------

# before_install = "nakhoda.install.before_install"
# after_install = "nakhoda.install.after_install"

# Uninstallation
# ------------

# before_uninstall = "nakhoda.uninstall.before_uninstall"
# after_uninstall = "nakhoda.uninstall.after_uninstall"

# Integration Setup
# ------------------
# To set up dependencies/integrations with other apps
# Name of the app being installed is passed as an argument

# before_app_install = "nakhoda.utils.before_app_install"
# after_app_install = "nakhoda.utils.after_app_install"

# Integration Cleanup
# -------------------
# To clean up dependencies/integrations with other apps
# Name of the app being uninstalled is passed as an argument

# before_app_uninstall = "nakhoda.utils.before_app_uninstall"
# after_app_uninstall = "nakhoda.utils.after_app_uninstall"

# Desk Notifications
# ------------------
# See frappe.core.notifications.get_notification_config

# notification_config = "nakhoda.notifications.get_notification_config"

# Permissions
# -----------
# The workbook family is owner-private until shared, which DocType permissions
# cannot express on their own - `if_owner` would make a share unreachable. The
# roles carry table-wide read/write and `nakhoda/permissions.py` narrows it:
# yours if you own it, if it is shared with you, or if its workbook is.
#
# Both hooks are needed and answer different questions. `has_permission` guards
# one loaded document (every save, delete and `check_permission` call);
# `permission_query_conditions` filters list queries, without which a list page
# would show titles that refuse when clicked.

_WORKBOOK_FAMILY = (
	"Nakhoda Workbook",
	"Nakhoda Query",
	"Nakhoda Chart",
	"Nakhoda Dashboard",
	"Nakhoda Folder",
)

permission_query_conditions = {
	doctype: "nakhoda.permissions.get_permission_query_conditions" for doctype in _WORKBOOK_FAMILY
}

has_permission = {doctype: "nakhoda.permissions.has_doc_permission" for doctype in _WORKBOOK_FAMILY}

# DocType Class
# ---------------
# Override standard doctype classes

# override_doctype_class = {
# 	"ToDo": "custom_app.overrides.CustomToDo"
# }

# Document Events
# ---------------
# Nothing here. The curated semantic layer is cached and needs invalidating on
# every write, but both writable doctypes own that in their own `on_update` /
# `on_trash` (`nakhoda_semantic_model.py`, `nakhoda_metric.py`) - colocated with
# the field the cache is built from, rather than in a table an app-wide file
# keeps. One mechanism, not two: a `doc_events` entry beside those controllers
# would fire the same `curation.forget()` twice per save.

# Scheduled Tasks
# ---------------

# `agent/quota.py` opens a new window lazily on every read, so `reset_quota` is
# only a backstop for a site nobody asks a question on - not the mechanism.
# The two Data Store jobs are load-bearing: `sync_stored_tables` re-copies only
# tables an admin already imported (never widens the warehouse on a cron), and
# `expire_stale_imports` is what stops a killed worker leaving a table on
# "Syncing" forever, which would make its own duplicate guard refuse every
# retry (see `api/data_store.py`).
# `profile.refresh` scans which columns this site never fills. It is worth eight
# of the forty gold retrieval questions and costs 68s, which is why it is a
# nightly artifact rather than something `build_index` establishes per question
# (see `semantic/profile.py`).
scheduler_events = {
	"hourly": [
		"nakhoda.api.data_store.expire_stale_imports",
	],
	"daily": [
		"nakhoda.agent.quota.reset_quota",
		"nakhoda.api.data_store.sync_stored_tables",
		"nakhoda.semantic.profile.refresh",
	],
}

# Migration
# ---------
# Three jobs. Push a newer shipped Intelligence Template version into every
# pristine (unedited) imported copy - a site-edited copy is left alone, see
# api/templates.py:sync_intelligence_template_updates and build-plan Phase 9.
# Then rebuild the column profile, because a migration is exactly when columns
# appear and disappear, and because the design already promises the semantic
# model regenerates on `bench migrate`.
# `curation.sync` then upserts a semantic row per document this site actually
# uses, from that fresh profile. It runs last because it reads what the profile
# just wrote, and it never overwrites a hand-edited row - a curator's words
# survive every migration (see `semantic/curation.py`).

after_migrate = [
	"nakhoda.api.templates.sync_intelligence_template_updates",
	"nakhoda.semantic.profile.refresh",
	"nakhoda.semantic.curation.sync",
]

# Fixtures
# --------
# The sidebar entry point: one `Workspace` record, shipped as the standard
# on-disk module doc `nakhoda/nakhoda/workspace/nakhoda/nakhoda.json` (like
# every other app's workspaces - see `hrms/hr/workspace/*/`), not a fixture.
# frappe v16's `remove_orphan_entities` (`model/sync.py`) deletes any public
# Workspace record with no matching on-disk `**/workspace/**/*.json` on every
# migrate - a pure-fixture Workspace fails that check and gets deleted right
# after fixture sync recreates it. The module doc is picked up by the same
# `IMPORTABLE_DOCTYPES` sync as every other app's workspaces, on every
# frappe version, and satisfies the v16 check by construction.
#
# It only deep-links into `/nakhoda` (the SPA) plus a few admin shortcuts - the
# product's whole point is the single Ask surface, not a desk CRUD app; see
# docs/design/14-frontend-design.md - section 4.

# Testing
# -------

# before_tests = "nakhoda.install.before_tests"

# Overriding Methods
# ------------------------------
#
# override_whitelisted_methods = {
# 	"frappe.desk.doctype.event.event.get_events": "nakhoda.event.get_events"
# }
#
# each overriding function accepts a `data` argument;
# generated from the base implementation of the doctype dashboard,
# along with any modifications made in other Frappe apps
# override_doctype_dashboards = {
# 	"Task": "nakhoda.task.get_dashboard_data"
# }

# exempt linked doctypes from being automatically cancelled
#
# auto_cancel_exempted_doctypes = ["Auto Repeat"]

# Ignore links to specified DocTypes when deleting documents
# -----------------------------------------------------------

# ignore_links_on_delete = ["Communication", "ToDo"]

# Request Events
# ----------------
# before_request = ["nakhoda.utils.before_request"]
# after_request = ["nakhoda.utils.after_request"]

# Job Events
# ----------
# before_job = ["nakhoda.utils.before_job"]
# after_job = ["nakhoda.utils.after_job"]

# User Data Protection
# --------------------

# user_data_fields = [
# 	{
# 		"doctype": "{doctype_1}",
# 		"filter_by": "{filter_by}",
# 		"redact_fields": ["{field_1}", "{field_2}"],
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_2}",
# 		"filter_by": "{filter_by}",
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_3}",
# 		"strict": False,
# 	},
# 	{
# 		"doctype": "{doctype_4}"
# 	}
# ]

# Authentication and authorization
# --------------------------------

# auth_hooks = [
# 	"nakhoda.auth.validate"
# ]

# Automatically update python controller files with type annotations for this app.
# export_python_type_annotations = True

# default_log_clearing_doctypes = {
# 	"Logging DocType Name": 30  # days to retain logs
# }

# Translation
# ------------
# List of apps whose translatable strings should be excluded from this app's translations.
# ignore_translatable_strings_from = []
