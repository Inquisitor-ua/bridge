import { createApp } from "vue";
import App from "./App.vue";
import "./style.css";
import { connect } from "./store.js";
import { loadMe } from "./auth.js";

connect();
loadMe();
createApp(App).mount("#app");
