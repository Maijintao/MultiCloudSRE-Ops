import { renderAdmin, renderAdminCaseCreator, renderAdminCaseEditor } from "./admin.js";
import { renderCaseDetail, renderCasesList, renderSubmit, renderTestSets, renderTestSetSubmit } from "./cases.js";
import { emit } from "./events.js";
import { renderOverview } from "./overview.js";
import { renderProfile } from "./profile.js";
import { parseRoute, routeTo, captureSidebarScroll } from "./router.js";
import { app, state } from "./state.js";
import { closeDetailStream, renderSubmissionDetail, renderSubmissions } from "./submissions.js";
import { compactTime, escapeHtml } from "./utils.js";

  function navButton(label, routeName, path) {
    const active = state.route.name === routeName || (
      routeName === "submissions" && state.route.name === "submission"
    ) || (
      routeName === "cases" && ["case", "submit"].includes(state.route.name)
    ) || (
      routeName === "testSets" && ["testSets", "testSetSubmit"].includes(state.route.name)
    ) || (
      routeName === "admin" && ["admin", "adminCase", "adminCaseNew"].includes(state.route.name)
    );
    return `<button class="nav-button ${active ? "active" : ""}" data-route="${escapeHtml(path)}">${escapeHtml(label)}</button>`;
  }

  function sidebarStats() {
    const cases = Array.isArray(state.cases) ? state.cases : [];
    return {
      total: cases.length,
      enabled: cases.filter((item) => item?.submission_enabled !== false).length,
      visible: cases.filter((item) => item?.ai_analysis_visible !== false).length,
    };
  }

  function renderLeaderboardSection() {
    const rows = Array.isArray(state.leaderboard) ? state.leaderboard : [];
    const leaderboardCaseCount = Math.max(0, Number(state.leaderboardCaseCount) || 0);
    const currentUserId = Number(state.user?.id || 0);
    if (!state.leaderboardLoadedAt) {
      return `
        <div class="sidebar-group sidebar-board">
          <div class="sidebar-label">排行榜</div>
          <p class="leaderboard-empty">排行榜正在后台刷新，不会阻塞页面加载。</p>
        </div>
      `;
    }
    if (!leaderboardCaseCount) {
      return `
        <div class="sidebar-group sidebar-board">
          <div class="sidebar-label">排行榜</div>
          <p class="leaderboard-empty">当前没有可计分题目，排行榜暂不显示。</p>
        </div>
      `;
    }
    return `
      <div class="sidebar-group sidebar-board">
        <div class="sidebar-board-head">
          <div>
            <div class="sidebar-label">排行榜</div>
            <p class="sidebar-board-note">按当前测试集整组提交的最高总分求和</p>
          </div>
          <span class="sidebar-board-count">${escapeHtml(leaderboardCaseCount)} 题</span>
        </div>
        ${rows.length ? `
          <div class="leaderboard-list">
            ${rows.map((item) => `
              <div class="leaderboard-row ${Number(item.user_id) === currentUserId ? "is-self" : ""}">
                <div class="leaderboard-rank">#${escapeHtml(item.rank)}</div>
                <div class="leaderboard-main">
                  <strong>${escapeHtml(item.username)}</strong>
                  <span>${escapeHtml(item.scored_cases)} 题 · ${escapeHtml(compactTime(item.latest_score_at || ""))}</span>
                </div>
                <div class="leaderboard-score">${escapeHtml(item.total_score)}</div>
              </div>
            `).join("")}
          </div>
        ` : `<p class="leaderboard-empty">还没有测试集成绩进入排行榜。</p>`}
      </div>
    `;
  }

  function renderShell() {
    captureSidebarScroll();
    state.route = parseRoute();
    const stats = sidebarStats();
    app.innerHTML = `
      <div class="shell">
        <aside class="sidebar">
          <div class="sidebar-top">
            <div class="sidebar-head">
              <div class="brand-mark small">OJ</div>
              <div>
                <strong>AIOps OJ</strong>
                <span>${escapeHtml(state.user.username)} · ${escapeHtml(state.user.role)}</span>
              </div>
            </div>
            <div class="sidebar-stat-grid">
              <article class="sidebar-stat">
                <span>题目</span>
                <strong>${escapeHtml(stats.total)}</strong>
              </article>
              <article class="sidebar-stat">
                <span>可提交</span>
                <strong>${escapeHtml(stats.enabled)}</strong>
              </article>
              <article class="sidebar-stat wide">
                <span>AI 分析可见</span>
                <strong>${escapeHtml(stats.visible)}</strong>
              </article>
            </div>
          </div>
          <div class="sidebar-group">
            <div class="sidebar-label">导航</div>
            <nav>
              ${navButton("总览", "overview", "/overview")}
              ${navButton("题目列表", "cases", "/cases")}
              ${navButton("测试题目", "testSets", "/test-sets")}
              ${navButton("提交记录", "submissions", "/submissions")}
              ${navButton("agent配置", "profile", "/profile")}
              ${state.user.role === "admin" ? navButton("管理", "admin", "/admin") : ""}
            </nav>
          </div>
          <div id="sidebarLeaderboardSlot">${renderLeaderboardSection()}</div>
          <div class="sidebar-footer">
            <button class="ghost logout" id="logoutBtn">退出</button>
          </div>
        </aside>
        <main class="content">
          <div class="content-frame">
            <div id="notice" class="notice-stack" aria-live="polite"></div>
            <div id="mainView"></div>
          </div>
        </main>
      </div>
    `;
    document.querySelectorAll("[data-route]").forEach((button) => {
      button.addEventListener("click", () => routeTo(button.dataset.route));
    });
    document.getElementById("logoutBtn").addEventListener("click", () => emit("auth:logout"));
    const sidebar = app.querySelector(".sidebar");
    if (sidebar && state.sidebarScrollTop > 0) {
      requestAnimationFrame(() => {
        sidebar.scrollTop = state.sidebarScrollTop;
      });
    }
    const content = app.querySelector(".content");
    const frame = app.querySelector(".content-frame");
    if (content) content.scrollTop = 0;
    if (frame) frame.scrollTop = 0;
    window.scrollTo({ top: 0, left: 0, behavior: "auto" });
    renderCurrentView();
  }

  function renderCurrentView() {
    const mainView = document.getElementById("mainView");
    if (mainView) mainView.onclick = null;
    if (state.route.name !== "submission") closeDetailStream();
    if (state.route.name === "overview") renderOverview();
    else if (state.route.name === "cases") renderCasesList();
    else if (state.route.name === "testSets") renderTestSets();
    else if (state.route.name === "case") renderCaseDetail(state.route.params.id);
    else if (state.route.name === "submit") renderSubmit(state.route.params.id);
    else if (state.route.name === "testSetSubmit") renderTestSetSubmit(state.route.params.id);
    else if (state.route.name === "submissions") renderSubmissions();
    else if (state.route.name === "submission") renderSubmissionDetail(state.route.params.id);
    else if (state.route.name === "profile") renderProfile();
    else if (state.route.name === "admin") renderAdmin();
    else if (state.route.name === "adminCase") renderAdminCaseEditor(state.route.params.id);
    else if (state.route.name === "adminCaseNew") renderAdminCaseCreator();
  }

  function renderSidebarLeaderboard() {
    const slot = document.getElementById("sidebarLeaderboardSlot");
    if (slot) slot.innerHTML = renderLeaderboardSection();
  }

export { navButton, sidebarStats, renderLeaderboardSection, renderShell, renderCurrentView, renderSidebarLeaderboard };
