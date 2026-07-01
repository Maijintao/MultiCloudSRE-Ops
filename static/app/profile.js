import { api } from "./api.js";
import { showNotice } from "./notice.js";
import { routeTo } from "./router.js";
import { currentSkills, renderSkillManagerSection, bindSkillManager } from "./skills.js";
import { currentSoulMarkdown, renderSoulEditorSection, bindSoulEditor } from "./soul.js";
import { state } from "./state.js";
import { escapeHtml } from "./utils.js";

  function renderProfile() {
    const profile = state.profile || {};
    const configured = !!profile.configured;
    const graderConfigured = !!profile.grader_configured;
    const skills = currentSkills(profile);
    const soulMd = currentSoulMarkdown(profile);
    const maxSkills = state.config?.max_skills || 10;
    const maxSkillChars = state.config?.max_skill_chars || 100000;
    const maxSoulChars = state.config?.max_soul_chars || 100000;
    const maxArchiveBytes = state.config?.max_skill_archive_bytes || (10 * 1024 * 1024);
    const view = document.getElementById("mainView");
    view.innerHTML = `
      <section class="page-title">
        <div>
          <span class="eyebrow">Profile</span>
          <h2>个人配置</h2>
        </div>
      </section>

      <section class="profile-layout">
        <form id="profileForm" class="panel form-panel">
          <div class="section-head">
            <div>
              <span class="eyebrow">LLM</span>
              <h3>模型接入</h3>
            </div>
            <span class="status ${configured ? "ok" : "queued"}">${configured ? "已配置" : "未配置"}</span>
          </div>
          <label>
            <span>Base URL</span>
            <input name="base_url" placeholder="https://api.example.com/v1" value="${escapeHtml(profile.api_base_url || "")}" required />
          </label>
          <label>
            <span>Model</span>
            <input name="model" placeholder="${escapeHtml(profile.default_model || "gpt-4o-mini")}" value="${escapeHtml(profile.model || "")}" required />
          </label>
          <label>
            <span>API Key</span>
            <input name="api_key" type="password" autocomplete="off" placeholder="${configured ? "留空保持当前密钥" : "请输入 API Key"}" ${configured ? "" : "required"} />
          </label>
          <div class="submit-actions">
            <button type="button" class="ghost" data-route="/overview">返回</button>
            <button type="button" class="ghost" id="checkModelBtn">检查模型</button>
            <button type="submit" class="primary">保存配置</button>
          </div>
          <p id="modelCheckMessage" class="form-message"></p>
        </form>

        <article class="panel">
          <h3>当前状态</h3>
          <dl class="kv">
            <dt>Base URL</dt><dd>${escapeHtml(profile.api_base_url || "-")}</dd>
            <dt>Model</dt><dd>${escapeHtml(profile.model || "-")}</dd>
            <dt>API Key</dt><dd>${escapeHtml(profile.api_key_mask || "-")}</dd>
            <dt>个人 Skill</dt><dd>${skills.length ? `${skills.length} 个` : "未配置"}</dd>
            <dt>SOUL.md</dt><dd>${soulMd.trim() ? "已自定义" : "使用默认"}</dd>
          </dl>
        </article>

        <article class="panel form-panel">
          <div class="section-head">
            <div>
              <span class="eyebrow">Scoring API</span>
              <h3>评分 API</h3>
            </div>
            <span class="status ${graderConfigured ? "ok" : "bad"}">${graderConfigured ? "平台托管" : "平台未就绪"}</span>
          </div>
          <p class="muted">评分 API 由平台统一管理，选手无需也不能单独修改。</p>
          <dl class="kv compact-kv">
            <dt>来源</dt><dd>${escapeHtml(profile.platform_grader_label || "平台统一评分 API")}</dd>
            <dt>Base URL</dt><dd>${escapeHtml(profile.grader_base_url || "not configured")}</dd>
            <dt>Model</dt><dd>${escapeHtml(profile.grader_model || "not configured")}</dd>
            <dt>API Key</dt><dd>${escapeHtml(profile.grader_api_key_mask || "-")}</dd>
          </dl>
          <p class="form-message ${graderConfigured ? "success-message" : ""}">
            ${escapeHtml(graderConfigured ? "当前平台评分配置可用，提交会自动使用这套评分服务。" : "平台评分服务当前不可用，请联系管理员。")}
          </p>
        </article>
      </section>

      ${renderSoulEditorSection({
        idPrefix: "profile",
        profile,
        maxChars: maxSoulChars,
        title: "个人 SOUL.md",
        description: "这里填写的 SOUL.md 会永久保存。留空表示使用平台默认 SOUL.md。",
        saveButtonLabel: "保存个人 SOUL.md",
      })}

      ${renderSkillManagerSection({
        idPrefix: "profile",
        profile,
        title: "个人 Skill",
        maxSkills,
        maxSkillChars,
        maxArchiveBytes,
        description: "这里配置的 Skill 会永久保存。文本 Skill 和 ZIP Skill 都可以在提交页直接复用。",
        saveButtonLabel: "保存个人 Skill",
      })}
    `;

    view.querySelectorAll("[data-route]").forEach((button) => {
      button.addEventListener("click", () => routeTo(button.dataset.route));
    });

    document.getElementById("checkModelBtn").addEventListener("click", async (event) => {
      const button = event.currentTarget;
      const form = new FormData(document.getElementById("profileForm"));
      const message = document.getElementById("modelCheckMessage");
      button.disabled = true;
      message.textContent = "正在检查模型配置...";
      message.className = "form-message muted-message";
      try {
        const data = await api("/api/profile/check", {
          method: "POST",
          body: JSON.stringify({
            base_url: form.get("base_url"),
            model: form.get("model"),
            api_key: form.get("api_key"),
          }),
        });
        message.textContent = data.message || (data.ok ? "模型可用" : "模型不可用");
        message.className = `form-message ${data.ok ? "success-message" : ""}`;
      } catch (error) {
        message.textContent = error.message;
        message.className = "form-message";
      } finally {
        button.disabled = false;
      }
    });

    document.getElementById("profileForm").addEventListener("submit", async (event) => {
      event.preventDefault();
      const form = new FormData(event.currentTarget);
      const button = event.currentTarget.querySelector("button[type='submit']");
      const message = document.getElementById("modelCheckMessage");
      button.disabled = true;
      message.textContent = "正在检查并保存模型配置...";
      message.className = "form-message muted-message";
      try {
        const data = await api("/api/profile", {
          method: "PATCH",
          body: JSON.stringify({
            base_url: form.get("base_url"),
            model: form.get("model"),
            api_key: form.get("api_key"),
          }),
        });
        state.profile = data.profile;
        if (state.user) state.user.profile_configured = data.profile.configured;
        showNotice("模型配置已保存", "success");
        renderProfile();
      } catch (error) {
        message.textContent = error.message;
        message.className = "form-message";
        showNotice(error.message, "error");
      } finally {
        button.disabled = false;
      }
    });

    bindSoulEditor({
      idPrefix: "profile",
      maxChars: maxSoulChars,
      saveButtonLabel: "保存个人 SOUL.md",
      saveSuccessMessage: "个人 SOUL.md 已保存。",
      noticeText: "个人 SOUL.md 已保存",
      onProfileUpdated: () => renderProfile(),
    });

    bindSkillManager({
      idPrefix: "profile",
      maxSkills,
      maxArchiveBytes,
      saveButtonLabel: "保存个人 Skill",
      saveSuccessMessage: "个人 Skill 已保存。",
      noticeText: "个人 Skill 已保存",
      onProfileUpdated: () => renderProfile(),
    });
  }

export { renderProfile };
