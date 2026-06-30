import { emit } from "./events.js";
import { state } from "./state.js";

  function captureSidebarScroll() {
    const sidebar = document.querySelector(".sidebar");
    if (sidebar) state.sidebarScrollTop = sidebar.scrollTop;
  }

  function routeTo(path) {
    if (!path.startsWith("/")) path = `/${path}`;
    captureSidebarScroll();
    const next = `#${path}`;
    if (window.location.hash === next) {
      state.route = parseRoute();
      emit("shell:render");
      return;
    }
    window.location.hash = next;
  }

function parseRoute() {
  const raw = window.location.hash.replace(/^#\/?/, "");
  const parts = raw.split("/").filter(Boolean).map(decodeURIComponent);
  if (!parts.length) return { name: "overview", params: {} };
  if (parts[0] === "overview") return { name: "overview", params: {} };
  if (parts[0] === "admin" && parts[1] === "cases" && parts[2] === "new") return { name: "adminCaseNew", params: {} };
  if (parts[0] === "admin" && parts[1] === "cases" && parts[2]) return { name: "adminCase", params: { id: parts[2] } };
  if (parts[0] === "test-sets" && parts[1] && parts[2] === "submit") return { name: "testSetSubmit", params: { id: parts[1] } };
  if (parts[0] === "test-sets") return { name: "testSets", params: {} };
  if (parts[0] === "cases" && parts[1]) return { name: "case", params: { id: parts[1] } };
  if (parts[0] === "cases") return { name: "cases", params: {} };
  if (parts[0] === "submit" && parts[1]) return { name: "submit", params: { id: parts[1] } };
  if (parts[0] === "submissions" && parts[1]) return { name: "submission", params: { id: Number(parts[1]) } };
  if (parts[0] === "submissions") return { name: "submissions", params: {} };
  if (parts[0] === "profile") return { name: "profile", params: {} };
  if (parts[0] === "admin") return { name: "admin", params: {} };
  return { name: "overview", params: {} };
}
export { captureSidebarScroll, routeTo, parseRoute };
