(function () {
  const OJApp = window.OJApp;
  const {
    state,
    app,
    api,
    escapeHtml,
    setToken,
    storeLoginCredential,
    prefillLoginCredential,
    closeDetailStream,
    loadInitialData,
    applyBootstrapResponse,
    parseRoute,
    renderShell,
    showNotice,
    maybeRefreshLeaderboard,
  } = OJApp;
function logout(render = true) {
  closeDetailStream();
  setToken("");
  state.user = null;
  state.config = null;
  state.profile = null;
  state.cases = [];
  state.casesLoadedAt = 0;
  state.casesLoadingPromise = null;
  state.leaderboard = [];
  state.leaderboardCaseCount = 0;
  state.testSetLeaderboardCaseCount = 0;
  state.leaderboardLoadedAt = 0;
  state.leaderboardLoadingPromise = null;
  state.submissions = [];
  state.submissionsTotal = 0;
  state.submissionsTotalPages = 1;
  state.submissionsLoadingPromise = null;
  state.submissionsRequestId = 0;
  state.caseView = {
    page: 1,
    perPage: 20,
  };
  state.submissionView = {
    username: "",
    caseId: "",
    displayCaseName: "",
    sortBy: "created_at",
    sortOrder: "desc",
    page: 1,
    perPage: 20,
  };
  state.adminView = {
    tab: "cases",
    caseQuery: "",
    casePage: 1,
    casePerPage: 10,
    users: [],
    usersLoadedAt: 0,
    usersLoadingPromise: null,
    usersError: "",
    agentStatus: null,
    agentLoadedAt: 0,
    agentLoadingPromise: null,
    agentError: "",
  };
  if (render) renderLogin();
}

function caseById(id) {
  return state.cases.find((item) => item.id === id) || null;
}

function renderAuthShell({
  eyebrow,
  title,
  description,
  panelEyebrow,
  panelTitle,
  panelDescription,
  formMarkup,
  switchButtonId,
  switchButtonLabel,
  messageId,
  message,
}) {
  return `
    <main class="login-shell">
      <section class="login-stage">
        <div class="login-copy">
          <div class="login-copy-head">
            <div class="brand-mark">OJ</div>
            <span class="eyebrow">${escapeHtml(eyebrow)}</span>
          </div>
          <h1>${escapeHtml(title)}</h1>
          <p>${escapeHtml(description)}</p>
          <div class="login-feature-list">
            <article>
              <strong>结构化评测</strong>
              <span>统一输出格式、统一评分 API、统一回放链路。</span>
            </article>
            <article>
              <strong>隔离运行</strong>
              <span>每次提交都有独立的 Hermes 运行环境与技能目录。</span>
            </article>
            <article>
              <strong>证据可追溯</strong>
              <span>题面、工具调用、过程输出和 AI 分析都能在详情页复盘。</span>
            </article>
          </div>
        </div>
        <section class="login-panel">
          <div class="login-panel-head">
            <span class="eyebrow">${escapeHtml(panelEyebrow)}</span>
            <h2>${escapeHtml(panelTitle)}</h2>
            <p>${escapeHtml(panelDescription)}</p>
          </div>
          ${formMarkup}
          <button type="button" class="ghost full-width" id="${escapeHtml(switchButtonId)}">${escapeHtml(switchButtonLabel)}</button>
          <p id="${escapeHtml(messageId)}" class="form-message">${escapeHtml(message)}</p>
        </section>
      </section>
    </main>
  `;
}

function renderLogin(message = "") {
  app.innerHTML = renderAuthShell({
    eyebrow: "AIOps OJ",
    title: "AIOps 评测平台",
    description: "面向云服务故障诊断的实战评测环境，强调根因定位、证据链推理和结构化结论输出。",
    panelEyebrow: "Welcome Back",
    panelTitle: "登录",
    panelDescription: "使用你的平台账号进入题目、提交和个人配置页面。",
    formMarkup: `
      <form id="loginForm" class="form-stack" autocomplete="on">
        <label>
          <span>用户名</span>
          <input id="loginUsername" name="username" autocomplete="username" value="${escapeHtml(state.savedUsername)}" required />
        </label>
        <label>
          <span>密码</span>
          <input id="loginPassword" name="password" type="password" autocomplete="current-password" required />
        </label>
        <button type="submit" class="primary">登录</button>
      </form>
    `,
    switchButtonId: "showRegisterBtn",
    switchButtonLabel: "注册账号",
    messageId: "loginMessage",
    message,
  });
  document.getElementById("showRegisterBtn").addEventListener("click", () => renderRegister());
  prefillLoginCredential();
  document.getElementById("loginForm").addEventListener("submit", async (event) => {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const messageEl = document.getElementById("loginMessage");
    messageEl.textContent = "";
    try {
      const data = await api("/api/auth/login", {
        method: "POST",
        body: JSON.stringify({
          username: form.get("username"),
          password: form.get("password"),
        }),
      });
      const username = String(form.get("username") || "");
      localStorage.setItem("oj_saved_username", username);
      state.savedUsername = username;
      await storeLoginCredential(username, String(form.get("password") || ""));
      setToken(data.token);
      applyBootstrapResponse(await api("/api/bootstrap"));
      if (!window.location.hash) window.location.hash = "#/overview";
      state.route = parseRoute();
      renderShell();
      maybeRefreshLeaderboard?.().catch(() => {});
    } catch (error) {
      messageEl.textContent = error.message;
    }
  });
}

function renderRegister(message = "") {
  app.innerHTML = renderAuthShell({
    eyebrow: "Create Access",
    title: "创建你的诊断席位",
    description: "注册后即可配置模型、评分 API、SOUL.md 与个人 Skill，并参与平台故障诊断测评。",
    panelEyebrow: "New Account",
    panelTitle: "注册账号",
    panelDescription: "填写用户名、密码和邀请码后，会自动登录并进入总览页。",
    formMarkup: `
      <form id="registerForm" class="form-stack" autocomplete="on">
        <label>
          <span>用户名</span>
          <input name="username" autocomplete="username" value="${escapeHtml(state.savedUsername)}" required />
        </label>
        <label>
          <span>密码</span>
          <input name="password" type="password" autocomplete="new-password" required />
        </label>
        <label>
          <span>邀请码</span>
          <input name="invite_code" autocomplete="off" required />
        </label>
        <button type="submit" class="primary">注册并登录</button>
      </form>
    `,
    switchButtonId: "showLoginBtn",
    switchButtonLabel: "返回登录",
    messageId: "registerMessage",
    message,
  });
  document.getElementById("showLoginBtn").addEventListener("click", () => renderLogin());
  document.getElementById("registerForm").addEventListener("submit", async (event) => {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const messageEl = document.getElementById("registerMessage");
    messageEl.textContent = "";
    try {
      const data = await api("/api/auth/register", {
        method: "POST",
        body: JSON.stringify({
          username: form.get("username"),
          password: form.get("password"),
          invite_code: form.get("invite_code"),
        }),
      });
      const username = String(form.get("username") || "");
      localStorage.setItem("oj_saved_username", username);
      state.savedUsername = username;
      await storeLoginCredential(username, String(form.get("password") || ""));
      setToken(data.token);
      applyBootstrapResponse(await api("/api/bootstrap"));
      window.location.hash = "#/overview";
      state.route = parseRoute();
      renderShell();
      maybeRefreshLeaderboard?.().catch(() => {});
    } catch (error) {
      messageEl.textContent = error.message;
    }
  });
}

async function boot() {
  if (OJApp.bootPromise) return OJApp.bootPromise;
  OJApp.bootPromise = (async () => {
    if (!OJApp.hashListenerBound) {
      window.addEventListener("hashchange", () => {
        if (!state.user) return;
        state.route = parseRoute();
        renderShell();
      });
      OJApp.hashListenerBound = true;
    }
    if (!state.token) {
      renderLogin();
      return;
    }
    try {
      applyBootstrapResponse(await api("/api/bootstrap"));
      if (!window.location.hash) window.location.hash = "#/overview";
      state.route = parseRoute();
      renderShell();
      maybeRefreshLeaderboard?.().catch(() => {});
    } catch (error) {
      renderLogin(error.message);
    }
  })();
  return OJApp.bootPromise;
}
  Object.assign(OJApp, { logout, renderLogin, renderRegister, boot });
})();
