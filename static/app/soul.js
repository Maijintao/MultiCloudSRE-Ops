(function () {
  const OJApp = window.OJApp;
  const { state, escapeHtml, showNotice, api, syncSubmissionDraftSouls } = OJApp;

  function currentSoulMarkdown(profile = state.profile) {
    return typeof profile?.soul_md === "string" ? profile.soul_md : "";
  }

  function soulConfigured(text) {
    return String(text || "").trim().length > 0;
  }

  function renderSoulEditorSection(options = {}) {
    const prefix = options.idPrefix || "shared";
    const maxChars = Number(options.maxChars || state.config?.max_soul_chars || 100000) || 100000;
    const value = typeof options.value === "string" ? options.value : currentSoulMarkdown(options.profile);
    const configured = soulConfigured(value);
    const description = options.description || "留空表示使用平台默认 SOUL.md。保存后会永久生效。";
    return `
      <section id="${prefix}SoulEditor" class="panel form-panel">
        <div class="section-head">
          <div>
            <span class="eyebrow">SOUL</span>
            <h3>${escapeHtml(options.title || "SOUL.md")}</h3>
          </div>
          <span class="status ${configured ? "ok" : "queued"}" id="${prefix}SoulStatus">${configured ? "已自定义" : "使用默认"}</span>
        </div>
        <p class="muted">${escapeHtml(description)}</p>
        <label>
          <span>SOUL.md</span>
          <textarea id="${prefix}SoulInput" rows="${Number(options.rows || 12)}" maxlength="${maxChars}" placeholder="留空表示使用平台默认 SOUL.md">${escapeHtml(value)}</textarea>
        </label>
        <div class="submit-actions">
          <button type="button" class="ghost" id="${prefix}ClearSoulBtn">恢复默认</button>
          <button type="button" class="primary" id="${prefix}SaveSoulBtn">${escapeHtml(options.saveButtonLabel || "保存 SOUL.md")}</button>
        </div>
        <p class="muted" id="${prefix}SoulCount">${value.length}/${maxChars}</p>
        <p id="${prefix}SoulMessage" class="form-message"></p>
      </section>
    `;
  }

  function bindSoulEditor(options = {}) {
    const prefix = options.idPrefix || "shared";
    const maxChars = Number(options.maxChars || state.config?.max_soul_chars || 100000) || 100000;
    const textarea = document.getElementById(`${prefix}SoulInput`);
    const saveBtn = document.getElementById(`${prefix}SaveSoulBtn`);
    const clearBtn = document.getElementById(`${prefix}ClearSoulBtn`);
    const countEl = document.getElementById(`${prefix}SoulCount`);
    const statusEl = document.getElementById(`${prefix}SoulStatus`);
    const messageEl = document.getElementById(`${prefix}SoulMessage`);
    if (!textarea || !saveBtn || !clearBtn || !countEl || !statusEl || !messageEl) return null;

    let savePromise = null;

    const setMessage = (text = "", kind = "") => {
      messageEl.textContent = text;
      messageEl.className = kind ? `form-message ${kind}` : "form-message";
    };

    const readValue = () => String(textarea.value || "").replace(/\r\n/g, "\n").replace(/\r/g, "\n");
    const savedValue = () => String(currentSoulMarkdown() || "").replace(/\r\n/g, "\n").replace(/\r/g, "\n");
    const hasUnsavedChanges = () => readValue() !== savedValue();

    const syncMeta = () => {
      const value = readValue();
      countEl.textContent = `${value.length}/${maxChars}`;
      const configured = soulConfigured(value);
      statusEl.textContent = configured ? "已自定义" : "使用默认";
      statusEl.className = `status ${configured ? "ok" : "queued"}`;
    };

    const notifyInputChange = () => {
      if (typeof options.onInputChange === "function") options.onInputChange(readValue());
    };

    const refreshFromProfile = (nextValue) => {
      textarea.value = typeof nextValue === "string" ? nextValue : currentSoulMarkdown();
      syncMeta();
      setMessage();
    };

    const saveSoul = async (saveOptions = {}) => {
      if (savePromise) return savePromise;
      if (!hasUnsavedChanges()) return state.profile;
      saveBtn.disabled = true;
      clearBtn.disabled = true;
      if (!saveOptions.silentProgress) {
        setMessage(saveOptions.messageText || "正在保存 SOUL.md...", "muted-message");
      }
      savePromise = (async () => {
        try {
          const data = await api("/api/profile/soul", {
            method: "PATCH",
            body: JSON.stringify({ soul_md: readValue() }),
          });
          state.profile = data.profile;
          syncSubmissionDraftSouls(typeof data.profile?.soul_md === "string" ? data.profile.soul_md : "");
          refreshFromProfile();
          if (!saveOptions.silentSuccess) {
            setMessage(saveOptions.successText || options.saveSuccessMessage || "SOUL.md 已保存。", "success-message");
            const noticeText = saveOptions.noticeText === undefined ? options.noticeText || "SOUL.md 已保存" : saveOptions.noticeText;
            if (noticeText) showNotice(noticeText, "success");
          }
          if (typeof options.onProfileUpdated === "function") options.onProfileUpdated(state.profile);
          return data.profile;
        } catch (error) {
          setMessage(error.message);
          if (!saveOptions.silentError) showNotice(error.message, "error");
          throw error;
        } finally {
          saveBtn.disabled = false;
          clearBtn.disabled = false;
          savePromise = null;
        }
      })();
      return savePromise;
    };

    if (typeof options.initialValue === "string") {
      textarea.value = options.initialValue;
    }

    clearBtn.addEventListener("click", () => {
      textarea.value = "";
      syncMeta();
      setMessage();
      notifyInputChange();
    });

    textarea.addEventListener("input", () => {
      syncMeta();
      setMessage();
      notifyInputChange();
    });
    textarea.addEventListener("change", () => {
      syncMeta();
      setMessage();
      notifyInputChange();
    });

    saveBtn.addEventListener("click", async () => {
      try {
        await saveSoul();
      } catch (error) {
        // Message is already surfaced in saveSoul.
      }
    });

    syncMeta();
    return {
      readValue,
      hasUnsavedChanges,
      saveSoul,
      refreshFromProfile,
    };
  }

  Object.assign(OJApp, {
    currentSoulMarkdown,
    renderSoulEditorSection,
    bindSoulEditor,
  });
})();
