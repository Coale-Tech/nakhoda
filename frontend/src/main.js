import { createApp } from "vue";
import { FrappeUI } from "frappe-ui";
import { createPinia } from "pinia";
import router from "./router";
import App from "./App.vue";
import "./style.css";

const app = createApp(App);
// `router` first: frappe-ui's <Button> injects Symbol(router) and warns on every
// render without an instance. `FrappeUI` installs the app-level injections the
// components and `useCall` expect.
app.use(router);
// `Pinia` is the global state layer for the workbench (workbooks, dashboards,
// queries, session). It must be installed before any component reads a store.
app.use(createPinia());
// `socketio: false`: the plugin otherwise opens a socket.io connection to the
// bench's realtime port on boot and retries forever. Nothing in this app
// subscribes to realtime events, so the only thing it produced was a console
// error loop wherever that port isn't reachable.
app.use(FrappeUI, { socketio: false });
app.mount("#app");
