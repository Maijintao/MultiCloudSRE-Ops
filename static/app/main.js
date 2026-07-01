import { on } from "./events.js";
import { boot, logout } from "./auth.js";
import { renderCurrentView, renderShell, renderSidebarLeaderboard } from "./shell.js";
import { renderOverview } from "./overview.js";
import { renderSubmissionTable } from "./submissions.js";

on("auth:unauthorized", () => logout(false));
on("auth:logout", () => logout());
on("shell:render", () => renderShell());
on("view:render", () => renderCurrentView());
on("overview:render", () => renderOverview());
on("submissions:table", () => renderSubmissionTable());
on("leaderboard:sidebar", () => renderSidebarLeaderboard());

function shouldRegisterStaticCache() {
  return "serviceWorker" in navigator
    && !["localhost", "127.0.0.1", "::1"].includes(window.location.hostname);
}

if (shouldRegisterStaticCache()) {
  window.addEventListener("load", () => {
    navigator.serviceWorker.register("/service-worker.js").catch(() => {
      // Static caching is an optimization; the app still works without it.
    });
  });
}

boot();
