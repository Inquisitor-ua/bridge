import { reactive } from "vue";
import { reconnectSocket } from "./store.js";

export const auth = reactive({
  // { username, display_name, created_at } or null for a guest
  user: null,
  // false until the first /api/me answers, so the header doesn't flash "Войти"
  ready: false,
});

async function api(method, path, body) {
  const res = await fetch(`/api${path}`, {
    method,
    headers: body ? { "Content-Type": "application/json" } : undefined,
    body: body ? JSON.stringify(body) : undefined,
    credentials: "same-origin",
  });
  const data = await res.json().catch(() => null);
  if (!res.ok) {
    const err = new Error(typeof data?.detail === "string" ? data.detail : "ошибка сервера");
    err.status = res.status;
    throw err;
  }
  return data;
}

export async function loadMe() {
  try {
    auth.user = await api("GET", "/me");
  } catch {
    auth.user = null;
  } finally {
    auth.ready = true;
  }
}

export async function login(username, password) {
  auth.user = await api("POST", "/login", { username, password });
  reconnectSocket();
}

export async function register(username, password, displayName) {
  auth.user = await api("POST", "/register", { username, password, display_name: displayName });
  reconnectSocket();
}

export async function logout() {
  await api("POST", "/logout");
  auth.user = null;
  reconnectSocket();
}

export async function updateProfile(displayName) {
  auth.user = await api("PATCH", "/me", { display_name: displayName });
  return auth.user;
}

export function fetchUser(username) {
  return api("GET", `/users/${encodeURIComponent(username)}`);
}
