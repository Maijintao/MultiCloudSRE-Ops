(function () {
  const OJApp = window.OJApp;
  const { escapeHtml, showNotice } = OJApp;
function copyIconButton(target, label = "复制内容") {
  return `
    <button type="button" class="ghost slim icon-button" data-copy-target="${escapeHtml(target)}" aria-label="${escapeHtml(label)}" title="${escapeHtml(label)}">
      <svg viewBox="0 0 24 24" aria-hidden="true">
        <path d="M9 8.25A2.25 2.25 0 0 1 11.25 6h7.5A2.25 2.25 0 0 1 21 8.25v10.5A2.25 2.25 0 0 1 18.75 21h-7.5A2.25 2.25 0 0 1 9 18.75V8.25Z"></path>
        <path d="M15 6V5.25A2.25 2.25 0 0 0 12.75 3h-7.5A2.25 2.25 0 0 0 3 5.25v10.5A2.25 2.25 0 0 0 5.25 18H9"></path>
      </svg>
    </button>
  `;
}

function downloadIconButton(target, filename, label = "下载 Markdown") {
  return `
    <button
      type="button"
      class="ghost slim icon-button"
      data-download-target="${escapeHtml(target)}"
      data-download-filename="${escapeHtml(filename)}"
      aria-label="${escapeHtml(label)}"
      title="${escapeHtml(label)}"
    >
      <svg viewBox="0 0 24 24" aria-hidden="true">
        <path d="M12 3v11.25"></path>
        <path d="m7.5 10.5 4.5 4.5 4.5-4.5"></path>
        <path d="M4.5 15.75v2.25A2.25 2.25 0 0 0 6.75 20.25h10.5A2.25 2.25 0 0 0 19.5 18v-2.25"></path>
      </svg>
    </button>
  `;
}

function textFromElement(el) {
  if (!el) return "";
  return "value" in el ? el.value : (el.textContent || "");
}

function ensureMarkdownFilename(filename) {
  const raw = String(filename || "output.md").trim() || "output.md";
  const safe = raw.replace(/[\\/:*?"<>|]+/g, "-").replace(/\s+/g, " ");
  return safe.toLowerCase().endsWith(".md") ? safe : `${safe}.md`;
}

async function copyTextFromElement(id) {
  const el = document.getElementById(id);
  if (!el) return;
  const text = textFromElement(el);
  let copied = false;
  if (window.isSecureContext && navigator.clipboard?.writeText) {
    try {
      await navigator.clipboard.writeText(text);
      copied = true;
    } catch (error) {
      copied = false;
    }
  }
  if (!copied) {
    const copyBuffer = document.createElement("textarea");
    copyBuffer.value = text;
    copyBuffer.setAttribute("aria-hidden", "true");
    copyBuffer.tabIndex = -1;
    copyBuffer.style.position = "fixed";
    copyBuffer.style.left = "0";
    copyBuffer.style.top = "0";
    copyBuffer.style.width = "1px";
    copyBuffer.style.height = "1px";
    copyBuffer.style.padding = "0";
    copyBuffer.style.border = "0";
    copyBuffer.style.opacity = "0";
    document.body.appendChild(copyBuffer);
    copyBuffer.focus();
    copyBuffer.select();
    copyBuffer.setSelectionRange(0, copyBuffer.value.length);
    try {
      copied = document.execCommand("copy");
    } catch (error) {
      copied = false;
    }
    copyBuffer.remove();
  }
  if (!copied) {
    if ("select" in el) {
      el.focus();
      el.select();
    } else {
      const range = document.createRange();
      range.selectNodeContents(el);
      const selection = window.getSelection();
      selection.removeAllRanges();
      selection.addRange(range);
    }
  }
  showNotice(copied ? "已复制" : "内容已选中，请按 Ctrl+C 复制", copied ? "success" : "info");
}

function downloadTextFromElement(id, filename) {
  const el = document.getElementById(id);
  if (!el) return;
  const text = textFromElement(el);
  const blob = new Blob(["\uFEFF", text], { type: "text/markdown;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = ensureMarkdownFilename(filename);
  link.style.display = "none";
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
  showNotice("已开始下载 Markdown 文件", "success");
}

function bindCopyButtons(root = document) {
  root.querySelectorAll("[data-copy-target]").forEach((button) => {
    button.addEventListener("click", () => copyTextFromElement(button.dataset.copyTarget));
  });
}

function bindDownloadButtons(root = document) {
  root.querySelectorAll("[data-download-target]").forEach((button) => {
    button.addEventListener("click", () => {
      downloadTextFromElement(button.dataset.downloadTarget, button.dataset.downloadFilename);
    });
  });
}

  Object.assign(OJApp, {
    copyIconButton,
    downloadIconButton,
    copyTextFromElement,
    downloadTextFromElement,
    bindCopyButtons,
    bindDownloadButtons,
  });
})();
