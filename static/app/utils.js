import { state } from "./state.js";

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

const BEIJING_TIME_FORMATTER = new Intl.DateTimeFormat("zh-CN", {
  timeZone: "Asia/Shanghai",
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
  hour: "2-digit",
  minute: "2-digit",
  second: "2-digit",
  hourCycle: "h23",
});

function formatBeijingTime(date) {
  const values = {};
  BEIJING_TIME_FORMATTER.formatToParts(date).forEach((part) => {
    if (part.type !== "literal") values[part.type] = part.value;
  });
  return `${values.year}-${values.month}-${values.day} ${values.hour}:${values.minute}:${values.second}`;
}

function compactTime(value) {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value).replace("T", " ").replace("+00:00", "");
  return formatBeijingTime(date);
}

function parseTimeValue(value) {
  if (!value) return null;
  const timestamp = Date.parse(value);
  return Number.isFinite(timestamp) ? timestamp : null;
}

function formatDurationMs(milliseconds) {
  if (!Number.isFinite(milliseconds) || milliseconds < 0) return "-";
  const totalSeconds = Math.floor(milliseconds / 1000);
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const seconds = totalSeconds % 60;
  if (hours > 0) return `${hours}h ${String(minutes).padStart(2, "0")}m ${String(seconds).padStart(2, "0")}s`;
  return `${minutes}m ${String(seconds).padStart(2, "0")}s`;
}

function submissionDurationText(item) {
  const startedAt = parseTimeValue(item?.started_at);
  if (!startedAt) return "-";
  const finishedAt = parseTimeValue(item?.finished_at);
  const endTime = finishedAt || Date.now();
  return formatDurationMs(endTime - startedAt);
}

const SUBMISSION_DRAFT_PREFIX = "oj_submission_draft";

function submissionDraftKey(caseId) {
  const username = state.user?.username || state.savedUsername || "anonymous";
  return `${SUBMISSION_DRAFT_PREFIX}:${username}:${caseId}`;
}

function submissionDraftPrefix(username = state.user?.username || state.savedUsername || "anonymous") {
  return `${SUBMISSION_DRAFT_PREFIX}:${username}:`;
}

function normalizeDraftSkillIds(skillIds, maxSkills = state.config?.max_skills || 10) {
  if (!Array.isArray(skillIds)) return [];
  const values = [];
  skillIds.forEach((item) => {
    const value = typeof item === "string"
      ? item.trim()
      : (typeof item?.id === "string" ? item.id.trim() : "");
    if (!value || values.includes(value)) return;
    if (values.length < maxSkills) values.push(value);
  });
  return values;
}

function readSubmissionDraft(caseId, maxSkills = state.config?.max_skills || 10) {
  try {
    const raw = localStorage.getItem(submissionDraftKey(caseId));
    if (!raw) {
      return {
        prompt: "",
        selected_skill_ids: [],
        selected_mcp_servers: [],
        has_selected_mcp_servers: false,
        soul_md: "",
        saved_at: "",
      };
    }
    const parsed = JSON.parse(raw);
    return {
      prompt: typeof parsed?.prompt === "string" ? parsed.prompt : "",
      selected_skill_ids: normalizeDraftSkillIds(parsed?.selected_skill_ids || parsed?.skills, maxSkills),
      selected_mcp_servers: Array.isArray(parsed?.selected_mcp_servers)
        ? parsed.selected_mcp_servers
          .map((item) => String(item || "").trim())
          .filter((item, index, items) => item && items.indexOf(item) === index)
        : [],
      has_selected_mcp_servers: Array.isArray(parsed?.selected_mcp_servers),
      soul_md: typeof parsed?.soul_md === "string" ? parsed.soul_md : "",
      saved_at: typeof parsed?.saved_at === "string" ? parsed.saved_at : "",
    };
  } catch (error) {
    return {
      prompt: "",
      selected_skill_ids: [],
      selected_mcp_servers: [],
      has_selected_mcp_servers: false,
      soul_md: "",
      saved_at: "",
    };
  }
}

