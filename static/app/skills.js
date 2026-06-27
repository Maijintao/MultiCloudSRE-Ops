(function () {
  const OJApp = window.OJApp;
  const { state, escapeHtml, showNotice, api } = OJApp;

  function currentSkills(profile = state.profile) {
    return normalizeSkillList(Array.isArray(profile?.skills) ? profile.skills : []);
  }

  function slugifySkillName(value, fallback = "SKILL1") {
    let text = String(value || "").trim().replace(/[^A-Za-z0-9._-]+/g, "-");
    text = text.replace(/^[._-]+|[._-]+$/g, "");
    if (!text || !/^[A-Za-z0-9]/.test(text)) text = String(fallback || "SKILL1");
    text = text.replace(/[^A-Za-z0-9._-]+/g, "-").slice(0, 64).replace(/[._-]+$/g, "");
    if (!text || !/^[A-Za-z0-9]/.test(text)) text = String(fallback || "SKILL1");
    return text.slice(0, 64);
  }

  function normalizeSkillName(value, fallback = "SKILL1", usedNames) {
    const safeFallback = slugifySkillName(fallback, "SKILL1");
    let name = String(value || "").trim();
    if (!/^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$/.test(name)) {
      name = slugifySkillName(name, safeFallback);
    }
    if (!name || !/^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$/.test(name)) {
      name = safeFallback;
    }
    if (!usedNames?.has(name)) {
      usedNames?.add(name);
      return name;
    }
    let suffix = 2;
    while (suffix < 1000) {
      const tail = `-${suffix}`;
      let base = name.slice(0, Math.max(1, 64 - tail.length)).replace(/[._-]+$/g, "");
      if (!base || !/^[A-Za-z0-9]/.test(base)) {
        base = safeFallback.slice(0, Math.max(1, 64 - tail.length)).replace(/[._-]+$/g, "") || safeFallback;
      }
      const deduped = `${base}${tail}`;
      if (/^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$/.test(deduped) && !usedNames?.has(deduped)) {
        usedNames?.add(deduped);
        return deduped;
      }
      suffix += 1;
    }
    const finalName = safeFallback.slice(0, 64);
    usedNames?.add(finalName);
    return finalName;
  }

  function normalizeSkillList(skills) {
    const usedNames = new Set();
    return (Array.isArray(skills) ? skills : []).map((skill, index) => normalizeSkill(skill, index, usedNames));
  }

  function normalizeSkill(skill, index = 0, usedNames = new Set()) {
    const type = skill?.type === "archive" ? "archive" : "text";
    const fallbackName = `SKILL${index + 1}`;
    const fallbackId = `skill-${index + 1}`;
    const name = normalizeSkillName(skill?.name || fallbackName, fallbackName, usedNames);
    if (type === "archive") {
      return {
        id: String(skill?.id || fallbackId),
        type,
        name,
        source_name: String(skill?.source_name || ""),
        file_count: Number(skill?.file_count || 0) || 0,
        archive_size: Number(skill?.archive_size || 0) || 0,
        stored_at: String(skill?.stored_at || ""),
      };
    }
    return {
      id: String(skill?.id || fallbackId),
      type,
      name,
      content: String(skill?.content || ""),
    };
  }

  function nextSkillName(skills) {
    const names = new Set((skills || []).map((item) => String(item?.name || "").trim()));
    let index = 1;
    while (names.has(`SKILL${index}`)) index += 1;
    return `SKILL${index}`;
  }

  function newTextSkill(skills) {
    const nextIndex = (skills?.length || 0) + 1;
    return {
      id: `skill-${Date.now()}-${nextIndex}`,
      type: "text",
      name: nextSkillName(skills || []),
      content: "",
    };
  }

  function formatBytes(value) {
    const bytes = Number(value);
    if (!Number.isFinite(bytes) || bytes <= 0) return "0 B";
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  }

  function skillCardHtml(skill, index, options = {}) {
    const includeSelection = !!options.includeSelection;
    const selected = options.selectedIds?.has(skill.id);
    const isArchive = skill.type === "archive";
    const typeLabel = isArchive ? "ZIP" : "TEXT";
    return `
      <section class="skill-card ${isArchive ? "archive" : "text"}" data-skill-id="${escapeHtml(skill.id)}" data-skill-type="${escapeHtml(skill.type)}">
        <div class="skill-card-head">
          <div class="skill-card-title">
            ${includeSelection ? `
              <label class="skill-check">
                <input type="checkbox" data-skill-select ${selected ? "checked" : ""} />
                <span>Attach</span>
              </label>
            ` : ""}
            <strong>Skill ${index + 1}</strong>
            <span class="skill-kind-badge ${isArchive ? "archive" : "text"}">${typeLabel}</span>
          </div>
          <button type="button" class="ghost slim" data-remove-skill="${escapeHtml(skill.id)}">Remove</button>
        </div>
        <label>
          <span>Name</span>
          <input class="skill-name" value="${escapeHtml(skill.name || "")}" maxlength="64" pattern="[A-Za-z0-9][A-Za-z0-9._-]{0,63}" required />
        </label>
        ${isArchive ? `
          <div class="skill-archive-meta">
            <div><strong>Source</strong><span>${escapeHtml(skill.source_name || "-")}</span></div>
            <div><strong>Bundle</strong><span>${escapeHtml(`${skill.file_count || 0} files / ${formatBytes(skill.archive_size)}`)}</span></div>
            <p class="muted">ZIP skill files are saved permanently. Files cannot be edited here.</p>
          </div>
        ` : `
          <label>
            <span>Content</span>
            <textarea class="skill-content" rows="7">${escapeHtml(skill.content || "")}</textarea>
          </label>
        `}
      </section>
    `;
  }

  function renderSkillManagerSection(options = {}) {
    const prefix = options.idPrefix || "shared";
    const skills = currentSkills(options.profile);
    const maxSkills = Number(options.maxSkills || state.config?.max_skills || 10) || 10;
    const maxSkillChars = Number(options.maxSkillChars || state.config?.max_skill_chars || 100000) || 100000;
    const maxArchiveBytes = Number(options.maxArchiveBytes || state.config?.max_skill_archive_bytes || (10 * 1024 * 1024)) || (10 * 1024 * 1024);
    const includeSelection = !!options.includeSelection;
    const description = options.description || "Skills are saved permanently. Add text skills or upload ZIP bundle skills.";
    return `
      <section id="${prefix}SkillManager" class="panel form-panel">
        <div class="section-head">
          <div>
            <span class="eyebrow">Skills</span>
            <h3>${escapeHtml(options.title || "Reusable Skills")}</h3>
          </div>
          <span class="status ${skills.length ? "ok" : "queued"}" id="${prefix}SkillCount">${skills.length}/${maxSkills}</span>
        </div>
        <p class="muted">${escapeHtml(description)}</p>
        <p class="muted">Limit: ${maxSkills} skills, text total up to ${maxSkillChars} chars, ZIP up to ${formatBytes(maxArchiveBytes)} each.</p>
        ${includeSelection ? `<p class="muted">Only checked skills will be attached to this submission.</p>` : ""}
        <div class="skill-editor">
          <div class="section-head compact">
            <div>
              <span class="eyebrow">Manage</span>
              <h4>Skill List</h4>
            </div>
            <div class="submit-actions">
              <input id="${prefix}SkillUploadInput" type="file" accept=".zip,application/zip" hidden />
              <button type="button" class="ghost slim" id="${prefix}AddTextSkillBtn">Add Text Skill</button>
              <button type="button" class="ghost slim" id="${prefix}UploadSkillBtn">Upload ZIP</button>
            </div>
          </div>
          <div id="${prefix}SkillList" class="skill-list"></div>
        </div>
        <div class="submit-actions">
          <button type="button" class="primary" id="${prefix}SaveSkillsBtn">${escapeHtml(options.saveButtonLabel || "Save Skills")}</button>
        </div>
        <p id="${prefix}SkillMessage" class="form-message"></p>
      </section>
    `;
  }

  function bindSkillManager(options = {}) {
    const prefix = options.idPrefix || "shared";
    const maxSkills = Number(options.maxSkills || state.config?.max_skills || 10) || 10;
    const maxArchiveBytes = Number(options.maxArchiveBytes || state.config?.max_skill_archive_bytes || (10 * 1024 * 1024)) || (10 * 1024 * 1024);
    const includeSelection = !!options.includeSelection;
    const listEl = document.getElementById(`${prefix}SkillList`);
    const addBtn = document.getElementById(`${prefix}AddTextSkillBtn`);
    const uploadBtn = document.getElementById(`${prefix}UploadSkillBtn`);
    const uploadInput = document.getElementById(`${prefix}SkillUploadInput`);
    const saveBtn = document.getElementById(`${prefix}SaveSkillsBtn`);
    const countEl = document.getElementById(`${prefix}SkillCount`);
    const messageEl = document.getElementById(`${prefix}SkillMessage`);
    if (!listEl || !addBtn || !uploadBtn || !uploadInput || !saveBtn) return null;

    let selectedIds = new Set(Array.isArray(options.initialSelectedIds) ? options.initialSelectedIds.map((item) => String(item || "").trim()).filter(Boolean) : []);
    let lastRenderedSkills = currentSkills();
    let savePromise = null;

    const setMessage = (text = "", kind = "") => {
      if (!messageEl) return;
      messageEl.textContent = text;
      messageEl.className = kind ? `form-message ${kind}` : "form-message";
    };

    const readSkills = () => {
      const rawSkills = [...listEl.querySelectorAll(".skill-card")].map((card, index) => {
        const type = card.dataset.skillType === "archive" ? "archive" : "text";
        const base = {
          id: card.dataset.skillId || `skill-${index + 1}`,
          type,
          name: card.querySelector(".skill-name")?.value || `SKILL${index + 1}`,
        };
        if (type === "archive") return base;
        return { ...base, content: card.querySelector(".skill-content")?.value || "" };
      });
      return normalizeSkillList(rawSkills);
    };

    const orderedSelectedIds = () => {
      return [...listEl.querySelectorAll(".skill-card")]
        .map((card) => ({
          id: card.dataset.skillId || "",
          checked: !!card.querySelector("[data-skill-select]")?.checked,
        }))
        .filter((item) => item.id && item.checked)
        .map((item) => item.id);
    };

    const payloadSkills = () => {
      return readSkills()
        .map((skill) => ({
          id: String(skill.id || "").trim(),
          type: skill.type === "archive" ? "archive" : "text",
          name: String(skill.name || "").trim(),
          content: skill.type === "archive" ? "" : String(skill.content || "").trim(),
        }))
        .filter((skill) => skill.type === "archive" || skill.content);
    };

    const savedPayloadSkills = () => {
      return currentSkills()
        .map((skill) => ({
          id: String(skill.id || "").trim(),
          type: skill.type === "archive" ? "archive" : "text",
          name: String(skill.name || "").trim(),
          content: skill.type === "archive" ? "" : String(skill.content || "").trim(),
        }))
        .filter((skill) => skill.type === "archive" || skill.content);
    };

    const hasUnsavedChanges = () => JSON.stringify(payloadSkills()) !== JSON.stringify(savedPayloadSkills());

    const syncSelection = () => {
      if (!includeSelection) return;
      selectedIds = new Set(orderedSelectedIds());
      if (typeof options.onSelectionChange === "function") options.onSelectionChange([...selectedIds]);
    };

    const updateButtons = (skills) => {
      const reachedLimit = skills.length >= maxSkills;
      addBtn.disabled = reachedLimit;
      uploadBtn.disabled = reachedLimit;
      if (countEl) countEl.textContent = `${skills.length}/${maxSkills}`;
    };

    const attachCardEvents = () => {
      listEl.querySelectorAll("[data-remove-skill]").forEach((button) => {
        button.addEventListener("click", () => {
          const skillId = button.dataset.removeSkill || "";
          const nextSkills = readSkills().filter((skill) => skill.id !== skillId);
          selectedIds.delete(skillId);
          render(nextSkills);
          setMessage();
          syncSelection();
        });
      });
      listEl.querySelectorAll("[data-skill-select]").forEach((input) => {
        input.addEventListener("change", syncSelection);
      });
      listEl.querySelectorAll(".skill-name, .skill-content").forEach((input) => {
        input.addEventListener("input", () => setMessage());
        input.addEventListener("change", () => setMessage());
      });
      listEl.querySelectorAll(".skill-name").forEach((input) => {
        input.addEventListener("blur", () => {
          render(readSkills());
          setMessage();
        });
      });
    };

    const render = (skills = readSkills()) => {
      lastRenderedSkills = normalizeSkillList(skills);
      const validIds = new Set(lastRenderedSkills.map((skill) => skill.id));
      selectedIds = new Set([...selectedIds].filter((skillId) => validIds.has(skillId)));
      listEl.innerHTML = lastRenderedSkills.map((skill, index) => skillCardHtml(skill, index, { includeSelection, selectedIds })).join("");
      if (!lastRenderedSkills.length) {
        listEl.innerHTML = `<div class="empty compact-empty">No saved skills yet.</div>`;
      }
      updateButtons(lastRenderedSkills);
      attachCardEvents();
      syncSelection();
    };

    const refreshFromProfile = (nextSelectedIds) => {
      if (Array.isArray(nextSelectedIds)) selectedIds = new Set(nextSelectedIds.map((item) => String(item || "").trim()).filter(Boolean));
      render(currentSkills());
    };

    addBtn.addEventListener("click", () => {
      const skills = readSkills();
      if (skills.length >= maxSkills) return;
      const skill = newTextSkill(skills);
      if (includeSelection) selectedIds.add(skill.id);
      render([...skills, skill]);
      setMessage();
    });

    uploadBtn.addEventListener("click", () => {
      if (!uploadBtn.disabled) uploadInput.click();
    });

    uploadInput.addEventListener("change", async () => {
      const [file] = [...(uploadInput.files || [])];
      uploadInput.value = "";
      if (!file) return;
      if (!/\.zip$/i.test(file.name)) {
        showNotice("Please upload a .zip file.", "error");
        return;
      }
      if (file.size > maxArchiveBytes) {
        showNotice(`ZIP file is too large. Max ${formatBytes(maxArchiveBytes)}.`, "error");
        return;
      }
      uploadBtn.disabled = true;
      addBtn.disabled = true;
      saveBtn.disabled = true;
      try {
        if (hasUnsavedChanges()) {
          const draftSkills = payloadSkills();
          if (draftSkills.length >= maxSkills) {
            throw new Error(`Skill limit is ${maxSkills}. Remove one saved skill before uploading ZIP.`);
          }
          setMessage("Saving current skills before uploading ZIP...", "muted-message");
          await saveSkills({
            silentProgress: true,
            silentSuccess: true,
            silentError: true,
            noticeText: "",
          });
        }
        uploadBtn.disabled = true;
        addBtn.disabled = true;
        saveBtn.disabled = true;
        setMessage("Uploading ZIP skill...", "muted-message");
        const previousIds = new Set(currentSkills().map((skill) => skill.id));
        const data = await api("/api/profile/skills/upload", {
          method: "POST",
          raw: true,
          headers: {
            "Content-Type": file.type || "application/zip",
            "X-Skill-File-Name": encodeURIComponent(file.name),
          },
          body: file,
        });
        state.profile = data.profile;
        const addedSkill = currentSkills().find((skill) => !previousIds.has(skill.id));
        if (includeSelection && addedSkill) selectedIds.add(addedSkill.id);
        setMessage("ZIP skill uploaded and saved.", "success-message");
        showNotice("ZIP skill uploaded.", "success");
        refreshFromProfile();
        if (typeof options.onProfileUpdated === "function") options.onProfileUpdated(state.profile);
      } catch (error) {
        setMessage(error.message);
        showNotice(error.message, "error");
      } finally {
        saveBtn.disabled = false;
        updateButtons(readSkills());
      }
    });

    const saveSkills = async (saveOptions = {}) => {
      if (savePromise) return savePromise;
      if (!hasUnsavedChanges()) return state.profile;
      const skills = payloadSkills();
      const messageText = saveOptions.messageText || "Saving skills...";
      const successText = saveOptions.successText || options.saveSuccessMessage || "Skills saved.";
      const noticeText = saveOptions.noticeText === undefined ? options.noticeText || "Skills saved." : saveOptions.noticeText;
      saveBtn.disabled = true;
      if (!saveOptions.silentProgress) setMessage(messageText, "muted-message");
      savePromise = (async () => {
        try {
          const data = await api("/api/profile/skills", {
            method: "PATCH",
            body: JSON.stringify({ skills }),
          });
          state.profile = data.profile;
          if (!saveOptions.silentSuccess) {
            setMessage(successText, "success-message");
            if (noticeText) showNotice(noticeText, "success");
          } else {
            setMessage();
          }
          refreshFromProfile();
          if (typeof options.onProfileUpdated === "function") options.onProfileUpdated(state.profile);
          return data.profile;
        } catch (error) {
          setMessage(error.message);
          if (!saveOptions.silentError) showNotice(error.message, "error");
          throw error;
        } finally {
          saveBtn.disabled = false;
          savePromise = null;
        }
      })();
      return savePromise;
    };

    saveBtn.addEventListener("click", async () => {
      try {
        await saveSkills();
      } catch (error) {
        // Message is already surfaced in saveSkills.
      }
    });

    render(lastRenderedSkills);
    return {
      getSelectedIds: () => [...selectedIds],
      hasUnsavedChanges,
      refreshFromProfile,
      readSkills,
      saveSkills,
    };
  }

  Object.assign(OJApp, {
    currentSkills,
    nextSkillName,
    formatBytes,
    renderSkillManagerSection,
    bindSkillManager,
  });
})();
