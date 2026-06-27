(function () {
  const OJApp = window.OJApp;
  const {
    state,
    escapeHtml,
    routeTo,
    compactTime,
    readSubmissionDraft,
    writeSubmissionDraft,
    clearSubmissionDraft,
    caseOrderText,
    copyIconButton,
    bindCopyButtons,
    currentSkills,
    renderSkillManagerSection,
    bindSkillManager,
    currentSoulMarkdown,
    renderSoulEditorSection,
    bindSoulEditor,
    showNotice,
    refreshSubmissions,
    refreshTestSets,
    api,
  } = OJApp;

  const TEST_SET_PLACEHOLDER_HELP_TEXT = "成员题面现已公开；Prompt 中仍可使用 {{fault_phenomenon}} 表示每道题的故障现象，使用 {{public_case_info}} 表示每道题的公开信息。生成真实提交时，平台会分别替换为对应题目的内容。";
  const TEST_SET_PLACEHOLDER_HELP_HTML = "成员题面现已公开；Prompt 中仍可使用 <code>{{fault_phenomenon}}</code> 表示每道题的故障现象，使用 <code>{{public_case_info}}</code> 表示每道题的公开信息。生成真实提交时，平台会分别替换为对应题目的内容。";

  function caseById(id) {
    return state.cases.find((item) => item.id === id) || null;
  }

  function caseHasDetails(item) {
    return !!item
      && Object.prototype.hasOwnProperty.call(item, "fault_phenomenon")
      && Object.prototype.hasOwnProperty.call(item, "public_case_info");
  }

  function mergeCaseDetail(caseItem) {
    if (!caseItem?.id) return caseItem;
    const index = state.cases.findIndex((item) => item.id === caseItem.id);
    if (index >= 0) {
      state.cases[index] = { ...state.cases[index], ...caseItem };
    } else {
      state.cases.push(caseItem);
    }
    return state.cases.find((item) => item.id === caseItem.id) || caseItem;
  }

  async function loadCaseDetail(caseId) {
    const data = await api(`/api/cases/${encodeURIComponent(caseId)}`);
    return mergeCaseDetail(data);
  }

  function isTrainingCase(item) {
    return !item?.case_set_id || item.case_set_id === "training";
  }

  function testSetById(id) {
    return (Array.isArray(state.testSets) ? state.testSets : []).find((item) => item.id === id) || null;
  }

  function testSetCaseNumbers(item) {
    return Array.isArray(item?.case_numbers)
      ? item.case_numbers.map((caseNumber) => String(caseNumber || "").trim()).filter(Boolean)
      : [];
  }

  function testSetMembers(item) {
    return (Array.isArray(state.cases) ? state.cases : [])
      .filter((caseItem) => caseItem?.case_set_id === item?.id)
      .sort((left, right) => (Number(left?.order_id) || 0) - (Number(right?.order_id) || 0));
  }

  function renderTestSetMembers(item) {
    const members = testSetMembers(item);
    if (!members.length) return renderTestSetCaseNumbers(item);
    return `
      <div class="test-set-members" aria-label="${escapeHtml(item?.name || "测试集")}成员题目">
        ${members.map((caseItem) => `
          <button type="button" class="test-set-member-row" data-case-route="/cases/${encodeURIComponent(caseItem.id)}">
            <span class="test-set-member-number">#${escapeHtml(caseItem.order_id)}</span>
            <span class="test-set-member-title">${escapeHtml(caseItem.title || caseItem.id)}</span>
            <code>${escapeHtml(caseItem.id)}</code>
          </button>
        `).join("")}
      </div>
    `;
  }

  function renderTestSetCaseNumbers(item) {
    const caseNumbers = testSetCaseNumbers(item);
    if (!caseNumbers.length) {
      return `<div class="test-set-case-numbers muted">暂无题目编号</div>`;
    }
    return `
      <div class="test-set-case-numbers" aria-label="测试集题目编号">
        <span>题目编号</span>
        ${caseNumbers.map((caseNumber) => `<code>${escapeHtml(caseNumber)}</code>`).join("")}
      </div>
    `;
  }

  function availableMcpServers() {
    const items = Array.isArray(state.config?.available_mcp_servers) ? state.config.available_mcp_servers : [];
    return items
      .map((item) => ({
        id: String(item?.id || "").trim(),
        label: String(item?.label || item?.id || "").trim(),
      }))
      .filter((item, index, list) => item.id && list.findIndex((entry) => entry.id === item.id) === index);
  }

  function renderMcpSelectionSection(selectedIds = []) {
    const options = availableMcpServers();
    const selected = Array.isArray(selectedIds) ? selectedIds : options.map((item) => item.id);
    return `
      <section class="panel form-panel">
        <div class="section-head">
          <div>
            <span class="eyebrow">MCP</span>
            <h3>本次提交启用的 MCP</h3>
          </div>
        </div>
        <p class="muted">默认全选。你可以按本次提交自由勾选，运行时只会加载勾选的 MCP。</p>
        <div class="mcp-selection-grid" id="submissionMcpSelection">
          ${options.map((item) => `
            <label class="checkbox-card">
              <input
                type="checkbox"
                name="mcp_server_ids"
                value="${escapeHtml(item.id)}"
                ${selected.includes(item.id) ? "checked" : ""}
              />
              <span>
                <strong>${escapeHtml(item.label)}</strong>
                <small>${escapeHtml(item.id)}</small>
              </span>
            </label>
          `).join("")}
        </div>
      </section>
    `;
  }

  function contestantSubmissionLocked(caseItem) {
    return state.user?.role !== "admin" && caseItem?.submission_enabled === false;
  }

  function submissionDisabledReason(caseItem, profile = state.profile || {}) {
    if (contestantSubmissionLocked(caseItem)) {
      return "当前题目已关闭选手提交，只有管理员可以提交";
    }
    if (!profile?.configured) {
      return "请先在个人配置中保存答题模型配置";
    }
    if (!profile?.grader_configured) {
      return "平台评分服务当前不可用，请联系管理员";
    }
    return "";
  }

  function caseAvailabilityClass(caseItem, surface = "card") {
    const enabled = caseItem?.submission_enabled !== false;
    if (surface === "sidebar") return enabled ? "is-open" : "is-closed";
    return enabled ? "case-open" : "case-closed";
  }

  function caseStateBadges(caseItem, options = {}) {
    const submissionEnabled = caseItem?.submission_enabled !== false;
    const aiAnalysisVisible = caseItem?.ai_analysis_visible !== false;
    const compact = !!options.compact;
    return [
      {
        text: compact
          ? (submissionEnabled ? "可提交" : "不可提交")
          : (submissionEnabled ? "选手可提交" : "选手不可提交"),
        className: submissionEnabled ? "ok" : "bad",
      },
      {
        text: compact
          ? (aiAnalysisVisible ? "AI分析可见" : "AI分析隐藏")
          : (aiAnalysisVisible ? "可查看 AI 分析" : "不可查看 AI 分析"),
        className: aiAnalysisVisible ? "ok" : "queued",
      },
    ];
  }

  function renderCaseStateBadges(caseItem, extraClass = "", options = {}) {
    return `
      <div class="case-state-tags ${escapeHtml(extraClass)}">
        ${caseStateBadges(caseItem, options).map((badge) => `
          <span class="status ${escapeHtml(badge.className)}">${escapeHtml(badge.text)}</span>
        `).join("")}
      </div>
    `;
  }

  function caseStateSummaryText(caseItem) {
    const submissionEnabled = caseItem?.submission_enabled !== false;
    const aiAnalysisVisible = caseItem?.ai_analysis_visible !== false;
    return `${submissionEnabled ? "可提交" : "不可提交"} · ${aiAnalysisVisible ? "AI分析可见" : "AI分析隐藏"}`;
  }

  function renderSidebarCaseSummary(caseItem) {
    return `<div class="case-state-summary ${escapeHtml(caseAvailabilityClass(caseItem, "sidebar"))}">${escapeHtml(caseStateSummaryText(caseItem))}</div>`;
  }

  function currentCasePage() {
    const perPage = Math.max(1, Number(state.caseView?.perPage) || 20);
    const totalPages = Math.max(1, Math.ceil(trainingCases().length / perPage));
    const page = Math.min(Math.max(1, Number(state.caseView?.page) || 1), totalPages);
    state.caseView.page = page;
    return page;
  }

  function trainingCases() {
    return (Array.isArray(state.cases) ? state.cases : []).filter(isTrainingCase);
  }

  function renderCasesList() {
    const view = document.getElementById("mainView");
    const cases = trainingCases();
    const enabledCases = cases.filter((item) => item?.submission_enabled !== false).length;
    const visibleAnalysisCases = cases.filter((item) => item?.ai_analysis_visible !== false).length;
    const perPage = Math.max(1, Number(state.caseView?.perPage) || 20);
    const total = cases.length;
    const totalPages = Math.max(1, Math.ceil(total / perPage));
    const page = currentCasePage();
    const startIndex = (page - 1) * perPage;
    const items = cases.slice(startIndex, startIndex + perPage);
    const start = total ? startIndex + 1 : 0;
    const end = total ? startIndex + items.length : 0;
    view.innerHTML = `
      <section class="page-title cases-hero">
        <div>
          <span class="eyebrow">Cases</span>
          <h2>题目列表</h2>
          <p>点击题目卡片即可查看题面，提交按钮会直接带你进入该题的提交区域。</p>
        </div>
        <div class="cases-hero-summary">
          <span>开放提交</span>
          <strong>${escapeHtml(enabledCases)} / ${escapeHtml(cases.length)}</strong>
          <small>AI 分析可见 ${escapeHtml(visibleAnalysisCases)} 题</small>
        </div>
      </section>
      <section class="panel case-list-panel">
        <div class="submission-toolbar-meta">第 ${escapeHtml(page)} / ${escapeHtml(totalPages)} 页，当前显示 ${escapeHtml(start)}-${escapeHtml(end)} 条，共 ${escapeHtml(total)} 题。</div>
        <div class="case-grid case-list">
          ${items.map((item) => {
            const locked = contestantSubmissionLocked(item);
            const hasBestScore = item?.personal_best_score != null && item?.personal_best_score !== "";
            return `
              <article class="case-card case-list-card ${escapeHtml(caseAvailabilityClass(item))}" data-route="/cases/${encodeURIComponent(item.id)}">
                <div class="case-list-main">
                  <div class="case-card-top">
                    <div class="case-meta">
                      <span>${escapeHtml(`${caseOrderText(item)} · ${item.id}`)}</span>
                    </div>
                    ${renderCaseStateBadges(item, "", { compact: true })}
                  </div>
                  <div class="case-list-title-wrap">
                    <h3>${escapeHtml(item.title)}</h3>
                    ${hasBestScore ? `<span class="case-best-score">最高分 ${escapeHtml(item.personal_best_score)}</span>` : ""}
                  </div>
                </div>
                <div class="card-actions case-list-actions">
                  <button class="primary" type="button" data-submit-route="/submit/${encodeURIComponent(item.id)}" ${locked ? "disabled" : ""}>提交测评</button>
                </div>
              </article>
            `;
          }).join("")}
        </div>
        <div class="submission-pagination">
          <div class="submission-pagination-info">第 ${page} / ${totalPages} 页</div>
          <div class="submit-actions submission-pagination-actions">
            <button type="button" class="ghost slim" data-case-page="1" ${page <= 1 ? "disabled" : ""}>首页</button>
            <button type="button" class="ghost slim" data-case-page="${Math.max(1, page - 1)}" ${page <= 1 ? "disabled" : ""}>上一页</button>
            <button type="button" class="ghost slim" data-case-page="${Math.min(totalPages, page + 1)}" ${page >= totalPages ? "disabled" : ""}>下一页</button>
            <button type="button" class="ghost slim" data-case-page="${totalPages}" ${page >= totalPages ? "disabled" : ""}>末页</button>
          </div>
        </div>
      </section>
    `;
    view.querySelectorAll("[data-route]").forEach((card) => {
      card.addEventListener("click", () => routeTo(card.dataset.route));
    });
    view.querySelectorAll("[data-submit-route]").forEach((button) => {
      button.addEventListener("click", (event) => {
        event.stopPropagation();
        routeTo(button.dataset.submitRoute);
      });
    });
    view.querySelectorAll("[data-case-page]").forEach((button) => {
      button.addEventListener("click", () => {
        const nextPage = Number(button.dataset.casePage);
        if (!Number.isFinite(nextPage) || nextPage === state.caseView.page) return;
        state.caseView.page = nextPage;
        renderCasesList();
      });
    });
  }

  function renderTestSets() {
    const view = document.getElementById("mainView");
    const items = Array.isArray(state.testSets) ? state.testSets.slice() : [];
    view.innerHTML = `
      <section class="page-title cases-hero">
        <div>
          <span class="eyebrow">Test Sets</span>
          <h2>测试题目</h2>
          <p>测试题目按题目族提交，系统会自动生成多条独立测评记录。</p>
        </div>
      </section>
      <section class="panel case-list-panel">
        <div class="case-grid case-list">
          ${items.length ? items.map((item) => {
            const submissionEnabled = item?.submission_enabled !== false;
            const contestantLocked = state.user?.role !== "admin" && !submissionEnabled;
            return `
            <article class="case-card case-list-card ${submissionEnabled ? "case-open" : "case-closed"}">
              <div class="case-list-main">
                <div class="case-card-top">
                  <div class="case-meta">
                    <span>TEST SET</span>
                  </div>
                  <div class="case-state-tags">
                    <span class="status ${submissionEnabled ? "ok" : "bad"}">${submissionEnabled ? "可提交" : "不可提交"}</span>
                  </div>
                </div>
                <div class="case-list-title-wrap">
                  <h3>${escapeHtml(item.name || item.id)}</h3>
                </div>
                ${renderTestSetMembers(item)}
              </div>
              <div class="card-actions case-list-actions">
                <button class="primary" type="button" ${contestantLocked ? "disabled" : `data-route="/test-sets/${encodeURIComponent(item.id)}/submit"`}>${contestantLocked ? "暂不可提交" : "提交测评"}</button>
              </div>
            </article>
          `;
          }).join("") : `<section class="empty compact-empty">当前没有测试题目</section>`}
        </div>
      </section>
    `;
    view.querySelectorAll("[data-route]").forEach((el) => {
      el.addEventListener("click", () => routeTo(el.dataset.route));
    });
    view.querySelectorAll("[data-case-route]").forEach((el) => {
      el.addEventListener("click", () => routeTo(el.dataset.caseRoute));
    });
    refreshTestSets?.({ rerender: false }).catch((error) => showNotice(error.message, "error"));
  }

  function renderCaseDetail(caseId) {
    const caseItem = caseById(caseId);
    const view = document.getElementById("mainView");
    if (!caseItem) {
      view.innerHTML = `<section class="empty">测试用例不存在</section>`;
      return;
    }
    if (!caseHasDetails(caseItem)) {
      view.innerHTML = `
        <section class="page-title">
          <div>
            <span class="eyebrow">Case ${escapeHtml(caseOrderText(caseItem))} · ${escapeHtml(caseItem.id)}</span>
            <h2>${escapeHtml(caseItem.title || caseItem.id)}</h2>
          </div>
        </section>
        <section class="empty">正在加载题目详情...</section>
      `;
      loadCaseDetail(caseId).then(() => {
        if (state.route.name === "case" && state.route.params.id === caseId) renderCaseDetail(caseId);
        if (state.route.name === "submit" && state.route.params.id === caseId) renderSubmit(caseId);
      }).catch((error) => {
        view.innerHTML = `<section class="empty">${escapeHtml(error.message)}</section>`;
      });
      return;
    }
    const memberTestSet = testSetById(caseItem.case_set_id);
    const contestantTestSetMember = !!memberTestSet && state.user?.role !== "admin";
    view.innerHTML = `
      <section class="page-title">
        <div>
          <span class="eyebrow">Case ${escapeHtml(caseOrderText(caseItem))} · ${escapeHtml(caseItem.id)}</span>
          <h2>${escapeHtml(caseItem.title)}</h2>
          ${renderCaseStateBadges(caseItem, "inline")}
        </div>
        ${contestantTestSetMember ? `
          <div class="submit-actions">
            <button type="button" class="ghost" data-route="/test-sets">返回测试题目</button>
            <button type="button" class="primary" data-route="/test-sets/${encodeURIComponent(memberTestSet.id)}/submit" ${memberTestSet.submission_enabled === false ? "disabled" : ""}>提交题目族</button>
          </div>
        ` : ""}
      </section>

      <section class="fault-band">
        <span>故障现象</span>
        <p>${escapeHtml(caseItem.fault_phenomenon)}</p>
      </section>

      <section class="panel case-public-info">
        <div class="section-head">
          <div>
            <span class="eyebrow">Public Info</span>
            <h3>题目公开信息</h3>
          </div>
          ${copyIconButton("casePublicInfo", "复制题目公开信息")}
        </div>
        <p id="casePublicInfo">${escapeHtml(caseItem.public_case_info || "")}</p>
      </section>

      ${contestantTestSetMember ? `
        <section class="notice always">
          <strong>${escapeHtml(memberTestSet.name || memberTestSet.id)}</strong> 中的成员题只能通过题目族入口统一提交。
        </section>
      ` : renderSubmissionForm(caseItem)}
    `;
    bindCasePageActions(view, caseItem);
  }

  function renderSubmissionForm(caseItem) {
    const profile = state.profile || {};
    const disabledReason = submissionDisabledReason(caseItem, profile);
    const submissionLocked = contestantSubmissionLocked(caseItem);
    const ready = !disabledReason;
    const maxSkills = state.config?.max_skills || 10;
    const maxSkillChars = state.config?.max_skill_chars || 100000;
    const maxSoulChars = state.config?.max_soul_chars || 100000;
    const maxArchiveBytes = state.config?.max_skill_archive_bytes || 10 * 1024 * 1024;
    return `
      <form id="submissionForm" class="submit-layout embedded-submit">
        <section class="panel form-panel">
          <h3>选手提示词</h3>
          <label>
            <span>Prompt</span>
            <textarea name="prompt" rows="12" required></textarea>
          </label>
          <p class="muted draft-hint" id="submissionDraftHint">草稿会自动保存在当前浏览器，翻页回来还能继续写。</p>
          ${submissionLocked ? `<section class="notice error always">当前题目已关闭选手提交，只有管理员可以继续提交。</section>` : ""}
        </section>

        ${renderSoulEditorSection({
          idPrefix: "submission",
          profile,
          maxChars: maxSoulChars,
          title: "提交 SOUL.md",
          description: "可以直接在提交页编辑个人 SOUL.md。保存后会永久生效；留空表示使用平台默认 SOUL.md。",
          saveButtonLabel: "保存 SOUL.md 到个人配置",
          rows: 14,
        })}

        ${renderMcpSelectionSection()}

        ${renderSkillManagerSection({
          idPrefix: "submission",
          profile,
          title: "提交 Skill",
          maxSkills,
          maxSkillChars,
          maxArchiveBytes,
          includeSelection: true,
          description: "可以直接在提交页维护个人 Skill。保存后会永久生效；本次只会附带你勾选的 Skill。",
          saveButtonLabel: "保存 Skill 到个人配置",
        })}

        <section class="panel form-panel">
          <div class="submit-actions">
            <button type="button" class="ghost" data-route="/profile">去个人配置页</button>
            <button type="button" class="ghost" data-route="/overview">查看说明</button>
            ${ready ? `
              <button type="submit" class="primary">加入队列</button>
            ` : `
              <span class="button-tooltip" title="${escapeHtml(disabledReason)}" aria-label="${escapeHtml(disabledReason)}">
                <button type="submit" class="primary" disabled>加入队列</button>
              </span>
            `}
          </div>
        </section>
      </form>
    `;
  }

  function contestantTestSetSubmissionLocked(testSet) {
    return state.user?.role !== "admin" && testSet?.submission_enabled === false;
  }

  function testSetSubmissionDisabledReason(testSet, profile = state.profile || {}) {
    if (contestantTestSetSubmissionLocked(testSet)) {
      return "当前测试集已关闭选手提交，只有管理员可以提交";
    }
    if (!profile?.configured) {
      return "请先在个人配置中保存答题模型配置";
    }
    if (!profile?.grader_configured) {
      return "平台评分服务当前不可用，请联系管理员";
    }
    return "";
  }

  function renderTestSetSubmissionForm(testSet) {
    const profile = state.profile || {};
    const disabledReason = testSetSubmissionDisabledReason(testSet, profile);
    const submissionLocked = contestantTestSetSubmissionLocked(testSet);
    const ready = !disabledReason;
    const maxSkills = state.config?.max_skills || 10;
    const maxSkillChars = state.config?.max_skill_chars || 100000;
    const maxSoulChars = state.config?.max_soul_chars || 100000;
    const maxArchiveBytes = state.config?.max_skill_archive_bytes || 10 * 1024 * 1024;
    return `
      <form id="testSetSubmissionForm" class="submit-layout embedded-submit">
        <section class="panel form-panel">
          <h3>选手提示词</h3>
          <label>
            <span>Prompt</span>
            <textarea name="prompt" rows="12" required></textarea>
          </label>
          <p class="muted draft-hint" id="submissionDraftHint">${TEST_SET_PLACEHOLDER_HELP_HTML}</p>
          ${submissionLocked ? `<section class="notice error always">当前测试集已关闭选手提交，只有管理员可以继续提交。</section>` : ""}
        </section>

        ${renderSoulEditorSection({
          idPrefix: "submission",
          profile,
          maxChars: maxSoulChars,
          title: "提交 SOUL.md",
          description: "可以直接在提交页编辑个人 SOUL.md。保存后会永久生效；留空表示使用平台默认 SOUL.md。",
          saveButtonLabel: "保存 SOUL.md 到个人配置",
          rows: 14,
        })}

        ${renderMcpSelectionSection()}

        ${renderSkillManagerSection({
          idPrefix: "submission",
          profile,
          title: "提交 Skill",
          maxSkills,
          maxSkillChars,
          maxArchiveBytes,
          includeSelection: true,
          description: "可以直接在提交页维护个人 Skill。保存后会永久生效；本次只会附带你勾选的 Skill。",
          saveButtonLabel: "保存 Skill 到个人配置",
        })}

        <section class="panel form-panel">
          <div class="submit-actions">
            <button type="button" class="ghost" data-route="/test-sets">返回测试题目</button>
            <button type="button" class="ghost" data-route="/profile">去个人配置页</button>
            ${ready ? `
              <button type="submit" class="primary">加入队列</button>
            ` : `
              <span class="button-tooltip" title="${escapeHtml(disabledReason)}" aria-label="${escapeHtml(disabledReason)}">
                <button type="submit" class="primary" disabled>加入队列</button>
              </span>
            `}
          </div>
        </section>
      </form>
    `;
  }

  function bindSubmissionForm(view, caseItem) {
    const formEl = view.querySelector("#submissionForm");
    if (!formEl) return;
    const disabledReason = submissionDisabledReason(caseItem, state.profile || {});
    const submitButton = formEl.querySelector("button[type='submit']");
    const promptInput = formEl.querySelector("textarea[name='prompt']");
    const draftHint = formEl.querySelector("#submissionDraftHint");
    if (submitButton) {
      submitButton.disabled = !!disabledReason;
      if (disabledReason) submitButton.setAttribute("aria-label", disabledReason);
    }
    view.querySelectorAll("[data-route]").forEach((button) => {
      button.addEventListener("click", () => routeTo(button.dataset.route));
    });

    const updateDraftHint = (savedAt) => {
      if (!draftHint) return;
      draftHint.textContent = savedAt
        ? `草稿已保存在当前浏览器 · ${compactTime(savedAt)}`
        : "草稿会自动保存在当前浏览器，翻页回来还能继续写。";
    };

    const draft = readSubmissionDraft(caseItem.id);
    const defaultSelectedIds = draft.selected_skill_ids?.length
      ? draft.selected_skill_ids
      : currentSkills(state.profile).map((skill) => skill.id);
    const defaultMcpIds = draft.has_selected_mcp_servers
      ? draft.selected_mcp_servers
      : availableMcpServers().map((item) => item.id);
    let skillManager = null;
    let soulEditor = null;

    const selectedMcpServers = () => Array.from(
      formEl.querySelectorAll("input[name='mcp_server_ids']:checked"),
    ).map((input) => String(input.value || "").trim()).filter(Boolean);

    const saveDraft = () => {
      const savedAt = writeSubmissionDraft(caseItem.id, {
        prompt: promptInput?.value || "",
        selected_skill_ids: skillManager ? skillManager.getSelectedIds() : defaultSelectedIds,
        selected_mcp_servers: selectedMcpServers(),
        soul_md: soulEditor ? soulEditor.readValue() : currentSoulMarkdown(state.profile),
      });
      updateDraftHint(savedAt);
    };

    if (promptInput && draft.prompt) promptInput.value = draft.prompt;
    formEl.querySelectorAll("input[name='mcp_server_ids']").forEach((input) => {
      input.checked = defaultMcpIds.includes(String(input.value || "").trim());
      input.addEventListener("change", saveDraft);
    });
    updateDraftHint(draft.saved_at);

    soulEditor = bindSoulEditor({
      idPrefix: "submission",
      maxChars: state.config?.max_soul_chars || 100000,
      initialValue: draft.saved_at ? draft.soul_md : undefined,
      saveButtonLabel: "保存 SOUL.md 到个人配置",
      saveSuccessMessage: "个人 SOUL.md 已保存，本次提交会自动使用最新配置。",
      noticeText: "个人 SOUL.md 已保存",
      onInputChange: () => saveDraft(),
      onProfileUpdated: () => saveDraft(),
    });

    skillManager = bindSkillManager({
      idPrefix: "submission",
      includeSelection: true,
      maxSkills: state.config?.max_skills || 10,
      maxArchiveBytes: state.config?.max_skill_archive_bytes || 10 * 1024 * 1024,
      initialSelectedIds: defaultSelectedIds,
      saveButtonLabel: "保存 Skill 到个人配置",
      saveSuccessMessage: "个人 Skill 已保存，本次勾选会继续保留。",
      noticeText: "个人 Skill 已保存",
      onSelectionChange: () => saveDraft(),
      onProfileUpdated: () => saveDraft(),
    });

    promptInput?.addEventListener("input", saveDraft);
    promptInput?.addEventListener("change", saveDraft);

    formEl.addEventListener("submit", async (event) => {
      event.preventDefault();
      if (disabledReason) {
        showNotice(disabledReason, "error");
        return;
      }
      const form = new FormData(event.currentTarget);
      const button = event.currentTarget.querySelector("button[type='submit']");
      button.disabled = true;
      try {
        if (soulEditor?.saveSoul) {
          await soulEditor.saveSoul({
            messageText: "正在保存当前 SOUL.md...",
            silentSuccess: true,
            noticeText: "",
          });
        }
        if (skillManager?.saveSkills) {
          await skillManager.saveSkills({
            messageText: "正在保存当前 Skill 配置...",
            silentSuccess: true,
            noticeText: "",
          });
        }
        const data = await api("/api/submissions", {
          method: "POST",
          body: JSON.stringify({
            case_id: caseItem.id,
            prompt: form.get("prompt"),
            mcp_servers: selectedMcpServers(),
            skill_ids: skillManager ? skillManager.getSelectedIds() : [],
          }),
        });
        clearSubmissionDraft(caseItem.id);
        updateDraftHint("");
        await refreshSubmissions();
        routeTo(`/submissions/${data.id}`);
      } catch (error) {
        showNotice(error.message, "error");
      } finally {
        button.disabled = false;
      }
    });
  }

  function bindTestSetSubmissionForm(view, testSet) {
    const formEl = view.querySelector("#testSetSubmissionForm");
    if (!formEl) return;
    const disabledReason = testSetSubmissionDisabledReason(testSet, state.profile || {});
    const submitButton = formEl.querySelector("button[type='submit']");
    const promptInput = formEl.querySelector("textarea[name='prompt']");
    const draftHint = formEl.querySelector("#submissionDraftHint");
    if (submitButton) {
      submitButton.disabled = !!disabledReason;
      if (disabledReason) submitButton.setAttribute("aria-label", disabledReason);
    }
    view.querySelectorAll("[data-route]").forEach((button) => {
      button.addEventListener("click", () => routeTo(button.dataset.route));
    });

    const draftKey = `test-set:${testSet.id}`;
    const updateDraftHint = (savedAt) => {
      if (!draftHint) return;
      draftHint.textContent = savedAt
        ? `草稿已保存在当前浏览器 · ${compactTime(savedAt)}`
        : TEST_SET_PLACEHOLDER_HELP_TEXT;
    };

    const draft = readSubmissionDraft(draftKey);
    const defaultSelectedIds = draft.selected_skill_ids?.length
      ? draft.selected_skill_ids
      : currentSkills(state.profile).map((skill) => skill.id);
    const defaultMcpIds = draft.has_selected_mcp_servers
      ? draft.selected_mcp_servers
      : availableMcpServers().map((item) => item.id);
    let skillManager = null;
    let soulEditor = null;

    const selectedMcpServers = () => Array.from(
      formEl.querySelectorAll("input[name='mcp_server_ids']:checked"),
    ).map((input) => String(input.value || "").trim()).filter(Boolean);

    const saveDraft = () => {
      const savedAt = writeSubmissionDraft(draftKey, {
        prompt: promptInput?.value || "",
        selected_skill_ids: skillManager ? skillManager.getSelectedIds() : defaultSelectedIds,
        selected_mcp_servers: selectedMcpServers(),
        soul_md: soulEditor ? soulEditor.readValue() : currentSoulMarkdown(state.profile),
      });
      updateDraftHint(savedAt);
    };

    if (promptInput && draft.prompt) promptInput.value = draft.prompt;
    formEl.querySelectorAll("input[name='mcp_server_ids']").forEach((input) => {
      input.checked = defaultMcpIds.includes(String(input.value || "").trim());
      input.addEventListener("change", saveDraft);
    });
    updateDraftHint(draft.saved_at);

    soulEditor = bindSoulEditor({
      idPrefix: "submission",
      maxChars: state.config?.max_soul_chars || 100000,
      initialValue: draft.saved_at ? draft.soul_md : undefined,
      saveButtonLabel: "保存 SOUL.md 到个人配置",
      saveSuccessMessage: "个人 SOUL.md 已保存，本次提交会自动使用最新配置。",
      noticeText: "个人 SOUL.md 已保存",
      onInputChange: () => saveDraft(),
      onProfileUpdated: () => saveDraft(),
    });

    skillManager = bindSkillManager({
      idPrefix: "submission",
      includeSelection: true,
      maxSkills: state.config?.max_skills || 10,
      maxArchiveBytes: state.config?.max_skill_archive_bytes || 10 * 1024 * 1024,
      initialSelectedIds: defaultSelectedIds,
      saveButtonLabel: "保存 Skill 到个人配置",
      saveSuccessMessage: "个人 Skill 已保存，本次勾选会继续保留。",
      noticeText: "个人 Skill 已保存",
      onSelectionChange: () => saveDraft(),
      onProfileUpdated: () => saveDraft(),
    });

    promptInput?.addEventListener("input", saveDraft);
    promptInput?.addEventListener("change", saveDraft);

    formEl.addEventListener("submit", async (event) => {
      event.preventDefault();
      if (disabledReason) {
        showNotice(disabledReason, "error");
        return;
      }
      const form = new FormData(event.currentTarget);
      const button = event.currentTarget.querySelector("button[type='submit']");
      button.disabled = true;
      try {
        if (soulEditor?.saveSoul) {
          await soulEditor.saveSoul({
            messageText: "正在保存当前 SOUL.md...",
            silentSuccess: true,
            noticeText: "",
          });
        }
        if (skillManager?.saveSkills) {
          await skillManager.saveSkills({
            messageText: "正在保存当前 Skill 配置...",
            silentSuccess: true,
            noticeText: "",
          });
        }
        await api(`/api/test-sets/${encodeURIComponent(testSet.id)}/submissions`, {
          method: "POST",
          body: JSON.stringify({
            prompt: form.get("prompt"),
            mcp_servers: selectedMcpServers(),
            skill_ids: skillManager ? skillManager.getSelectedIds() : [],
          }),
        });
        clearSubmissionDraft(draftKey);
        await refreshSubmissions({ resetPage: true, clearItems: true });
        showNotice("测试题目已加入队列", "success");
        routeTo("/submissions");
      } catch (error) {
        showNotice(error.message, "error");
      } finally {
        button.disabled = false;
      }
    });
  }

  function bindCasePageActions(view, caseItem) {
    view.querySelectorAll("[data-route]").forEach((button) => {
      button.addEventListener("click", () => routeTo(button.dataset.route));
    });
    bindCopyButtons(view);
    bindSubmissionForm(view, caseItem);
  }

  function renderSubmit(caseId) {
    renderCaseDetail(caseId);
    setTimeout(() => {
      document.getElementById("submissionForm")?.scrollIntoView({ behavior: "smooth", block: "start" });
    }, 0);
  }

  function renderTestSetSubmit(testSetId) {
    const testSet = testSetById(testSetId);
    const view = document.getElementById("mainView");
    if (!testSet) {
      view.innerHTML = `<section class="empty">测试题目不存在</section>`;
      refreshTestSets?.({ rerender: true }).catch((error) => showNotice(error.message, "error"));
      return;
    }
    view.innerHTML = `
      <section class="page-title">
        <div>
          <span class="eyebrow">Test Set</span>
          <h2>${escapeHtml(testSet.name || testSet.id)}</h2>
          <p>提交后会生成该测试题目下的独立测评记录，你可以查看自己每条提交的完整过程和 AI 分析。${TEST_SET_PLACEHOLDER_HELP_TEXT}</p>
        </div>
      </section>
      ${renderTestSetSubmissionForm(testSet)}
    `;
    bindTestSetSubmissionForm(view, testSet);
  }

  Object.assign(OJApp, {
    caseById,
    isTrainingCase,
    testSetById,
    caseAvailabilityClass,
    caseStateBadges,
    renderCaseStateBadges,
    caseStateSummaryText,
    renderSidebarCaseSummary,
    renderCasesList,
    renderTestSets,
    renderCaseDetail,
    loadCaseDetail,
    renderSubmissionForm,
    bindSubmissionForm,
    bindTestSetSubmissionForm,
    bindCasePageActions,
    renderSubmit,
    renderTestSetSubmit,
  });
})();