function writeSubmissionDraft(caseId, draft, maxSkills = state.config?.max_skills || 10) {
  try {
    const selectedMcpServers = Array.isArray(draft?.selected_mcp_servers)
      ? draft.selected_mcp_servers
        .map((item) => String(item || "").trim())
        .filter((item, index, items) => item && items.indexOf(item) === index)
      : [];
    const payload = {
      prompt: typeof draft?.prompt === "string" ? draft.prompt : "",
      selected_skill_ids: normalizeDraftSkillIds(draft?.selected_skill_ids || draft?.skills, maxSkills),
      selected_mcp_servers: selectedMcpServers,
      soul_md: typeof draft?.soul_md === "string" ? draft.soul_md : "",
      saved_at: new Date().toISOString(),
    };
    const hasContent = (
      payload.prompt.trim()
      || payload.selected_skill_ids.length > 0
      || payload.soul_md.trim()
      || Array.isArray(draft?.selected_mcp_servers)
    );
    if (!hasContent) {
      localStorage.removeItem(submissionDraftKey(caseId));
      return "";
    }
    localStorage.setItem(submissionDraftKey(caseId), JSON.stringify(payload));
    return payload.saved_at;
  } catch (error) {
    return "";
  }
}

function clearSubmissionDraft(caseId) {
  try {
    localStorage.removeItem(submissionDraftKey(caseId));
  } catch (error) {
    // Ignore local storage failures.
  }
}

function syncSubmissionDraftSouls(nextSoulMd, username = state.user?.username || state.savedUsername || "anonymous") {
  try {
    const prefix = submissionDraftPrefix(username);
    const normalizedSoul = typeof nextSoulMd === "string"
      ? nextSoulMd.replace(/\r\n/g, "\n").replace(/\r/g, "\n")
      : "";
    const keys = [];
    for (let index = 0; index < localStorage.length; index += 1) {
      const key = localStorage.key(index);
      if (key && key.startsWith(prefix)) keys.push(key);
    }
    keys.forEach((key) => {
      try {
        const raw = localStorage.getItem(key);
        if (!raw) return;
        const parsed = JSON.parse(raw);
        const payload = {
          prompt: typeof parsed?.prompt === "string" ? parsed.prompt : "",
          selected_skill_ids: normalizeDraftSkillIds(parsed?.selected_skill_ids || parsed?.skills),
          selected_mcp_servers: Array.isArray(parsed?.selected_mcp_servers)
            ? parsed.selected_mcp_servers
              .map((item) => String(item || "").trim())
              .filter((item, index, items) => item && items.indexOf(item) === index)
            : [],
          soul_md: normalizedSoul,
          saved_at: new Date().toISOString(),
        };
        const hasContent = (
          payload.prompt.trim()
          || payload.selected_skill_ids.length > 0
          || payload.soul_md.trim()
          || Array.isArray(parsed?.selected_mcp_servers)
        );
        if (!hasContent) {
          localStorage.removeItem(key);
          return;
        }
        localStorage.setItem(key, JSON.stringify(payload));
      } catch (error) {
        // Ignore malformed or inaccessible draft entries.
      }
    });
  } catch (error) {
    // Ignore local storage failures.
  }
}

function confirmTwice(firstMessage, secondMessage) {
  if (!window.confirm(String(firstMessage || "请确认该操作。"))) return false;
  return window.confirm(String(secondMessage || "这是最后一次确认，是否继续？"));
}

function caseOrderText(item) {
  const value = Number(item?.order_id);
  return Number.isFinite(value) && value > 0 ? `#${value}` : "#-";
}

function caseNavLabel(item) {
  return `${caseOrderText(item)} ${item?.title || item?.id || ""}`.trim();
}

function statusText(status) {
  return {
    queued: "排队中",
    running: "准备运行",
    injecting: "注入故障",
    answering: "测评中",
    recovering: "恢复环境",
    grading: "评分中",
    done: "已完成",
    failed: "失败",
  }[status] || status;
}

function statusClass(status) {
  if (status === "done") return "ok";
  if (status === "failed") return "bad";
  if (["running", "injecting", "answering", "recovering", "grading"].includes(status)) return "busy";
  return "queued";
}

function verdictText(score) {
  if (score == null || score === "") return "-";
  const value = Number(score);
  if (!Number.isFinite(value)) return "-";
  if (value >= 90) return "优秀";
  if (value >= 75) return "良好";
  if (value >= 60) return "合格";
  return "不合格";
}

