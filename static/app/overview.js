(function () {
  const OJApp = window.OJApp;
  const { state, escapeHtml, routeTo, copyIconButton, bindCopyButtons } = OJApp;

  function renderOverview() {
    const view = document.getElementById("mainView");
    const config = state.config || {};
    const outputText = String(config.output_format_markdown || "").trim() || "暂无统一输出格式说明";
    const enabledCases = state.cases.filter((item) => item?.submission_enabled !== false).length;
    const visibleAnalysisCases = state.cases.filter((item) => item?.ai_analysis_visible !== false).length;
    const submissionMetric = state.submissionsLoadedAt ? String(state.submissionsTotal || 0) : "--";
    view.innerHTML = `
      <section class="panel overview-hero">
        <div class="overview-hero-copy">
          <span class="eyebrow">AIOps OJ</span>
          <h2>${escapeHtml(config.title || "AIOps 故障评测平台")}</h2>
          <p>${escapeHtml(config.overview || "")}</p>
        </div>
        <div class="overview-hero-side">
          <article class="overview-highlight">
            <span class="eyebrow">当前节奏</span>
            <strong>注入 → 答题 → 恢复 → 评分</strong>
            <p>题面只公开现象和必要背景，统一输出格式与评分规则集中在平台总览里维护。</p>
          </article>
          <div class="hero-actions">
            <button class="primary" data-route="/cases">进入题目</button>
            <button class="ghost" data-route="/submissions">查看提交</button>
          </div>
        </div>
      </section>

      <section class="metric-grid">
        <article class="metric-card">
          <span>测试用例</span>
          <strong>${escapeHtml(state.cases.length)}</strong>
        </article>
        <article class="metric-card">
          <span>提交记录</span>
          <strong>${escapeHtml(submissionMetric)}</strong>
        </article>
        <article class="metric-card">
          <span>开放提交</span>
          <strong>${escapeHtml(enabledCases)}</strong>
        </article>
        <article class="metric-card">
          <span>AI分析可见</span>
          <strong>${escapeHtml(visibleAnalysisCases)}</strong>
        </article>
        <article class="metric-card">
          <span>执行顺序</span>
          <strong>注入 -> 答题 -> 恢复 -> 评分</strong>
        </article>
      </section>

      <section class="panel announcement-panel">
        <div class="section-head">
          <div>
            <span class="eyebrow">Announcement</span>
            <h3>公告</h3>
          </div>
        </div>
        <p class="announcement-text ${config.announcement ? "" : "muted"}">${escapeHtml(config.announcement || "暂无公告")}</p>
      </section>

      <section class="grid two overview-grid">
        <article class="panel">
          <div class="section-head">
            <div>
              <span class="eyebrow">Flow</span>
              <h3>测试流程</h3>
            </div>
          </div>
          <ol class="flow-list">
            ${(config.test_flow || []).map((item) => `<li>${escapeHtml(item)}</li>`).join("")}
          </ol>
        </article>
        <article class="panel">
          <div class="section-head">
            <div>
              <span class="eyebrow">Policy</span>
              <h3>工具调用口径</h3>
            </div>
          </div>
          <dl class="kv compact-kv">
            <dt>定义</dt><dd>${escapeHtml(config.tool_call_policy?.definition || "")}</dd>
            <dt>要求</dt><dd>${escapeHtml(config.tool_call_policy?.expectation || "")}</dd>
            <dt>评分</dt><dd>${escapeHtml(config.tool_call_policy?.scoring || "")}</dd>
          </dl>
        </article>
      </section>

      <section class="panel copy-panel">
        <div class="section-head">
          <div>
            <span class="eyebrow">Format</span>
            <h3>统一输出格式</h3>
          </div>
          ${copyIconButton("outputText", "复制统一输出格式")}
        </div>
        <pre id="outputText" class="copy-box copy-document">${escapeHtml(outputText)}</pre>
      </section>
    `;
    view.querySelectorAll("[data-route]").forEach((button) => {
      button.addEventListener("click", () => routeTo(button.dataset.route));
    });
    bindCopyButtons(view);
  }

  Object.assign(OJApp, { renderOverview });
})();
