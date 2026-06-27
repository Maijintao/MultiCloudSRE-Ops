(function () {
  const OJApp = window.OJApp;
  const {
    state,
    escapeHtml,
    routeTo,
    showNotice,
    api,
    compactTime,
    caseOrderText,
    confirmTwice,
    refreshLeaderboard,
  } = OJApp;

  const ADMIN_TABS = [
    { key: "cases", label: "题目管理", eyebrow: "Cases", description: "批量管理题目开关、顺序和编辑入口" },
    { key: "public", label: "公开内容", eyebrow: "Public", description: "维护公告、测试流程和 output.md" },
    { key: "users", label: "用户", eyebrow: "Users", description: "创建账号、修改角色和删除用户" },
    { key: "runtime", label: "运行状态", eyebrow: "Runtime", description: "查看 Agent 和评分链路当前状态" },
  ];

  function adminViewState() {
    if (!state.adminView || typeof state.adminView !== "object") {
      state.adminView = {};
    }
    const viewState = state.adminView;
    viewState.tab = viewState.tab || "cases";
    viewState.caseQuery = viewState.caseQuery || "";
    viewState.casePage = Math.max(1, Number(viewState.casePage) || 1);
    viewState.casePerPage = Math.max(1, Number(viewState.casePerPage) || 10);
    viewState.users = Array.isArray(viewState.users) ? viewState.users : [];
    viewState.usersLoadedAt = Number(viewState.usersLoadedAt) || 0;
    viewState.usersLoadingPromise = viewState.usersLoadingPromise || null;
    viewState.usersError = viewState.usersError || "";
    viewState.agentStatus = viewState.agentStatus || null;
    viewState.agentLoadedAt = Number(viewState.agentLoadedAt) || 0;
    viewState.agentLoadingPromise = viewState.agentLoadingPromise || null;
    viewState.agentError = viewState.agentError || "";
    return viewState;
  }

  function rerenderAdminIfActive() {
    if (state.route?.name === "admin") renderAdmin();
  }

  function adminScrollContainer() {
    return document.querySelector(".content-frame") || document.querySelector(".content") || document.getElementById("mainView");
  }

  function rerenderAdminPreservingScroll() {
    const container = adminScrollContainer();
    const scrollTop = container?.scrollTop || 0;
    renderAdmin();
    window.requestAnimationFrame(() => {
      const nextContainer = adminScrollContainer();
      if (nextContainer) nextContainer.scrollTop = scrollTop;
    });
  }

  function patchAdminCase(caseId, nextCase) {
    if (!caseId || !Array.isArray(state.cases)) return;
    state.cases = state.cases.map((item) => (
      item.id === caseId
        ? { ...item, ...(nextCase || {}) }
        : item
    ));
  }

  async function adminSetTab(tabKey) {
    const viewState = adminViewState();
    if (!tabKey || tabKey === viewState.tab) return;
    viewState.tab = tabKey;
    renderAdmin();
    if (tabKey === "users") {
      try {
        await ensureAdminUsers();
      } catch (error) {
        showNotice(error.message, "error");
      }
    }
    if (tabKey === "runtime") {
      try {
        await ensureAdminAgentStatus();
      } catch (error) {
        showNotice(error.message, "error");
      }
    }
  }

  function adminSetCasePage(pageValue) {
    const viewState = adminViewState();
    const nextPage = Number(pageValue);
    if (!Number.isFinite(nextPage) || nextPage < 1 || nextPage === viewState.casePage) return;
    viewState.casePage = nextPage;
    renderAdmin();
  }

  function routeWithNotice(path, message, type = "success") {
    routeTo(path);
    setTimeout(() => {
      showNotice(message, type);
    }, 0);
  }

  async function adminRefreshUsers() {
    try {
      await ensureAdminUsers(true);
    } catch (error) {
      showNotice(error.message, "error");
    }
  }

  async function adminRefreshRuntime() {
    try {
      await ensureAdminAgentStatus(true);
    } catch (error) {
      showNotice(error.message, "error");
    }
  }

  async function refreshAdminContentState() {
    const [config, caseData] = await Promise.all([
      api("/api/config"),
      api("/api/cases"),
    ]);
    state.config = config;
    state.cases = Array.isArray(caseData?.cases) ? caseData.cases : [];
    state.testSets = Array.isArray(config?.test_sets) ? config.test_sets : [];
    state.testSetsLoadedAt = Date.now();
    await refreshLeaderboard?.({ rerenderShell: false });
    return { config: state.config, cases: state.cases };
  }

  function newCaseTemplateFiles() {
    return {
      case_json: JSON.stringify(
        {
          id: "new-case-id",
          title: "新题目标题",
          case_set_id: "ungrouped",
          fault_phenomenon: "请填写故障现象",
          public_case_info: "请填写题目公开信息",
          submission_enabled: false,
          ai_analysis_visible: true,
        },
        null,
        2,
      ),
      inject_script: "#!/usr/bin/env bash\nset -euo pipefail\n\n",
      recover_script: "#!/usr/bin/env bash\nset -euo pipefail\n\n",
      ideal_answer_json: JSON.stringify(
        {
          fault_info: {
            root_cause: "请填写根因",
            faulty_clouds: ["unknown"],
            affected_clouds: ["unknown"],
            fault_location: {
              module: "unknown",
              file_path: null,
              function_or_config: null,
              description: "请说明故障位置与原因",
            },
          },
          reasoning_process: {
            observed_symptoms: ["请填写观察到的故障现象"],
            key_evidence: [
              {
                source: "请填写证据来源",
                content: "请填写关键证据内容",
                conclusion: "请填写由此得到的结论",
              },
            ],
            causal_chain: ["请填写因果链"],
          },
          verification_method: {
            verification_commands: [
              {
                cmd: "请填写验证命令",
                purpose: "请填写验证目的",
                expected_result: "请填写期望结果",
              },
            ],
            success_criteria: ["请填写修复成功标准"],
          },
          proposed_resolution: {
            suggestion: "请填写修复建议",
            fix_steps: ["请填写修复步骤"],
          },
          confidence: 0.8,
        },
        null,
        2,
      ),
      rubrics_json: JSON.stringify(
        {
          positive_points_total: 100,
          negative_points_total: -50,
          rubrics: [
            {
              criterion: "准确指出真实根因",
              points: 40,
              tags: ["level:example", "axis:accuracy"],
            },
            {
              criterion: "给出关键证据、因果链、验证方法和修复建议",
              points: 60,
              tags: ["level:example", "axis:completeness"],
            },
            {
              criterion: "错误地把根因定位到无关组件",
              points: -20,
              tags: ["level:example", "axis:accuracy"],
            },
            {
              criterion: "建议明显危险或破坏性的修复操作",
              points: -30,
              tags: ["level:example", "axis:accuracy"],
            },
          ],
        },
        null,
        2,
      ),
    };
  }

  function renderAdminCaseForm(view, mode, casePayload, files) {
    const caseInfo = casePayload || {};
    const isCreate = mode === "create";
    const heading = isCreate
      ? "新建题目"
      : `配置题目 · ${caseOrderText(caseInfo)} · ${caseInfo.title || caseInfo.id || ""}`;
    const eyebrow = isCreate ? "Create Case" : `Case · ${caseInfo.id || ""}`;
    const submitLabel = isCreate ? "创建题目" : "保存五个文件";
    const maxCaseArchiveBytes = Number(state.config?.max_case_archive_bytes || 0);
    const maxCaseArchiveText = maxCaseArchiveBytes
      ? `${Math.max(1, Math.round(maxCaseArchiveBytes / (1024 * 1024)))} MB`
      : "10 MB";
    view.innerHTML = `
      <section class="page-title">
        <div>
          <span class="eyebrow">${escapeHtml(eyebrow)}</span>
          <h2>${escapeHtml(heading)}</h2>
          <p>这里直接维护题目的五个核心文件，保存后会覆盖对应题目目录下的内容。</p>
        </div>
        <div class="submit-actions">
          <button type="button" class="ghost" data-route="/admin">返回管理</button>
          ${!isCreate ? `<button type="button" class="ghost" data-delete-case="${escapeHtml(caseInfo.id || "")}">删除题目</button>` : ""}
        </div>
      </section>
      <form id="adminCaseForm" class="panel form-panel public-content-form">
        <div class="section-head">
          <div>
            <span class="eyebrow">Files</span>
            <h3>${escapeHtml(submitLabel)}</h3>
          </div>
          <div class="submit-actions">
            ${isCreate ? `
              <input type="file" id="caseArchiveInput" accept=".zip,application/zip" hidden />
              <button type="button" class="ghost" id="caseArchiveUploadBtn">上传 ZIP 出题</button>
            ` : ""}
            <button type="submit" class="primary">${escapeHtml(submitLabel)}</button>
          </div>
        </div>
        <p class="muted">
          这里会直接覆盖该题目目录下的 <code>case.json</code>、<code>inject.sh</code>、
          <code>recover.sh</code>、<code>ideal-answer.json</code>、<code>rubrics.json</code>。
        </p>
        ${isCreate ? `<p class="muted">也可以直接上传 ZIP 自动出题。ZIP 内需要包含这 5 个文件，允许最外层再套一层目录；最大 ${escapeHtml(maxCaseArchiveText)}。</p>` : ""}
        <section class="content-editor-grid admin-case-editor-grid">
          <label>
            <span>case.json</span>
            <textarea name="case_json" class="json-editor" rows="20">${escapeHtml(files.case_json || "")}</textarea>
          </label>
          <label>
            <span>ideal-answer.json</span>
            <textarea name="ideal_answer_json" class="json-editor" rows="20">${escapeHtml(files.ideal_answer_json || "")}</textarea>
          </label>
          <label>
            <span>rubrics.json</span>
            <textarea name="rubrics_json" class="json-editor" rows="20">${escapeHtml(files.rubrics_json || "")}</textarea>
          </label>
          <label class="editor-wide">
            <span>inject.sh</span>
            <textarea name="inject_script" class="json-editor code-editor" rows="14">${escapeHtml(files.inject_script || "")}</textarea>
          </label>
          <label class="editor-wide">
            <span>recover.sh</span>
            <textarea name="recover_script" class="json-editor code-editor" rows="14">${escapeHtml(files.recover_script || "")}</textarea>
          </label>
        </section>
        <div class="submit-actions">
          <button type="button" class="ghost" data-route="/admin">返回管理</button>
          <button type="submit" class="primary">${escapeHtml(submitLabel)}</button>
        </div>
      </form>
    `;
    view.querySelectorAll("[data-route]").forEach((button) => {
      button.addEventListener("click", () => routeTo(button.dataset.route));
    });
  }

  async function toggleCaseFlag(caseId, flagName, nextValue) {
    return api(`/api/admin/cases/${encodeURIComponent(caseId)}/flags`, {
      method: "PATCH",
      body: JSON.stringify({ [flagName]: nextValue }),
    });
  }

  async function applyCaseFlagToggle(caseItem, flagName, nextValue, successMessage) {
    const response = await toggleCaseFlag(caseItem.id, flagName, nextValue);
    patchAdminCase(caseItem.id, response?.case || { [flagName]: nextValue });
    rerenderAdminPreservingScroll();
    return response;
  }

  async function deleteAdminCase(caseId, caseTitle) {
    const label = caseTitle || caseId;
    const confirmed = confirmTwice(
      `确定要删除题目 ${label} 吗？这会直接删除该题目的五个文件，已完成提交记录不会自动删除。`,
      `最后确认一次：删除题目 ${label} 后无法恢复。如果该题还有排队中或运行中的提交，系统会拒绝删除。是否继续？`,
    );
    if (!confirmed) return null;
    return api(`/api/admin/cases/${encodeURIComponent(caseId)}`, {
      method: "DELETE",
    });
  }

  async function uploadAdminCaseArchive(file) {
    if (!file) return null;
    const maxBytes = Number(state.config?.max_case_archive_bytes || 0);
    if (maxBytes > 0 && file.size > maxBytes) {
      throw new Error(`ZIP 文件过大，最大 ${Math.max(1, Math.round(maxBytes / (1024 * 1024)))} MB`);
    }
    return api("/api/admin/cases/import-zip", {
      method: "POST",
      raw: true,
      headers: {
        "Content-Type": file.type || "application/zip",
        "X-Case-Archive-Name": encodeURIComponent(file.name || "case.zip"),
      },
      body: file,
    });
  }

  function bindCaseArchiveUpload(button, input, onUploaded) {
    if (!button || !input) return;
    button.addEventListener("click", () => input.click());
    input.addEventListener("change", async () => {
      const file = input.files?.[0];
      if (!file) return;
      button.disabled = true;
      try {
        const created = await uploadAdminCaseArchive(file);
        await refreshAdminContentState();
        onUploaded?.(created);
      } catch (error) {
        showNotice(error.message, "error");
      } finally {
        input.value = "";
        button.disabled = false;
      }
    });
  }

  function adminCaseMetrics() {
    const cases = Array.isArray(state.cases) ? state.cases : [];
    return {
      total: cases.length,
      enabled: cases.filter((item) => item?.submission_enabled !== false).length,
      hiddenAi: cases.filter((item) => item?.ai_analysis_visible === false).length,
      visibleAi: cases.filter((item) => item?.ai_analysis_visible !== false).length,
      ungroupedCases: cases.filter((item) => item?.case_set_id === "ungrouped").length,
      testSetCases: cases.filter((item) => item?.case_set_id && !["training", "ungrouped"].includes(item.case_set_id)).length,
    };
  }

  function caseSetOptions(selectedId = "training") {
    const testSets = Array.isArray(state.testSets) ? state.testSets : [];
    const selected = selectedId || "training";
    return [
      `<option value="training" ${selected === "training" ? "selected" : ""}>训练集</option>`,
      `<option value="ungrouped" ${selected === "ungrouped" ? "selected" : ""}>未分组</option>`,
      ...testSets.map((item) => `
        <option value="${escapeHtml(item.id)}" ${selected === item.id ? "selected" : ""}>${escapeHtml(item.name || item.id)}</option>
      `),
    ].join("");
  }

  function caseSetLabel(item) {
    const setId = item?.case_set_id || "training";
    if (setId === "training") return "训练集";
    if (setId === "ungrouped") return "未分组";
    const testSet = (Array.isArray(state.testSets) ? state.testSets : []).find((entry) => entry.id === setId);
    return testSet?.name || "测试集";
  }

  function caseSetStatusClass(item) {
    const setId = item?.case_set_id || "training";
    if (setId === "training") return "ok";
    if (setId === "ungrouped") return "bad";
    return "queued";
  }

  function renderAdminTestSetManager() {
    const testSets = Array.isArray(state.testSets) ? state.testSets : [];
    return `
      <section class="admin-test-set-manager">
        <div class="section-head">
          <div>
            <span class="eyebrow">Test Sets</span>
            <h4>测试集提交控制</h4>
          </div>
        </div>
        <div class="admin-test-set-results">
          ${testSets.length ? testSets.map((item) => {
            const enabled = item?.submission_enabled !== false;
            const caseNumbers = Array.isArray(item?.case_numbers) ? item.case_numbers : [];
            return `
              <div class="admin-test-set-row">
                <div class="admin-test-set-main">
                  <div class="admin-case-card-meta">
                    <span class="status ${enabled ? "ok" : "bad"}">${enabled ? "选手可提交" : "选手不可提交"}</span>
                    <span class="admin-case-pill">${escapeHtml(item.id)}</span>
                  </div>
                  <label class="admin-test-set-name-field">
                    <span>名称</span>
                    <input type="text" maxlength="64" value="${escapeHtml(item.name || item.id)}" data-admin-test-set-name="${escapeHtml(item.id)}" />
                  </label>
                  <div class="test-set-case-numbers">
                    <span>题目编号</span>
                    ${caseNumbers.length
                      ? caseNumbers.map((number) => `<code>#${escapeHtml(number)}</code>`).join("")
                      : `<span>暂无题目</span>`}
                  </div>
                </div>
                <div class="admin-test-set-actions">
                  <button type="button" class="ghost slim" data-admin-save-test-set="${escapeHtml(item.id)}">保存名称</button>
                  <button type="button" class="ghost slim" data-admin-toggle-test-set-submit="${escapeHtml(item.id)}">${enabled ? "关闭提交" : "开放提交"}</button>
                  <button type="button" class="ghost slim danger" data-admin-delete-test-set="${escapeHtml(item.id)}">删除</button>
                </div>
              </div>
            `;
          }).join("") : `<section class="empty compact-empty">当前没有测试集</section>`}
        </div>
      </section>
    `;
  }

  function currentAdminCasesPage() {
    const viewState = adminViewState();
    const perPage = Math.max(1, Number(viewState.casePerPage) || 10);
    const items = filteredAdminCases();
    const totalPages = Math.max(1, Math.ceil(items.length / perPage));
    viewState.casePage = Math.min(Math.max(1, Number(viewState.casePage) || 1), totalPages);
    return viewState.casePage;
  }

  function filteredAdminCases() {
    const viewState = adminViewState();
    const query = String(viewState.caseQuery || "").trim().toLowerCase();
    if (!query) return Array.isArray(state.cases) ? state.cases.slice() : [];
    return (Array.isArray(state.cases) ? state.cases : []).filter((item) => {
      const haystack = [
        caseOrderText(item),
        item.id || "",
        item.title || "",
      ].join(" ").toLowerCase();
      return haystack.includes(query);
    });
  }

  function pagedAdminCases() {
    const viewState = adminViewState();
    const items = filteredAdminCases();
    const perPage = Math.max(1, Number(viewState.casePerPage) || 10);
    const total = items.length;
    const totalPages = Math.max(1, Math.ceil(total / perPage));
    const page = currentAdminCasesPage();
    const startIndex = (page - 1) * perPage;
    const pageItems = items.slice(startIndex, startIndex + perPage);
    return {
      items: pageItems,
      total,
      totalPages,
      page,
      start: total ? startIndex + 1 : 0,
      end: total ? startIndex + pageItems.length : 0,
    };
  }

  function adminTabButton(tab) {
    const viewState = adminViewState();
    const active = viewState.tab === tab.key;
    return `
      <button
        type="button"
        class="admin-tab-button ${active ? "active" : ""}"
        data-admin-tab="${escapeHtml(tab.key)}"
        onclick="window.OJApp.adminSetTab('${escapeHtml(tab.key)}')"
      >
        <span>${escapeHtml(tab.eyebrow)}</span>
        <strong>${escapeHtml(tab.label)}</strong>
        <small>${escapeHtml(tab.description)}</small>
      </button>
    `;
  }

  function renderAdminMetricsStrip() {
    const metrics = adminCaseMetrics();
    return `
      <div class="admin-metric-strip">
        <article class="admin-mini-metric">
          <span>总题目</span>
          <strong>${escapeHtml(metrics.total)}</strong>
        </article>
        <article class="admin-mini-metric">
          <span>开放提交</span>
          <strong>${escapeHtml(metrics.enabled)}</strong>
        </article>
        <article class="admin-mini-metric">
          <span>AI 分析隐藏</span>
          <strong>${escapeHtml(metrics.hiddenAi)}</strong>
        </article>
        <article class="admin-mini-metric">
          <span>AI 分析可见</span>
          <strong>${escapeHtml(metrics.visibleAi)}</strong>
        </article>
        <article class="admin-mini-metric">
          <span>未分组</span>
          <strong>${escapeHtml(metrics.ungroupedCases)}</strong>
        </article>
        <article class="admin-mini-metric">
          <span>测试集题</span>
          <strong>${escapeHtml(metrics.testSetCases)}</strong>
        </article>
      </div>
    `;
  }

  function renderAdminCaseRow(item) {
    return `
      <article class="admin-case-card">
        <div class="admin-case-card-main">
          <div class="admin-case-card-meta">
            <span class="admin-case-pill">${escapeHtml(`${caseOrderText(item)} · ${item.id}`)}</span>
            <span class="status ${item.submission_enabled ? "ok" : "bad"}">${item.submission_enabled ? "选手可提交" : "选手不可提交"}</span>
            <span class="status ${item.ai_analysis_visible ? "ok" : "queued"}">${item.ai_analysis_visible ? "AI 分析可见" : "AI 分析隐藏"}</span>
            <span class="status ${caseSetStatusClass(item)}">${escapeHtml(caseSetLabel(item))}</span>
          </div>
          <h3>${escapeHtml(item.title)}</h3>
        </div>
        <div class="admin-case-card-actions">
          <label class="admin-inline-select">
            <span>所属集合</span>
            <select data-admin-case-set="${escapeHtml(item.id)}">
              ${caseSetOptions(item.case_set_id || "training")}
            </select>
          </label>
          <button type="button" class="ghost slim" data-admin-toggle-submit="${escapeHtml(item.id)}">${item.submission_enabled ? "关闭提交" : "开放提交"}</button>
          <button type="button" class="ghost slim" data-admin-toggle-ai="${escapeHtml(item.id)}">${item.ai_analysis_visible ? "隐藏 AI" : "显示 AI"}</button>
          <button type="button" class="ghost slim" data-route="/cases/${encodeURIComponent(item.id)}">查看题面</button>
          <button type="button" class="ghost slim" data-delete-case-row="${escapeHtml(item.id)}">删除</button>
          <button type="button" class="primary slim" data-route="/admin/cases/${encodeURIComponent(item.id)}">配置文件</button>
        </div>
      </article>
    `;
  }

  function renderAdminCasesPanel() {
    const viewState = adminViewState();
    const maxCaseArchiveBytes = Number(state.config?.max_case_archive_bytes || 0);
    const maxCaseArchiveText = maxCaseArchiveBytes
      ? `${Math.max(1, Math.round(maxCaseArchiveBytes / (1024 * 1024)))} MB`
      : "10 MB";
    const pageData = pagedAdminCases();
    return `
      <section class="panel admin-section-panel">
        <div class="section-head">
          <div>
            <span class="eyebrow">Case Desk</span>
            <h3>题目管理</h3>
          </div>
          <div class="submit-actions">
            <input type="file" id="adminCaseArchiveInput" accept=".zip,application/zip" hidden />
            <button type="button" class="ghost" id="adminCreateTestSetBtn">增加测试集</button>
            <button type="button" class="ghost" id="adminCaseArchiveBtn">上传 ZIP 出题</button>
            <button type="button" class="primary" data-route="/admin/cases/new">新建题目</button>
          </div>
        </div>
        <p class="muted">默认只展示这一块，避免管理页一打开就把用户、状态和大文本编辑器全部一起加载。ZIP 出题上限 ${escapeHtml(maxCaseArchiveText)}。</p>
        ${renderAdminMetricsStrip()}
        ${renderAdminTestSetManager()}
        <div class="admin-case-toolbar">
          <label class="admin-search-field">
            <span>筛选题目</span>
            <input
              type="search"
              id="adminCaseSearch"
              placeholder="按题号、id 或标题搜索"
              value="${escapeHtml(viewState.caseQuery || "")}"
            />
          </label>
        </div>
        <div class="submission-toolbar-meta">
          第 ${escapeHtml(pageData.page)} / ${escapeHtml(pageData.totalPages)} 页，当前显示 ${escapeHtml(pageData.start)}-${escapeHtml(pageData.end)} 条，共 ${escapeHtml(pageData.total)} 题。
        </div>
        <div class="admin-case-results">
          ${pageData.items.length
            ? pageData.items.map((item) => renderAdminCaseRow(item)).join("")
            : `<section class="empty compact-empty">没有匹配的题目</section>`}
        </div>
        <div class="submission-pagination">
          <div class="submission-pagination-info">第 ${escapeHtml(pageData.page)} / ${escapeHtml(pageData.totalPages)} 页</div>
          <div class="submit-actions submission-pagination-actions">
            <button type="button" class="ghost slim" data-admin-case-page="1" onclick="window.OJApp.adminSetCasePage(1)" ${pageData.page <= 1 ? "disabled" : ""}>首页</button>
            <button type="button" class="ghost slim" data-admin-case-page="${Math.max(1, pageData.page - 1)}" onclick="window.OJApp.adminSetCasePage(${Math.max(1, pageData.page - 1)})" ${pageData.page <= 1 ? "disabled" : ""}>上一页</button>
            <button type="button" class="ghost slim" data-admin-case-page="${Math.min(pageData.totalPages, pageData.page + 1)}" onclick="window.OJApp.adminSetCasePage(${Math.min(pageData.totalPages, pageData.page + 1)})" ${pageData.page >= pageData.totalPages ? "disabled" : ""}>下一页</button>
            <button type="button" class="ghost slim" data-admin-case-page="${pageData.totalPages}" onclick="window.OJApp.adminSetCasePage(${pageData.totalPages})" ${pageData.page >= pageData.totalPages ? "disabled" : ""}>末页</button>
          </div>
        </div>
      </section>
    `;
  }

  function renderAdminPublicContentPanel() {
    const editableConfig = state.config || {};
    return `
      <form id="publicContentForm" class="panel form-panel public-content-form admin-section-panel">
        <div class="section-head">
          <div>
            <span class="eyebrow">Public Content</span>
            <h3>公开内容管理</h3>
          </div>
          <button type="submit" class="primary">保存公开内容</button>
        </div>
        <p class="muted">这里直接维护 <code>config.json</code> 里对外展示的配置，以及项目根目录下的 <code>output.md</code>。</p>
        <section class="content-editor-grid">
          <label class="editor-wide">
            <span>公告</span>
            <textarea name="announcement" rows="4" placeholder="在总览页向所有用户展示的公告">${escapeHtml(editableConfig.announcement || "")}</textarea>
          </label>
          <label>
            <span>测试流程（每行一项）</span>
            <textarea name="test_flow" rows="10">${escapeHtml((editableConfig.test_flow || []).join("\n"))}</textarea>
          </label>
          <div class="policy-editor">
            <label><span>工具调用口径 · 定义</span><textarea name="tool_definition" rows="3">${escapeHtml(editableConfig.tool_call_policy?.definition || "")}</textarea></label>
            <label><span>工具调用口径 · 要求</span><textarea name="tool_expectation" rows="3">${escapeHtml(editableConfig.tool_call_policy?.expectation || "")}</textarea></label>
            <label><span>工具调用口径 · 评分</span><textarea name="tool_scoring" rows="3">${escapeHtml(editableConfig.tool_call_policy?.scoring || "")}</textarea></label>
          </div>
          <label class="editor-wide">
            <span>统一输出格式（output.md）</span>
            <textarea name="output_format_markdown" class="json-editor admin-output-editor" rows="26">${escapeHtml(editableConfig.output_format_markdown || "")}</textarea>
          </label>
        </section>
        <div class="submit-actions">
          <button type="submit" class="primary">保存公开内容</button>
        </div>
      </form>
    `;
  }

  function renderAdminUsersTable(users) {
    return `
      <table class="submissions">
        <thead>
          <tr>
            <th>ID</th>
            <th>用户名</th>
            <th>密码</th>
            <th>角色</th>
            <th>状态</th>
            <th>创建时间</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          ${users.map((item) => {
            const protectedAdmin = !!item.protected_admin;
            return `
              <tr data-admin-user="${escapeHtml(item.id)}" data-admin-username="${escapeHtml(item.username)}" data-admin-protected="${protectedAdmin ? "1" : "0"}">
                <td>${escapeHtml(item.id)}</td>
                <td>${escapeHtml(item.username)}${protectedAdmin ? ' <span class="status ok">内置管理员</span>' : ""}</td>
                <td><input class="inline-input" data-user-password type="password" placeholder="输入新密码" /></td>
                <td>
                  <select class="inline-input" data-user-role ${protectedAdmin ? "disabled" : ""}>
                    <option value="contestant" ${item.role === "contestant" ? "selected" : ""}>contestant</option>
                    <option value="admin" ${item.role === "admin" ? "selected" : ""}>admin</option>
                  </select>
                </td>
                <td>
                  <select class="inline-input" data-user-disabled ${protectedAdmin ? "disabled" : ""}>
                    <option value="0" ${item.disabled ? "" : "selected"}>正常</option>
                    <option value="1" ${item.disabled ? "selected" : ""}>禁用</option>
                  </select>
                </td>
                <td>${escapeHtml(compactTime(item.created_at))}</td>
                <td>
                  <div class="submit-actions">
                    <button type="button" class="ghost slim" data-save-password>保存密码</button>
                    <button type="button" class="ghost slim" data-delete-user ${protectedAdmin ? "disabled" : ""}>删除用户</button>
                  </div>
                </td>
              </tr>
            `;
          }).join("")}
        </tbody>
      </table>
    `;
  }

  function renderAdminUsersPanel() {
    const viewState = adminViewState();
    const usersLoading = !!viewState.usersLoadingPromise;
    const usersLoaded = !!viewState.usersLoadedAt;
    const usersError = viewState.usersError;
    return `
      <section class="admin-users-grid">
        <article class="panel admin-section-panel">
          <div class="section-head">
            <div>
              <span class="eyebrow">Create User</span>
              <h3>新增账号</h3>
            </div>
          </div>
          <form id="userForm" class="form-stack">
            <label><span>用户名</span><input name="username" required /></label>
            <label><span>密码</span><input name="password" type="password" required /></label>
            <label>
              <span>角色</span>
              <select name="role">
                <option value="contestant">contestant</option>
                <option value="admin">admin</option>
              </select>
            </label>
            <button type="submit" class="primary">创建账号</button>
          </form>
        </article>
        <article class="panel admin-section-panel">
          <div class="section-head">
            <div>
              <span class="eyebrow">Users</span>
              <h3>用户列表</h3>
            </div>
            <button type="button" class="ghost" data-admin-refresh-users onclick="window.OJApp.adminRefreshUsers()">刷新用户</button>
          </div>
          ${usersLoading ? `<section class="empty compact-empty">正在加载用户列表...</section>` : ""}
          ${!usersLoading && usersError ? `<section class="notice error always">${escapeHtml(usersError)}</section>` : ""}
          ${!usersLoading && !usersError && usersLoaded ? renderAdminUsersTable(viewState.users) : ""}
          ${!usersLoading && !usersError && !usersLoaded ? `<section class="empty compact-empty">首次打开这个标签页时才会加载用户列表。</section>` : ""}
        </article>
      </section>
    `;
  }

  function renderAdminRuntimePanel() {
    const viewState = adminViewState();
    const agentLoading = !!viewState.agentLoadingPromise;
    const agentLoaded = !!viewState.agentLoadedAt;
    const agentError = viewState.agentError;
    return `
      <article class="panel admin-section-panel">
        <div class="section-head">
          <div>
            <span class="eyebrow">Runtime</span>
            <h3>运行状态</h3>
          </div>
          <button type="button" class="ghost" data-admin-refresh-runtime onclick="window.OJApp.adminRefreshRuntime()">刷新状态</button>
        </div>
        <p class="muted">这里按需拉取当前 Agent 和评分配置状态，避免每次点进管理页都阻塞加载。</p>
        ${agentLoading ? `<section class="empty compact-empty">正在加载运行状态...</section>` : ""}
        ${!agentLoading && agentError ? `<section class="notice error always">${escapeHtml(agentError)}</section>` : ""}
        ${!agentLoading && !agentError && agentLoaded ? `<pre class="admin-status-pre">${escapeHtml(JSON.stringify(viewState.agentStatus, null, 2))}</pre>` : ""}
        ${!agentLoading && !agentError && !agentLoaded ? `<section class="empty compact-empty">首次打开这个标签页时才会加载运行状态。</section>` : ""}
      </article>
    `;
  }

  function renderAdminCurrentPanel() {
    const viewState = adminViewState();
    if (viewState.tab === "public") return renderAdminPublicContentPanel();
    if (viewState.tab === "users") return renderAdminUsersPanel();
    if (viewState.tab === "runtime") return renderAdminRuntimePanel();
    return renderAdminCasesPanel();
  }

  async function ensureAdminUsers(force = false) {
    const viewState = adminViewState();
    if (!force && viewState.usersLoadedAt) return viewState.users;
    if (viewState.usersLoadingPromise) return viewState.usersLoadingPromise;
    viewState.usersError = "";
    viewState.usersLoadingPromise = (async () => {
      try {
        const data = await api("/api/admin/users");
        viewState.users = Array.isArray(data?.users) ? data.users : [];
        viewState.usersLoadedAt = Date.now();
        return viewState.users;
      } catch (error) {
        viewState.usersError = error.message;
        throw error;
      } finally {
        viewState.usersLoadingPromise = null;
        rerenderAdminIfActive();
      }
    })();
    return viewState.usersLoadingPromise;
  }

  async function ensureAdminAgentStatus(force = false) {
    const viewState = adminViewState();
    if (!force && viewState.agentLoadedAt) return viewState.agentStatus;
    if (viewState.agentLoadingPromise) return viewState.agentLoadingPromise;
    viewState.agentError = "";
    viewState.agentLoadingPromise = (async () => {
      try {
        const data = await api("/api/admin/agent-status");
        viewState.agentStatus = data;
        viewState.agentLoadedAt = Date.now();
        return data;
      } catch (error) {
        viewState.agentError = error.message;
        throw error;
      } finally {
        viewState.agentLoadingPromise = null;
        rerenderAdminIfActive();
      }
    })();
    return viewState.agentLoadingPromise;
  }

  function primeActiveAdminTab() {
    const viewState = adminViewState();
    if (viewState.tab === "users" && !viewState.usersLoadedAt && !viewState.usersLoadingPromise) {
      ensureAdminUsers().catch(() => {});
    }
    if (viewState.tab === "runtime" && !viewState.agentLoadedAt && !viewState.agentLoadingPromise) {
      ensureAdminAgentStatus().catch(() => {});
    }
  }

  function renderAdmin() {
    if (state.user.role !== "admin") {
      document.getElementById("mainView").innerHTML = `<section class="empty">需要管理员权限</section>`;
      return;
    }
    const viewState = adminViewState();
    if (viewState.tab === "users" && !viewState.usersLoadedAt && !viewState.usersLoadingPromise) {
      ensureAdminUsers().catch(() => {});
    }
    if (viewState.tab === "runtime" && !viewState.agentLoadedAt && !viewState.agentLoadingPromise) {
      ensureAdminAgentStatus().catch(() => {});
    }
    const currentTab = ADMIN_TABS.find((item) => item.key === viewState.tab) || ADMIN_TABS[0];
    const mainView = document.getElementById("mainView");
    mainView.innerHTML = `
      <section class="page-title admin-hero">
        <div>
          <span class="eyebrow">Admin</span>
          <h2>管理面板</h2>
          <p>把题目管理、公开内容、用户和运行状态拆成独立工作区。默认先打开题目管理，其他内容按需加载，管理页会比以前快很多。</p>
        </div>
        <div class="admin-hero-focus">
          <span>${escapeHtml(currentTab.eyebrow)}</span>
          <strong>${escapeHtml(currentTab.label)}</strong>
          <small>${escapeHtml(currentTab.description)}</small>
        </div>
      </section>

      <section class="admin-tabs">
        ${ADMIN_TABS.map((tab) => adminTabButton(tab)).join("")}
      </section>

      ${renderAdminCurrentPanel()}
    `;

    mainView.onclick = (event) => {
      const target = event.target instanceof Element
        ? event.target
        : event.target?.parentElement;
      if (!target) return;

      const routeButton = target.closest("[data-route]");
      if (routeButton && mainView.contains(routeButton)) {
        routeTo(routeButton.dataset.route);
        return;
      }

      const tabButton = target.closest("[data-admin-tab]");
      if (tabButton && mainView.contains(tabButton)) {
        const nextTab = tabButton.dataset.adminTab;
        adminSetTab(nextTab);
        return;
      }

      if (viewState.tab === "cases") {
        const pageButton = target.closest("[data-admin-case-page]");
        if (pageButton && mainView.contains(pageButton)) {
          adminSetCasePage(pageButton.dataset.adminCasePage);
        }
      }
    };

    if (viewState.tab === "cases") {
      const searchInput = document.getElementById("adminCaseSearch");
      if (searchInput) {
        searchInput.addEventListener("input", () => {
          viewState.caseQuery = searchInput.value;
          viewState.casePage = 1;
          renderAdmin();
        });
      }

      bindCaseArchiveUpload(
        document.getElementById("adminCaseArchiveBtn"),
        document.getElementById("adminCaseArchiveInput"),
        (created) => {
          routeWithNotice(
            `/admin/cases/${encodeURIComponent(created.case.id)}`,
            `题目 ${created.case.title || created.case.id} 已通过 ZIP 创建`,
          );
        },
      );

      document.getElementById("adminCreateTestSetBtn")?.addEventListener("click", async (event) => {
        const button = event.currentTarget;
        button.disabled = true;
        try {
          const data = await api("/api/admin/test-sets", { method: "POST", body: JSON.stringify({}) });
          await refreshAdminContentState();
          rerenderAdminPreservingScroll();
          showNotice(`${data.test_set?.name || "测试集"} 已创建`, "success");
        } catch (error) {
          showNotice(error.message, "error");
        } finally {
          button.disabled = false;
        }
      });

      mainView.querySelectorAll("[data-admin-toggle-test-set-submit]").forEach((button) => {
        button.addEventListener("click", async () => {
          const testSetId = button.dataset.adminToggleTestSetSubmit;
          const testSet = state.testSets.find((item) => item.id === testSetId);
          if (!testSet) return;
          button.disabled = true;
          try {
            const response = await api(`/api/admin/test-sets/${encodeURIComponent(testSetId)}/flags`, {
              method: "PATCH",
              body: JSON.stringify({ submission_enabled: !(testSet.submission_enabled !== false) }),
            });
            state.testSets = Array.isArray(response?.test_sets) ? response.test_sets : state.testSets;
            state.config = { ...(state.config || {}), test_sets: state.testSets };
            state.testSetsLoadedAt = Date.now();
            rerenderAdminPreservingScroll();
            showNotice("测试集提交通道已更新", "success");
          } catch (error) {
            showNotice(error.message, "error");
          } finally {
            button.disabled = false;
          }
        });
      });

      mainView.querySelectorAll("[data-admin-save-test-set]").forEach((button) => {
        button.addEventListener("click", async () => {
          const testSetId = button.dataset.adminSaveTestSet;
          const input = mainView.querySelector(`[data-admin-test-set-name="${testSetId}"]`);
          const name = String(input?.value || "").trim();
          button.disabled = true;
          try {
            const response = await api(`/api/admin/test-sets/${encodeURIComponent(testSetId)}`, {
              method: "PATCH",
              body: JSON.stringify({ name }),
            });
            state.testSets = Array.isArray(response?.test_sets) ? response.test_sets : state.testSets;
            state.config = { ...(state.config || {}), test_sets: state.testSets };
            state.testSetsLoadedAt = Date.now();
            rerenderAdminPreservingScroll();
            showNotice("测试集名称已更新，历史提交名称保持不变", "success");
          } catch (error) {
            showNotice(error.message, "error");
          } finally {
            button.disabled = false;
          }
        });
      });

      mainView.querySelectorAll("[data-admin-delete-test-set]").forEach((button) => {
        button.addEventListener("click", async () => {
          const testSetId = button.dataset.adminDeleteTestSet;
          const testSet = state.testSets.find((item) => item.id === testSetId);
          if (!testSet) return;
          const memberCount = Array.isArray(testSet.case_numbers) ? testSet.case_numbers.length : 0;
          const confirmed = confirmTwice(
            `确定删除“${testSet.name}”吗？其中 ${memberCount} 道题将移入未分组。`,
            "最后确认一次：历史提交和成绩会保留，但以后不能再从该测试集提交。是否继续？",
          );
          if (!confirmed) return;
          button.disabled = true;
          try {
            const response = await api(`/api/admin/test-sets/${encodeURIComponent(testSetId)}`, { method: "DELETE" });
            await refreshAdminContentState();
            rerenderAdminPreservingScroll();
            showNotice(`${response?.deleted?.name || "测试集"} 已删除，成员题已移入未分组`, "success");
          } catch (error) {
            showNotice(error.message, "error");
          } finally {
            button.disabled = false;
          }
        });
      });

      mainView.querySelectorAll("[data-admin-case-set]").forEach((select) => {
        select.addEventListener("change", async () => {
          const caseId = select.dataset.adminCaseSet;
          const nextValue = select.value || "training";
          select.disabled = true;
          try {
            const response = await toggleCaseFlag(caseId, "case_set_id", nextValue);
            patchAdminCase(caseId, response?.case || { case_set_id: nextValue });
            showNotice("题目所属集合已更新", "success");
            rerenderAdminPreservingScroll();
          } catch (error) {
            showNotice(error.message, "error");
            await refreshAdminContentState();
            rerenderAdminPreservingScroll();
          } finally {
            select.disabled = false;
          }
        });
      });

      mainView.querySelectorAll("[data-admin-toggle-submit]").forEach((button) => {
        button.addEventListener("click", async () => {
          const caseId = button.dataset.adminToggleSubmit;
          const caseItem = state.cases.find((item) => item.id === caseId);
          if (!caseItem) return;
          button.disabled = true;
          try {
            await applyCaseFlagToggle(
              caseItem,
              "submission_enabled",
              !(caseItem.submission_enabled !== false),
              "题目提交开关已更新",
            );
            showNotice("题目提交通道已更新", "success");
          } catch (error) {
            showNotice(error.message, "error");
          } finally {
            button.disabled = false;
          }
        });
      });

      mainView.querySelectorAll("[data-admin-toggle-ai]").forEach((button) => {
        button.addEventListener("click", async () => {
          const caseId = button.dataset.adminToggleAi;
          const caseItem = state.cases.find((item) => item.id === caseId);
          if (!caseItem) return;
          button.disabled = true;
          try {
            await applyCaseFlagToggle(
              caseItem,
              "ai_analysis_visible",
              !(caseItem.ai_analysis_visible !== false),
              "AI 分析可见性已更新",
            );
            showNotice("AI 分析可见性已更新", "success");
          } catch (error) {
            showNotice(error.message, "error");
          } finally {
            button.disabled = false;
          }
        });
      });

      mainView.querySelectorAll("[data-delete-case-row]").forEach((button) => {
        button.addEventListener("click", async () => {
          const caseItem = state.cases.find((item) => item.id === button.dataset.deleteCaseRow);
          if (!caseItem) return;
          button.disabled = true;
          try {
            const result = await deleteAdminCase(caseItem.id, caseItem.title || caseItem.id);
            if (!result) return;
            await refreshAdminContentState();
            OJApp.renderShell?.();
            const kept = Number(result.deleted?.historical_submissions || 0);
            showNotice(
              kept > 0
                ? `题目 ${result.deleted.title} 已删除，保留了 ${kept} 条历史提交记录`
                : `题目 ${result.deleted.title} 已删除`,
              "success",
            );
          } catch (error) {
            showNotice(error.message, "error");
          } finally {
            button.disabled = false;
          }
        });
      });
    }

    if (viewState.tab === "public") {
      document.getElementById("publicContentForm")?.addEventListener("submit", async (event) => {
        event.preventDefault();
        const form = new FormData(event.currentTarget);
        const buttons = event.currentTarget.querySelectorAll("button[type='submit']");
        const payload = {
          announcement: form.get("announcement"),
          test_flow: String(form.get("test_flow") || "").split(/\r?\n/),
          tool_call_policy: {
            definition: form.get("tool_definition"),
            expectation: form.get("tool_expectation"),
            scoring: form.get("tool_scoring"),
          },
          output_format_markdown: form.get("output_format_markdown"),
        };
        buttons.forEach((button) => {
          button.disabled = true;
        });
        try {
          const content = await api("/api/admin/public-content", {
            method: "PATCH",
            body: JSON.stringify(payload),
          });
          state.config = content.config;
          state.cases = content.cases;
          state.testSets = Array.isArray(content.config?.test_sets) ? content.config.test_sets : [];
          state.testSetsLoadedAt = Date.now();
          await refreshLeaderboard?.({ rerenderShell: false });
          OJApp.renderShell?.();
          showNotice("公开内容已保存", "success");
        } catch (error) {
          showNotice(error.message, "error");
        } finally {
          buttons.forEach((button) => {
            button.disabled = false;
          });
        }
      });
    }

    if (viewState.tab === "users") {
      primeActiveAdminTab();

      document.getElementById("userForm")?.addEventListener("submit", async (event) => {
        event.preventDefault();
        const form = new FormData(event.currentTarget);
        const button = event.currentTarget.querySelector("button[type='submit']");
        button.disabled = true;
        try {
          await api("/api/admin/users", {
            method: "POST",
            body: JSON.stringify({
              username: form.get("username"),
              password: form.get("password"),
              role: form.get("role"),
            }),
          });
          event.currentTarget.reset();
          await ensureAdminUsers(true);
          renderAdmin();
          showNotice("账号已创建", "success");
        } catch (error) {
          showNotice(error.message, "error");
        } finally {
          button.disabled = false;
        }
      });

      mainView.querySelector("[data-admin-refresh-users]")?.addEventListener("click", async (event) => {
        const button = event.currentTarget;
        button.disabled = true;
        try {
          await ensureAdminUsers(true);
        } catch (error) {
          showNotice(error.message, "error");
        } finally {
          button.disabled = false;
        }
      });

      mainView.querySelectorAll("[data-save-password]").forEach((button) => {
        button.addEventListener("click", async () => {
          const row = button.closest("[data-admin-user]");
          const password = row.querySelector("[data-user-password]").value.trim();
          if (password.length < 8) {
            showNotice("密码至少 8 位", "error");
            return;
          }
          button.disabled = true;
          try {
            await api(`/api/admin/users/${row.dataset.adminUser}`, {
              method: "PATCH",
              body: JSON.stringify({ password }),
            });
            row.querySelector("[data-user-password]").value = "";
            showNotice("密码已更新", "success");
          } catch (error) {
            showNotice(error.message, "error");
          } finally {
            button.disabled = false;
          }
        });
      });

      mainView.querySelectorAll("[data-user-role]").forEach((select) => {
        select.addEventListener("change", async () => {
          const row = select.closest("[data-admin-user]");
          try {
            await api(`/api/admin/users/${row.dataset.adminUser}`, {
              method: "PATCH",
              body: JSON.stringify({ role: select.value }),
            });
            await ensureAdminUsers(true);
            showNotice("角色已更新", "success");
          } catch (error) {
            showNotice(error.message, "error");
          }
        });
      });

      mainView.querySelectorAll("[data-user-disabled]").forEach((select) => {
        select.addEventListener("change", async () => {
          const row = select.closest("[data-admin-user]");
          try {
            await api(`/api/admin/users/${row.dataset.adminUser}`, {
              method: "PATCH",
              body: JSON.stringify({ disabled: select.value === "1" }),
            });
            await ensureAdminUsers(true);
            showNotice("状态已更新", "success");
          } catch (error) {
            showNotice(error.message, "error");
          }
        });
      });

      mainView.querySelectorAll("[data-delete-user]").forEach((button) => {
        button.addEventListener("click", async () => {
          const row = button.closest("[data-admin-user]");
          const username = row.dataset.adminUsername || row.dataset.adminUser;
          const confirmed = confirmTwice(
            `确定要删除用户 ${username} 吗？这会同时删除该用户可删除状态下的提交记录。`,
            `最后确认一次：删除用户 ${username} 后无法恢复，是否继续？`,
          );
          if (!confirmed) return;
          button.disabled = true;
          try {
            const result = await api(`/api/admin/users/${row.dataset.adminUser}`, {
              method: "DELETE",
            });
            await ensureAdminUsers(true);
            showNotice(
              `用户 ${result.deleted.username} 已删除，同时删除了 ${result.deleted.deleted_submissions} 条提交`,
              "success",
            );
          } catch (error) {
            showNotice(error.message, "error");
          } finally {
            button.disabled = false;
          }
        });
      });
    }

    if (viewState.tab === "runtime") {
      primeActiveAdminTab();
      mainView.querySelector("[data-admin-refresh-runtime]")?.addEventListener("click", async (event) => {
        const button = event.currentTarget;
        button.disabled = true;
        try {
          await ensureAdminAgentStatus(true);
        } catch (error) {
          showNotice(error.message, "error");
        } finally {
          button.disabled = false;
        }
      });
    }
  }

  async function renderAdminCaseEditor(caseId) {
    if (state.user.role !== "admin") {
      document.getElementById("mainView").innerHTML = `<section class="empty">需要管理员权限</section>`;
      return;
    }
    const view = document.getElementById("mainView");
    let data;
    try {
      data = await api(`/api/admin/cases/${encodeURIComponent(caseId)}`);
    } catch (error) {
      view.innerHTML = `<section class="empty">${escapeHtml(error.message)}</section>`;
      return;
    }
    renderAdminCaseForm(view, "edit", data.case, data.files || {});
    const deleteButton = document.querySelector("[data-delete-case]");
    if (deleteButton) {
      deleteButton.addEventListener("click", async () => {
        deleteButton.disabled = true;
        try {
          const result = await deleteAdminCase(caseId, data.case?.title || caseId);
          if (!result) return;
          await refreshAdminContentState();
          const kept = Number(result.deleted?.historical_submissions || 0);
          routeWithNotice(
            "/admin",
            kept > 0
              ? `题目 ${result.deleted.title} 已删除，保留了 ${kept} 条历史提交记录`
              : `题目 ${result.deleted.title} 已删除`,
          );
        } catch (error) {
          showNotice(error.message, "error");
        } finally {
          deleteButton.disabled = false;
        }
      });
    }
    document.getElementById("adminCaseForm").addEventListener("submit", async (event) => {
      event.preventDefault();
      const button = event.currentTarget.querySelector("button[type='submit']");
      const form = new FormData(event.currentTarget);
      button.disabled = true;
      try {
        await api(`/api/admin/cases/${encodeURIComponent(caseId)}`, {
          method: "PATCH",
          body: JSON.stringify({
            case_json: form.get("case_json"),
            inject_script: form.get("inject_script"),
            recover_script: form.get("recover_script"),
            ideal_answer_json: form.get("ideal_answer_json"),
            rubrics_json: form.get("rubrics_json"),
          }),
        });
        await refreshAdminContentState();
        showNotice("题目五个文件已保存", "success");
        await renderAdminCaseEditor(caseId);
      } catch (error) {
        showNotice(error.message, "error");
      } finally {
        button.disabled = false;
      }
    });
  }

  async function renderAdminCaseCreator() {
    if (state.user.role !== "admin") {
      document.getElementById("mainView").innerHTML = `<section class="empty">需要管理员权限</section>`;
      return;
    }
    const view = document.getElementById("mainView");
    renderAdminCaseForm(view, "create", { id: "new-case-id", title: "新题目" }, newCaseTemplateFiles());
    bindCaseArchiveUpload(
      document.getElementById("caseArchiveUploadBtn"),
      document.getElementById("caseArchiveInput"),
      (created) => {
        routeWithNotice(
          `/admin/cases/${encodeURIComponent(created.case.id)}`,
          `题目 ${created.case.title || created.case.id} 已通过 ZIP 创建`,
        );
      },
    );
    document.getElementById("adminCaseForm").addEventListener("submit", async (event) => {
      event.preventDefault();
      const button = event.currentTarget.querySelector("button[type='submit']");
      const form = new FormData(event.currentTarget);
      button.disabled = true;
      try {
        const created = await api("/api/admin/cases", {
          method: "POST",
          body: JSON.stringify({
            case_json: form.get("case_json"),
            inject_script: form.get("inject_script"),
            recover_script: form.get("recover_script"),
            ideal_answer_json: form.get("ideal_answer_json"),
            rubrics_json: form.get("rubrics_json"),
          }),
        });
        await refreshAdminContentState();
        routeWithNotice(`/admin/cases/${encodeURIComponent(created.case.id)}`, "题目已创建");
      } catch (error) {
        showNotice(error.message, "error");
      } finally {
        button.disabled = false;
      }
    });
  }

  async function loadUsers(force = false) {
    return ensureAdminUsers(force);
  }

  async function loadAgentStatus(force = false) {
    return ensureAdminAgentStatus(force);
  }

  Object.assign(OJApp, {
    refreshAdminContentState,
    newCaseTemplateFiles,
    renderAdminCaseForm,
    renderAdmin,
    renderAdminCaseEditor,
    renderAdminCaseCreator,
    deleteAdminCase,
    uploadAdminCaseArchive,
    bindCaseArchiveUpload,
    adminSetTab,
    adminSetCasePage,
    adminRefreshUsers,
    adminRefreshRuntime,
    loadUsers,
    loadAgentStatus,
  });
})();
