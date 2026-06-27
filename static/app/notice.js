(function () {
  const OJApp = window.OJApp;

  const DEFAULT_NOTICE_DURATION = 4000;
  let noticeSeed = 0;

  function noticeHost() {
    let host = document.getElementById("notice");
    if (host) return host;
    const frame = document.querySelector(".content-frame") || document.body;
    host = document.createElement("div");
    host.id = "notice";
    host.className = "notice-stack";
    host.setAttribute("aria-live", "polite");
    frame.appendChild(host);
    return host;
  }

  function removeNoticeCard(card) {
    if (!card || !card.parentElement) return;
    card.classList.add("leaving");
    window.setTimeout(() => {
      if (card.parentElement) card.parentElement.removeChild(card);
    }, 180);
  }

  function showNotice(message, type = "info", duration = DEFAULT_NOTICE_DURATION) {
    const text = String(message || "").trim();
    if (!text) return;
    const host = noticeHost();
    const card = document.createElement("div");
    card.className = `notice ${type}`;
    card.dataset.noticeId = `notice-${Date.now()}-${noticeSeed += 1}`;
    card.innerHTML = `
      <div class="notice-body">${OJApp.escapeHtml(text)}</div>
      <button type="button" class="notice-close" aria-label="关闭提示">×</button>
    `;
    const closeButton = card.querySelector(".notice-close");
    closeButton?.addEventListener("click", () => removeNoticeCard(card));
    host.appendChild(card);
    if (Number.isFinite(duration) && duration > 0) {
      window.setTimeout(() => removeNoticeCard(card), duration);
    }
  }

  OJApp.showNotice = showNotice;
})();
