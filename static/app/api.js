import { emit } from "./events.js";
import { state } from "./state.js";

async function api(path, options = {}) {
  const headers = { ...(options.headers || {}) };
  const hasContentType = Object.keys(headers).some((key) => key.toLowerCase() === "content-type");
  if (!hasContentType && !options.raw) headers["Content-Type"] = "application/json";
  if (state.token) headers.Authorization = `Bearer ${state.token}`;
  const response = await fetch(path, { ...options, headers });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    if (response.status === 401) emit("auth:unauthorized");
    throw new Error(data.error || `HTTP ${response.status}`);
  }
  return data;
}

function setToken(token) {
  state.token = token;
  if (token) localStorage.setItem("oj_token", token);
  else localStorage.removeItem("oj_token");
}

export { api, setToken };
