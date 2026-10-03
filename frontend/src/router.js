import { reactive } from "vue";

// A tiny hash router: the app has just one extra page (a profile), and hash
// URLs need no server-side fallback from StaticFiles. "#/u/<username>" is a
// profile, anything else is the main screen (lobby / room / game).
export const route = reactive({ name: "home", username: null });

function parse() {
  const m = location.hash.match(/^#\/u\/([^/]+)$/);
  if (m) {
    route.name = "profile";
    route.username = decodeURIComponent(m[1]);
  } else {
    route.name = "home";
    route.username = null;
  }
}

window.addEventListener("hashchange", parse);
parse();

export function openProfile(username) {
  location.hash = `#/u/${encodeURIComponent(username)}`;
}

export function goHome() {
  if (route.name === "home") return;
  history.pushState(null, "", location.pathname + location.search);
  parse();
}
