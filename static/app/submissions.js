import { api } from "./api.js";
import { copyIconButton, downloadIconButton, bindCopyButtons, bindDownloadButtons } from "./copy.js";
import { refreshLeaderboard, refreshSubmissions } from "./data.js";
import { showNotice } from "./notice.js";
import { routeTo } from "./router.js";
import { state } from "./state.js";
import {
  caseNavLabel,
  caseOrderText,
  compactTime,
  confirmTwice,
  escapeHtml,
  gradingResultText,
  processOutputText,
  renderLogLines,
  statusClass,
  statusText,
  submissionDurationText,
  verdictText,
} from "./utils.js";

let submissionRefreshTimer = 0;

function scheduleSubmissionRefresh(options = {}) {
  if (submissionRefreshTimer) window.clearTimeout(submissionRefreshTimer);
  const routeName = state.route.name;
  submissionRefreshTimer = window.setTimeout(() => {
    submissionRefreshTimer = 0;
    if (routeName !== "submissions" || state.route.name !== "submissions") return;
    if (state.submissionsLoadingPromise) return;
    refreshSubmissions(options).catch((error) => showNotice(error.message, "error"));
  }, 0);
}

  function closeDetailStream() {
    if (state.detailStreamAbort) {
      state.detailStreamAbort.abort();
      state.detailStreamAbort = null;
    }
    if (state.detailElapsedTimer) {
      clearInterval(state.detailElapsedTimer);
      state.detailElapsedTimer = null;
    }
    state.detailElapsedItem = null;
  }

  function testSetFilterOptions() {
    const optionsById = new Map();
    (Array.isArray(state.submissionTestSetFilters) ? state.submissionTestSetFilters : []).forEach((item) => {
      const testSetId = String(item?.test_set_id || item?.id || "").trim();
      const name = String(item?.name || testSetId).trim();
      if (!testSetId || !name) return;
      const numbers = Array.isArray(item?.case_numbers)
        ? item.case_numbers.map((caseNumber) => String(caseNumber || "").trim()).filter(Boolean)
        : [];
      optionsById.set(testSetId, {
        value: `testset:${testSetId}`,
        label: numbers.length ? `${name}（#${numbers.join("、")}）` : name,
        testSetId,
        displayName: "",
      });
    });
    (Array.isArray(state.testSets) ? state.testSets : []).forEach((testSet) => {
      const testSetId = String(testSet?.id || "").trim();
      const name = String(testSet?.name || testSet?.id || "").trim();
      if (!testSetId || !name || optionsById.has(testSetId)) return;
      const numbers = Array.isArray(testSet?.case_numbers) ? testSet.case_numbers : [];
      const numberText = numbers.map((caseNumber) => String(caseNumber || "").trim()).filter(Boolean);
      optionsById.set(testSetId, {
        value: `testset:${testSetId}`,
        label: numberText.length ? `${name}（#${numberText.join("、")}）` : name,
        testSetId,
        displayName: "",
      });
    });
    return Array.from(optionsById.values());
  }

  function isTrainingCaseFilterOption(item) {
    return !item?.case_set_id || item.case_set_id === "training";
  }

  function submissionVisibleCaseOptions() {
    return (Array.isArray(state.cases) ? state.cases : [])
      .filter(isTrainingCaseFilterOption)
      .map((item) => ({
        value: `case:${item.id}`,
        label: `${caseNavLabel(item)} · ${item.id}`,
      }));
  }

  function submissionCaseFilterValue() {
    const testSetId = String(state.submissionView.testSetId || "").trim();
    if (testSetId) return `testset:${testSetId}`;
    const displayCaseName = String(state.submissionView.displayCaseName || "").trim();
    if (displayCaseName) return `test:${displayCaseName}`;
    const caseId = String(state.submissionView.caseId || "").trim();
    return caseId ? `case:${caseId}` : "";
  }

  function renderSubmissionCaseFilterOptions() {
    const selectedValue = submissionCaseFilterValue();
    const caseOptions = submissionVisibleCaseOptions();
    const testOptions = testSetFilterOptions();
    return `
      <option value="">全部题目</option>
      ${caseOptions.map((item) => `
        <option value="${escapeHtml(item.value)}" ${selectedValue === item.value ? "selected" : ""}>${escapeHtml(item.label)}</option>
      `).join("")}
      ${testOptions.length ? `
        <optgroup label="测试集">
          ${testOptions.map((item) => `
            <option value="${escapeHtml(item.value)}" ${selectedValue === item.value ? "selected" : ""}>${escapeHtml(item.label)}</option>
          `).join("")}
        </optgroup>
      ` : ""}
    `;
  }

  function applySubmissionCaseFilter(value) {
    const raw = String(value || "").trim();
    state.submissionView.caseId = "";
    state.submissionView.displayCaseName = "";
    state.submissionView.testSetId = "";
    if (raw.startsWith("case:")) {
      state.submissionView.caseId = raw.slice(5).trim();
    } else if (raw.startsWith("testset:")) {
      state.submissionView.testSetId = raw.slice(8).trim();
    } else if (raw.startsWith("test:")) {
      state.submissionView.displayCaseName = raw.slice(5).trim();
    }
  }

  async function deleteSubmissionWithConfirm(item, options = {}) {
    const confirmed = confirmTwice(
      `确定要删除提交 #${item.id} 吗？`,
      `最后确认一次：删除提交 #${item.id} 后无法恢复，是否继续？`,
    );
    if (!confirmed) return false;
    await api(`/api/submissions/${item.id}`, { method: "DELETE" });
    showNotice(`提交 #${item.id} 已删除`, "success");
    closeDetailStream();
    await refreshSubmissions({ clearItems: true });
    refreshLeaderboard?.().catch(() => {});
    if (options.redirectToList) {
      routeTo("/submissions");
    }
    return true;
  }

  async function retrySubmissionWithConfirm(item) {
    const confirmed = confirmTwice(
      `确定要重测提交 #${item.id} 吗？`,
      `最后确认一次：将以用户 ${item.username} 当前最新的模型配置重新创建一条新提交，是否继续？`,
    );
    if (!confirmed) return false;
    const data = await api(`/api/admin/submissions/${item.id}/retry`, { method: "POST" });
    showNotice(`已创建重测提交 #${data.id}`, "success");
    closeDetailStream();
    try {
      await refreshSubmissions({ clearItems: true });
    } catch (error) {
      showNotice(error.message, "error");
    }
    return true;
  }

  function renderSubmissions() {
    document.getElementById("mainView").innerHTML = `
      <section class="page-title">
        <div>
          <span class="eyebrow">Submissions</span>
          <h2>提交记录</h2>
        </div>
        <button class="ghost" id="refreshBtn">刷新</button>
      </section>
      <section class="table-panel">
        <div class="submission-toolbar">
          <label>
            <span>用户名</span>
            <input id="submissionUserFilter" placeholder="按用户名筛选" value="${escapeHtml(state.submissionView.username)}" />
          </label>
          <label>
            <span>题目</span>
            <select id="submissionCaseFilter">
              ${renderSubmissionCaseFilterOptions()}
            </select>
          </label>
          <label>
            <span>排序字段</span>
            <select id="submissionSortBy">
              <option value="created_at" ${state.submissionView.sortBy === "created_at" ? "selected" : ""}>时间</option>
              <option value="score" ${state.submissionView.sortBy === "score" ? "selected" : ""}>分数</option>
            </select>
          </label>
          <label>
            <span>排序方向</span>
            <select id="submissionSortOrder">
              <option value="desc" ${state.submissionView.sortOrder === "desc" ? "selected" : ""}>降序</option>
              <option value="asc" ${state.submissionView.sortOrder === "asc" ? "selected" : ""}>升序</option>
            </select>
          </label>
          <label>
            <span>每页</span>
            <select id="submissionPerPage">
              ${[20, 50, 100].map((size) => `
                <option value="${size}" ${Number(state.submissionView.perPage) === size ? "selected" : ""}>${size} 条</option>
              `).join("")}
            </select>
          </label>
          <div class="submit-actions submission-toolbar-actions">
            <button type="button" class="ghost slim" id="resetSubmissionFilters">重置</button>
          </div>
        </div>
        <div id="submissionTableMeta" class="submission-toolbar-meta"></div>
        <div id="submissionTableWrap" data-submission-table></div>
      </section>
    `;
    document.getElementById("refreshBtn").addEventListener("click", () => {
      refreshSubmissions({ clearItems: true }).catch((error) => showNotice(error.message, "error"));
    });
    bindSubmissionToolbar();
    renderSubmissionTable();
    scheduleSubmissionRefresh({ clearItems: !state.submissions.length });
  }

  function bindSubmissionToolbar() {
    let inputTimer = null;
    const syncStateFromControls = () => {
      state.submissionView.username = document.getElementById("submissionUserFilter")?.value || "";
      applySubmissionCaseFilter(document.getElementById("submissionCaseFilter")?.value || "");
      state.submissionView.sortBy = document.getElementById("submissionSortBy")?.value || "created_at";
      state.submissionView.sortOrder = document.getElementById("submissionSortOrder")?.value || "desc";
      state.submissionView.perPage = Number(document.getElementById("submissionPerPage")?.value || 20) || 20;
    };
    const submitFilters = (options = {}) => {
      syncStateFromControls();
      refreshSubmissions({
        page: options.resetPage ? 1 : state.submissionView.page,
        perPage: state.submissionView.perPage,
        clearItems: true,
      }).catch((error) => showNotice(error.message, "error"));
    };
    document.getElementById("submissionUserFilter")?.addEventListener("input", () => {
      clearTimeout(inputTimer);
      inputTimer = setTimeout(() => submitFilters({ resetPage: true }), 250);
    });
    document.getElementById("submissionCaseFilter")?.addEventListener("change", () => submitFilters({ resetPage: true }));
    document.getElementById("submissionSortBy")?.addEventListener("change", () => submitFilters({ resetPage: true }));
    document.getElementById("submissionSortOrder")?.addEventListener("change", () => submitFilters({ resetPage: true }));
    document.getElementById("submissionPerPage")?.addEventListener("change", () => submitFilters({ resetPage: true }));
    document.getElementById("resetSubmissionFilters")?.addEventListener("click", () => {
      state.submissionView = {
        username: "",
        caseId: "",
        displayCaseName: "",
        testSetId: "",
        sortBy: "created_at",
        sortOrder: "desc",
        page: 1,
        perPage: 20,
      };
      renderSubmissions();
    });
  }

  function renderSubmissionTable() {
    const wrap = document.getElementById("submissionTableWrap");
    const meta = document.getElementById("submissionTableMeta");
    if (!wrap) return;
    const items = state.submissions.slice();
    const total = Number(state.submissionsTotal) || 0;
    const totalPages = Math.max(1, Number(state.submissionsTotalPages) || 1);
    const page = Math.min(Math.max(1, Number(state.submissionView.page) || 1), totalPages);
    const perPage = Math.max(1, Number(state.submissionView.perPage) || 20);
    const start = total ? ((page - 1) * perPage) + 1 : 0;
    const end = total ? start + items.length - 1 : 0;
    if (meta) {
      if (state.submissionsLoadingPromise && !items.length) meta.textContent = `正在加载第 ${page} 页...`;
      else if (!total) meta.textContent = "共 0 条提交。";
      else meta.textContent = `第 ${page} / ${totalPages} 页，当前显示 ${start}-${end} 条，共 ${total} 条。`;
    }
    if (!items.length) {
      wrap.innerHTML = state.submissionsLoadingPromise
        ? `<div class="empty">正在加载提交记录...</div>`
        : `<div class="empty">暂无提交</div>`;
      return;
    }
    wrap.innerHTML = `
      <table class="submissions">
        <thead>
          <tr>
            <th>ID</th>
            <th>Model</th>
            <th>用户</th>
            <th>题目</th>
            <th>状态</th>
            <th>分数</th>
            <th>结论</th>
            <th>Runtime</th>
            <th>创建时间</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          ${items.map((item) => {
            const actionButtons = [];
            const caseLabel = submissionCaseLabel(item);
            if (item.can_retry) actionButtons.push(`<button type="button" class="ghost slim" data-retry-submission="${escapeHtml(item.id)}">重测</button>`);
            if (item.can_delete) actionButtons.push(`<button type="button" class="ghost slim" data-delete-submission="${escapeHtml(item.id)}">删除</button>`);
            return `
            <tr class="${item.can_view_content ? "clickable" : ""}" data-submission="${item.can_view_content ? item.id : ""}">
              <td>#${escapeHtml(item.id)}</td>
              <td>${escapeHtml(item.model || "-")}</td>
              <td>${escapeHtml(item.username)}</td>
              <td>${escapeHtml(caseLabel)}</td>
              <td><span class="status ${statusClass(item.status)}">${statusText(item.status)}</span></td>
              <td>${item.score == null ? "-" : escapeHtml(item.score)}</td>
              <td>${escapeHtml(verdictText(item.score))}</td>
              <td>${escapeHtml(submissionDurationText(item))}</td>
              <td>${escapeHtml(compactTime(item.created_at))}</td>
              <td>
                <div class="submit-actions">
                  ${actionButtons.length ? actionButtons.join("") : `<span class="muted">-</span>`}
                </div>
              </td>
            </tr>
          `;
          }).join("")}
        </tbody>
      </table>
      <div class="submission-pagination">
        <div class="submission-pagination-info">第 ${page} / ${totalPages} 页</div>
        <div class="submit-actions submission-pagination-actions">
          <button type="button" class="ghost slim" data-submission-page="1" ${page <= 1 || state.submissionsLoadingPromise ? "disabled" : ""}>首页</button>
          <button type="button" class="ghost slim" data-submission-page="${Math.max(1, page - 1)}" ${page <= 1 || state.submissionsLoadingPromise ? "disabled" : ""}>上一页</button>
          <button type="button" class="ghost slim" data-submission-page="${Math.min(totalPages, page + 1)}" ${page >= totalPages || state.submissionsLoadingPromise ? "disabled" : ""}>下一页</button>
          <button type="button" class="ghost slim" data-submission-page="${totalPages}" ${page >= totalPages || state.submissionsLoadingPromise ? "disabled" : ""}>末页</button>
        </div>
      </div>
    `;
    wrap.querySelectorAll("[data-submission]").forEach((row) => {
      if (!row.dataset.submission) return;
      row.addEventListener("click", () => routeTo(`/submissions/${row.dataset.submission}`));
    });
    wrap.querySelectorAll("[data-submission-page]").forEach((button) => {
      button.addEventListener("click", () => {
        const nextPage = Number(button.dataset.submissionPage);
        if (!Number.isFinite(nextPage) || nextPage === page) return;
        refreshSubmissions({ page: nextPage, clearItems: true }).catch((error) => showNotice(error.message, "error"));
      });
    });
    wrap.querySelectorAll("[data-delete-submission]").forEach((button) => {
      button.addEventListener("click", async (event) => {
        event.stopPropagation();
        const item = items.find((entry) => String(entry.id) === button.dataset.deleteSubmission);
        if (!item) return;
        button.disabled = true;
        try {
          await deleteSubmissionWithConfirm(item);
        } catch (error) {
          showNotice(error.message, "error");
        } finally {
          button.disabled = false;
        }
      });
    });
    wrap.querySelectorAll("[data-retry-submission]").forEach((button) => {
      button.addEventListener("click", async (event) => {
        event.stopPropagation();
        const item = items.find((entry) => String(entry.id) === button.dataset.retrySubmission);
        if (!item) return;
        button.disabled = true;
        try {
          await retrySubmissionWithConfirm(item);
        } catch (error) {
          showNotice(error.message, "error");
        } finally {
          button.disabled = false;
        }
      });
    });
  }

  function cachedSubmissionById(id) {
    const submissionId = Number(id);
    if (!Number.isFinite(submissionId)) return null;
    return state.submissions.find((item) => Number(item.id) === submissionId) || null;
  }

  function caseConfigById(caseId) {
    return state.cases.find((item) => item.id === caseId) || null;
  }

  function submissionCaseLabel(item) {
    if (item?.source_kind === "test_set") {
      return item.display_case_name || item.test_set_name || "测试集";
    }
    const caseItem = caseConfigById(item?.case_id);
    return caseItem ? caseNavLabel(caseItem) : item.case_name;
  }

  function caseForSubmission(item) {
    return item?.case || caseConfigById(item?.case_id) || null;
  }

  function submissionMcpEntries(item) {
    if (Array.isArray(item?.answer_mcp_server_labels) && item.answer_mcp_server_labels.length) {
      return item.answer_mcp_server_labels.map((entry) => ({
        id: entry.id,
        label: entry.label || entry.id,
      }));
    }
    const selectedIds = Array.isArray(item?.answer_mcp_servers) ? item.answer_mcp_servers : [];
    const available = Array.isArray(state.config?.available_mcp_servers) ? state.config.available_mcp_servers : [];
    const labelMap = new Map(
      available.map((entry) => [String(entry.id || "").trim(), entry.label || entry.id || ""])
    );
    return selectedIds.map((id) => ({
      id,
      label: labelMap.get(id) || id,
    }));
  }

  function shouldStreamSubmission(item) {
    return !["done", "failed"].includes(item?.status);
  }

  function renderSubmissionDetailShell(view, id) {
    view.innerHTML = `
      <div id="submissionDetailRoot" data-submission-id="${escapeHtml(id)}">
        <section class="page-title">
          <div>
            <span class="eyebrow" id="detailEyebrow">Submission #${escapeHtml(id)}</span>
            <div id="detailCaseMeta" class="case-state-tags inline"></div>
            <h2 id="detailTitle">正在加载提交详情...</h2>
          </div>
          <div class="submit-actions" id="detailActions">
            <button class="ghost" data-route="/submissions">返回记录</button>
          </div>
        </section>

        <section class="detail-head">
          <div><span>状态</span><strong id="detailStatus" class="status queued">加载中</strong></div>
          <div><span>分数</span><strong id="detailScore">-</strong></div>
          <div><span>结论</span><strong id="detailVerdict">-</strong></div>
          <div><span id="detailQueueLabel">Elapsed</span><strong id="detailQueue">-</strong></div>
        </section>

        <div id="detailErrorSlot"></div>

        <section class="grid two detail-grid">
          <article class="panel submission-info-panel">
            <h3>提交信息</h3>
            <dl class="kv">
              <dt>Base URL</dt><dd id="detailBaseUrl">-</dd>
              <dt>Model</dt><dd id="detailModel">-</dd>
              <dt>AI Analysis</dt><dd id="detailAiVisibility">-</dd>
              <dt>创建时间</dt><dd id="detailCreated">-</dd>
              <dt>开始时间</dt><dd id="detailStarted">-</dd>
              <dt>结束时间</dt><dd id="detailFinished">-</dd>
            </dl>
            <div class="submission-info-scroll">
              <h4>Prompt</h4>
              <div id="detailPrompt" class="text-box prompt-box">正在加载...</div>
              <div id="detailMcpWrap" hidden>
                <h4>MCP</h4>
                <div id="detailMcp" class="text-box skill-box"></div>
              </div>
              <div id="detailSkillWrap" hidden>
                <h4>Skill</h4>
                <div id="detailSkill" class="text-box skill-box"></div>
              </div>
            </div>
          </article>
          <article class="panel live-panel rich-live">
            <div class="section-head">
              <div>
                <span class="eyebrow">Live</span>
                <h3>测评过程</h3>
              </div>
              <span id="detailRunStatus" class="status queued">加载中</span>
            </div>
            <div class="log-toolbar">
              <span>实时输出</span>
              <button type="button" class="ghost slim" id="scrollLogBottom">跳到底部</button>
            </div>
            <div id="runLogScroll" class="log-scroll">
              <div id="runLogLines">${renderLogLines("")}</div>
            </div>
          </article>
        </section>

        <section class="grid two output-grid" id="finalOutputs" hidden>
          <article class="panel">
            <div class="section-head">
              <h3>Agent 故障诊断输出</h3>
              <div class="submit-actions">
                ${copyIconButton("answerOutput", "复制 Agent 故障诊断输出")}
                ${downloadIconButton(`answerOutput`, `submission-${id}-agent-diagnosis.md`, "下载 Agent 故障诊断输出 Markdown")}
              </div>
            </div>
            <textarea id="answerOutput" class="output-box fixed-output" readonly rows="16"></textarea>
          </article>
          <article class="panel">
            <div class="section-head">
              <h3>Agent 调用过程和工具结果</h3>
              <div class="submit-actions">
                ${copyIconButton("processOutput", "复制 Agent 调用过程和工具结果")}
                ${downloadIconButton(`processOutput`, `submission-${id}-agent-process.md`, "下载 Agent 调用过程和工具结果 Markdown")}
              </div>
            </div>
            <textarea id="processOutput" class="output-box fixed-output" readonly rows="18"></textarea>
          </article>
          <article class="panel output-wide" id="gradeOutputPanel">
            <div class="section-head">
              <h3>AI 分析</h3>
              <div class="submit-actions">
                ${copyIconButton("gradeOutput", "复制 AI 分析")}
                ${downloadIconButton(`gradeOutput`, `submission-${id}-ai-analysis.md`, "下载 AI 分析 Markdown")}
              </div>
            </div>
            <pre id="gradeOutput" class="output-box grade-output-document"></pre>
          </article>
        </section>
      </div>
    `;
    view.querySelectorAll("[data-route]").forEach((button) => {
      button.addEventListener("click", () => routeTo(button.dataset.route));
    });
    document.getElementById("scrollLogBottom").addEventListener("click", () => {
      const logScroll = document.getElementById("runLogScroll");
      if (logScroll) logScroll.scrollTop = logScroll.scrollHeight;
    });
    bindCopyButtons(view);
    bindDownloadButtons(view);
  }

  function syncDetailElapsed(item = state.detailElapsedItem) {
    const valueEl = document.getElementById("detailQueue");
    const labelEl = document.getElementById("detailQueueLabel");
    if (!valueEl || !labelEl || !item) return;
    labelEl.textContent = item?.finished_at ? "Runtime" : "Elapsed";
    valueEl.textContent = submissionDurationText(item);
  }

  function updateDetailElapsedClock(item) {
    state.detailElapsedItem = item;
    syncDetailElapsed(item);
    const running = !!(item?.started_at && !item?.finished_at);
    if (running && !state.detailElapsedTimer) {
      state.detailElapsedTimer = setInterval(() => syncDetailElapsed(), 1000);
    }
    if (!running && state.detailElapsedTimer) {
      clearInterval(state.detailElapsedTimer);
      state.detailElapsedTimer = null;
    }
  }

  function bindDetailDeleteAction(item) {
    const actions = document.getElementById("detailActions");
    if (!actions) return;
    actions.innerHTML = `
      ${item.can_delete ? `<button type="button" class="ghost" id="detailDeleteBtn">删除提交</button>` : ""}
      <button class="ghost" data-route="/submissions">返回记录</button>
    `;
    actions.querySelectorAll("[data-route]").forEach((button) => {
      button.addEventListener("click", () => routeTo(button.dataset.route));
    });
    const deleteBtn = document.getElementById("detailDeleteBtn");
    if (!deleteBtn) return;
    deleteBtn.addEventListener("click", async () => {
      deleteBtn.disabled = true;
      try {
        await deleteSubmissionWithConfirm(item, { redirectToList: true });
      } catch (error) {
        showNotice(error.message, "error");
      } finally {
        deleteBtn.disabled = false;
      }
    });
  }

  function updateSubmissionDetailView(item) {
    const root = document.getElementById("submissionDetailRoot");
    if (!root) return;
    if (root.dataset.submissionId && String(item?.id || "") !== root.dataset.submissionId) return;

    const setText = (id, value) => {
      const el = document.getElementById(id);
      if (!el) return;
      if (el.tagName === "TEXTAREA") el.value = value ?? "-";
      else el.textContent = value ?? "-";
    };
    const setStatus = (id, status) => {
      const el = document.getElementById(id);
      if (!el) return;
      el.className = `status ${statusClass(status)}`;
      el.textContent = statusText(status);
    };

    bindDetailDeleteAction(item);
    const caseItem = caseForSubmission(item);
    const orderPrefix = caseItem?.order_id ? `${caseOrderText(caseItem)} · ` : "";
    const aiVisible = item?.can_view_ai_analysis !== false;
    const titleText = item?.source_kind === "test_set"
      ? (item.display_case_name || item.test_set_name || "测试集")
      : `${orderPrefix}${caseItem?.title || item.case_name || item.case_id}`;
    setText("detailEyebrow", `Submission #${item.id} · ${item.username}`);
    setText("detailTitle", titleText);
    setStatus("detailStatus", item.status);
    setText("detailScore", item.score == null ? "-" : item.score);
    setText("detailVerdict", verdictText(item.score));
    setText("detailBaseUrl", item.api_base_url || "-");
    setText("detailModel", item.model);
    setText("detailAiVisibility", aiVisible ? "可见" : "隐藏");
    setText("detailCreated", compactTime(item.created_at));
    setText("detailStarted", compactTime(item.started_at));
    setText("detailFinished", compactTime(item.finished_at));
    updateDetailElapsedClock(item);
    setText("detailPrompt", item.prompt || "");
    setStatus("detailRunStatus", item.status);

    const caseMeta = document.getElementById("detailCaseMeta");
    if (caseMeta) {
      caseMeta.innerHTML = `
        ${item?.source_kind === "test_set" ? `<span class="status queued">${escapeHtml(item.test_set_name || "测试集")}</span>` : ""}
        <span class="status ${caseItem?.submission_enabled !== false ? "ok" : "bad"}">${caseItem?.submission_enabled !== false ? "选手可提交" : "选手不可提交"}</span>
        <span class="status ${aiVisible ? "ok" : "queued"}">${aiVisible ? "AI分析可见" : "AI分析隐藏"}</span>
      `;
    }

    const errorSlot = document.getElementById("detailErrorSlot");
    if (errorSlot) {
      errorSlot.innerHTML = item.error ? `<section class="notice error always">${escapeHtml(item.error)}</section>` : "";
    }

    const mcpWrap = document.getElementById("detailMcpWrap");
    const mcpBox = document.getElementById("detailMcp");
    if (mcpWrap && mcpBox) {
      const mcpEntries = submissionMcpEntries(item);
      mcpWrap.hidden = false;
      mcpBox.textContent = mcpEntries.length
        ? mcpEntries.map((entry) => `${entry.label} (${entry.id})`).join("\n")
        : "本次提交未附带 MCP";
    }

    const skillWrap = document.getElementById("detailSkillWrap");
    const skillBox = document.getElementById("detailSkill");
    if (skillWrap && skillBox) {
      const skillSummary = [];
      if (Array.isArray(item.skill_names) && item.skill_names.length) {
        skillSummary.push(`Attached skills: ${item.skill_names.join(", ")}`);
      }
      if (item.skill) skillSummary.push(item.skill);
      skillWrap.hidden = !skillSummary.length;
      skillBox.textContent = skillSummary.join("\n\n");
    }

    const logScroll = document.getElementById("runLogScroll");
    const logLines = document.getElementById("runLogLines");
    if (logScroll && logLines) {
      const nearBottom = logScroll.scrollTop + logScroll.clientHeight >= logScroll.scrollHeight - 32;
      const previousTop = logScroll.scrollTop;
      logLines.innerHTML = renderLogLines(item.run_log || "");
      logScroll.scrollTop = nearBottom ? logScroll.scrollHeight : previousTop;
    }

    const answerText = item.answer_output || "本次没有生成故障诊断输出。";
    const processText = processOutputText(item) || "本次没有记录到工具调用过程。";
    const gradeText = gradingResultText(item) || "本次没有生成 AI 分析。";
    const canViewAiAnalysis = item.can_view_ai_analysis !== false;
    const outputGrid = document.getElementById("finalOutputs");
    const gradePanel = document.getElementById("gradeOutputPanel");
    const showOutputs = Boolean(
      item.answer_output || item.answer_process || item.grade_output || item.grade_json || ["done", "failed"].includes(item.status)
    );
    if (outputGrid) outputGrid.hidden = !showOutputs;
    if (gradePanel) gradePanel.hidden = !canViewAiAnalysis;
    setText("answerOutput", answerText);
    setText("processOutput", processText);
    setText("gradeOutput", canViewAiAnalysis ? gradeText : "");
  }

  async function updateSubmissionDetail(id) {
    const root = document.getElementById("submissionDetailRoot");
    if (!root || root.dataset.submissionId !== String(id)) return renderSubmissionDetail(id);
    const data = await api(`/api/submissions/${id}`);
    updateSubmissionDetailView(data.submission);
  }

  function startSubmissionStream(id) {
    closeDetailStream();
    const controller = new AbortController();
    state.detailStreamAbort = controller;
    fetch(`/api/submissions/${id}/stream`, {
      headers: {
        Authorization: `Bearer ${state.token}`,
      },
      signal: controller.signal,
    }).then(async (response) => {
      if (!response.ok || !response.body) throw new Error(`HTTP ${response.status}`);
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() || "";
        lines.forEach((line) => {
          if (!line.trim()) return;
          const payload = JSON.parse(line);
          updateSubmissionDetailView(payload.submission);
        });
      }
    }).catch(() => {
      if (controller.signal.aborted) return;
      updateSubmissionDetail(id).catch(() => {});
    }).finally(() => {
      if (state.detailStreamAbort === controller) state.detailStreamAbort = null;
    });
  }

  async function renderSubmissionDetail(id) {
    const view = document.getElementById("mainView");
    if (!view) return;
    renderSubmissionDetailShell(view, id);
    const cachedItem = cachedSubmissionById(id);
    if (cachedItem) {
      updateSubmissionDetailView({
        ...cachedItem,
        case: null,
        prompt: "",
        skill: "",
        run_log: "",
        answer_output: "",
        grade_output: "",
        grade_json: "",
        answer_process: "",
        grade_process: "",
        error: "",
        can_view_ai_analysis: state.user?.role === "admin" || caseConfigById(cachedItem.case_id)?.ai_analysis_visible !== false,
      });
    }
    let item;
    try {
      const data = await api(`/api/submissions/${id}`);
      item = data.submission;
    } catch (error) {
      if (!cachedItem) view.innerHTML = `<section class="empty">${escapeHtml(error.message)}</section>`;
      else showNotice(error.message, "error");
      return;
    }
    updateSubmissionDetailView(item);
    if (shouldStreamSubmission(item)) startSubmissionStream(id);
  }

export {
  closeDetailStream,
  deleteSubmissionWithConfirm,
  retrySubmissionWithConfirm,
  renderSubmissions,
  bindSubmissionToolbar,
  renderSubmissionTable,
  syncDetailElapsed,
  updateDetailElapsedClock,
  updateSubmissionDetailView,
  updateSubmissionDetail,
  startSubmissionStream,
  renderSubmissionDetail,
};