function visibleSubmissions() {
  return state.submissions.slice();
}

function lineClass(line) {
  const text = String(line || "");
  const lower = text.toLowerCase();
  if (lower.includes("error") || lower.includes("failed") || lower.includes("forbidden") || text.includes("失败")) return "error";
  if (lower.includes("/tool") || lower.includes("工具调用")) return "tool";
  if (text.includes("inject")) return "inject";
  if (text.includes("recover")) return "recover";
  if (text.includes("评分")) return "grade";
  if (text.includes("测评")) return "answer";
  if (lower.includes("finished") || text.includes("完成")) return "done";
  return "";
}

function parseLiveLogLine(line) {
  const text = String(line || "");
  const match = text.match(/^\[([^\]]+)\]\s+([^:]+):\s?(.*)$/);
  if (!match) return null;
  const [, time, channel, body] = match;
  const parts = channel.split("/");
  const kind = parts.slice(1).join("/");
  if (!["stage", "tool-call", "tool-result"].includes(kind)) return null;
  const phase = parts[0] || "agent";
  const title = {
    stage: "",
    "tool-call": "调用工具",
    "tool-result": "工具返回",
  }[kind];
  return { time, phase, kind, title, body };
}

function splitLiveToolBody(body) {
  const text = String(body || "");
  const match = text.match(/^(?:调用工具|返回摘要)\s+([^:(\s]+)(?:\s*\(([^)]*)\))?:?\s*(.*)$/);
  if (!match) return { tool: "", meta: "", detail: text };
  return {
    tool: match[1] || "",
    meta: match[2] || "",
    detail: match[3] || "",
  };
}

function renderLiveEvent(event) {
  if (event.kind === "stage") {
    return `
      <div class="live-event stage">
        <div class="live-time">${escapeHtml(compactTime(event.time))}</div>
        <div class="live-message">${escapeHtml(event.body || "")}</div>
      </div>
    `;
  }
  const tool = splitLiveToolBody(event.body);
  return `
    <div class="live-event ${event.kind}">
      <div class="live-meta">
        <strong>${escapeHtml(event.title)}</strong>
        <span>${escapeHtml([tool.tool, tool.meta].filter(Boolean).join(" · ") || compactTime(event.time))}</span>
      </div>
      <pre>${escapeHtml(tool.detail || event.body || "")}</pre>
    </div>
  `;
}

function renderLogLines(text) {
  const lines = String(text || "等待 worker 接收任务").split("\n").filter((line) => line.trim());
  return `<div class="log-timeline">${lines.map((line) => {
    const event = parseLiveLogLine(line);
    if (event) return renderLiveEvent(event);
    return `
      <div class="log-line ${lineClass(line)}">
        <span>${escapeHtml(formatLogLineTime(line || " "))}</span>
      </div>
    `;
  }).join("")}</div>`;
}

function gradingResultText(item) {
  if (item?.grade_output) return item.grade_output;
  if (item?.grade_json) {
    try {
      return JSON.stringify(JSON.parse(item.grade_json), null, 2);
    } catch (error) {
      // Fall through to the streamed API output.
    }
  }
  return item?.grade_output || "";
}

function processOutputText(item) {
  return item?.answer_process ? `答题 Agent 调用过程\n${item.answer_process}` : "";
}

function formatLogLineTime(line) {
  return String(line || "").replace(/^\[([^\]]+)\]/, (_, rawTime) => `[${compactTime(rawTime)}]`);
}

export {
  escapeHtml,
  formatBeijingTime,
  compactTime,
  parseTimeValue,
  formatDurationMs,
  submissionDurationText,
  submissionDraftKey,
  normalizeDraftSkillIds,
  readSubmissionDraft,
  writeSubmissionDraft,
  clearSubmissionDraft,
  syncSubmissionDraftSouls,
  confirmTwice,
  caseOrderText,
  caseNavLabel,
  statusText,
  statusClass,
  verdictText,
  visibleSubmissions,
  lineClass,
  parseLiveLogLine,
  splitLiveToolBody,
  renderLiveEvent,
  renderLogLines,
  gradingResultText,
  processOutputText,
  formatLogLineTime,
};
