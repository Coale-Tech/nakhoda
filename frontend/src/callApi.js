/**
 * A minimal `frappe.call`-style client, ported from `frappe-ui`'s own
 * `src/utils/call.js` (same wire protocol: `X-Frappe-CSRF-Token` from
 * `window.csrf_token`, POST to `/api/method/<method>`, unwrap `.message`,
 * throw a structured `Error` with `.messages` on failure) rather than
 * imported from the package. `frappe-ui`'s root export is one barrel that
 * pulls in its whole Vue component library - `Sidebar`, `TextEditor`,
 * etc. - which drags in `vue-router` and other dependencies this
 * single-page, router-less app was deliberately built without
 * (`package.json` has no `vue-router`; see `12-build-plan.md`'s dependency
 * table). `frappe-ui` itself stays a dependency for its Vite plugin only
 * (`vite.config.js`).
 */
export async function call(method, args = {}) {
	const headers = {
		Accept: "application/json",
		"Content-Type": "application/json; charset=utf-8",
		"X-Frappe-Site-Name": window.location.hostname,
	};
	if (window.csrf_token && window.csrf_token !== "{{ csrf_token }}") {
		headers["X-Frappe-CSRF-Token"] = window.csrf_token;
	}

	const path = method.startsWith("/") ? method : `/api/method/${method}`;
	const res = await fetch(path, { method: "POST", headers, body: JSON.stringify(args) });

	if (res.ok) {
		const data = await res.json();
		return data.message;
	}

	const text = await res.text();
	let body = {};
	try {
		body = JSON.parse(text);
	} catch {
		// non-JSON error body - fall through with an empty object
	}
	let messages = body._server_messages ? JSON.parse(body._server_messages) : [];
	messages = messages.concat(body.message).map((m) => {
		try {
			return JSON.parse(m).message;
		} catch {
			return m;
		}
	});
	messages = messages.filter(Boolean);
	if (!messages.length) messages = [body._error_message || body.exc_type || "Request failed"];

	const err = new Error(messages.join("\n"));
	err.messages = messages;
	err.status = res.status;
	throw err;
}
