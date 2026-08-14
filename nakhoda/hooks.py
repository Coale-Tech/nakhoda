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
# Permissions evaluated in scripted ways

# permission_query_conditions = {
# 	"Event": "frappe.desk.doctype.event.event.get_permission_query_conditions",
# }
#
# has_permission = {
# 	"Event": "frappe.desk.doctype.event.event.has_permission",
# }

# DocType Class
# ---------------
# Override standard doctype classes

# override_doctype_class = {
# 	"ToDo": "custom_app.overrides.CustomToDo"
# }

# Document Events
# ---------------
# Hook on document methods and events

# doc_events = {
# 	"*": {
# 		"on_update": "method",
# 		"on_cancel": "method",
# 		"on_trash": "method"
# 	}
# }

# Scheduled Tasks
# ---------------

# scheduler_events = {
# 	"all": [
# 		"nakhoda.tasks.all"
# 	],
# 	"daily": [
# 		"nakhoda.tasks.daily"
# 	],
# 	"hourly": [
# 		"nakhoda.tasks.hourly"
# 	],
# 	"weekly": [
# 		"nakhoda.tasks.weekly"
# 	],
# 	"monthly": [
# 		"nakhoda.tasks.monthly"
# 	],
# }

# Migration
# ---------
# Push a newer shipped Intelligence Template version into every pristine
# (unedited) imported copy. A site-edited copy is left alone - see
# api/templates.py:sync_intelligence_template_updates and build-plan Phase 9.

after_migrate = "nakhoda.api.templates.sync_intelligence_template_updates"

# Fixtures
# --------
# The sidebar entry point: one `Workspace` record, `nakhoda/fixtures/workspace.json`.
# It only deep-links into `/nakhoda` (the SPA) plus a few admin shortcuts - the
# product's whole point is the single Ask surface, not a desk CRUD app; see
# docs/design/14-frontend-design.md - section 4.

fixtures = [
	{"doctype": "Workspace", "filters": [["name", "=", "Nakhoda"]]},
]

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
