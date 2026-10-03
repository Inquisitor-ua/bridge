import { createApp } from "vue";
import App from "./App.vue";
import "./style.css";
import { connect } from "./store.js";
import { loadMe } from "./auth.js";
import "./friends.js"; // keeps the friend lists and invites in sync from the start

connect();
loadMe();
createApp(App).mount("#app");
