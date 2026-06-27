(function () {
  const OJApp = window.OJApp;
  const { state, api } = OJApp;
  const LEADERBOARD_CACHE_KEY = "oj_leaderboard_cache_v3";
  const CASES_CACHE_KEY_PREFIX = "oj_cases_cache_v3:";
  const SUBMISSION_SUMMARY_CACHE_PREFIX = "oj_submission_summary_v2:";

function leaderboardUrl(limit = 100) {
  const size = Math.max(1, Math.min(500, Number(limit) || 100));
  return `/api/leaderboard?limit=${size}`;
}

function applyLeaderboardResponse(data) {
  const items = Array.isArray(data?.leaderboard) ? data.leaderboard : [];
  state.leaderboard = items;
  state.leaderboardCaseCount = Math.max(
    0,
    Number(data?.leaderboard_case_count ?? data?.hidden_case_count) || 0,
  );
  state.testSetLeaderboardCaseCount = Math.max(0, Number(data?.test_set_case_count) || 0);
  state.leaderboardLoadedAt = Math.max(0, Number(data?.loaded_at) || Date.now());
}

function readLeaderboardCache() {
  try {
    const raw = localStorage.getItem(LEADERBOARD_CACHE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    if (!parsed || !Array.isArray(parsed.leaderboard)) return null;
    return parsed;
  } catch (error) {
    return null;
  }
}

function writeLeaderboardCache() {
  try {
    localStorage.setItem(LEADERBOARD_CACHE_KEY, JSON.stringify({
      leaderboard: state.leaderboard,
      leaderboard_case_count: state.leaderboardCaseCount,
      test_set_case_count: state.testSetLeaderboardCaseCount,
      loaded_at: state.leaderboardLoadedAt || Date.now(),
    }));
  } catch (error) {
    // Ignore storage failures.
  }
}

function applyCachedLeaderboard() {
  const cached = readLeaderboardCache();
  if (!cached) return false;
  applyLeaderboardResponse(cached);
  return true;
}

function leaderboardCacheFresh(maxAgeMs = 120000) {
  const cached = readLeaderboardCache();
  if (!cached) return false;
  const loadedAt = Math.max(0, Number(cached.loaded_at) || 0);
  if (!loadedAt) return false;
  return Date.now() - loadedAt <= Math.max(1000, Number(maxAgeMs) || 120000);
}

function submissionSummaryCacheKey() {
  const userId = Number(state.user?.id || 0);
  return userId > 0 ? `${SUBMISSION_SUMMARY_CACHE_PREFIX}${userId}` : "";
}

function casesCacheKey() {
  const userId = Number(state.user?.id || 0);
  return userId > 0 ? `${CASES_CACHE_KEY_PREFIX}${userId}` : "";
}

function readCasesCache() {
  try {
    const key = casesCacheKey();
    if (!key) return null;
    const raw = localStorage.getItem(key);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    if (!parsed || !Array.isArray(parsed.cases)) return null;
    return parsed;
  } catch (error) {
    return null;
  }
}

function writeCasesCache() {
  try {
    const key = casesCacheKey();
    if (!key) return;
    localStorage.setItem(key, JSON.stringify({
      cases: Array.isArray(state.cases) ? state.cases : [],
      loaded_at: Math.max(0, Number(state.casesLoadedAt) || Date.now()),
    }));
  } catch (error) {
    // Ignore storage failures.
  }
}

function applyCasesResponse(data) {
  state.cases = Array.isArray(data?.cases) ? data.cases : [];
  state.casesLoadedAt = Date.now();
}

function applyTestSetsResponse(data) {
  state.testSets = Array.isArray(data?.test_sets) ? data.test_sets : [];
  state.testSetsLoadedAt = Date.now();
}

function applyCachedCases() {
  const cached = readCasesCache();
  if (!cached) return false;
  state.cases = Array.isArray(cached.cases) ? cached.cases : [];
  state.casesLoadedAt = Math.max(0, Number(cached.loaded_at) || 0);
  return true;
}

function readSubmissionSummaryCache() {
  try {
    const key = submissionSummaryCacheKey();
    if (!key) return null;
    const raw = localStorage.getItem(key);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    if (!parsed || typeof parsed !== "object") return null;
    return parsed;
  } catch (error) {
    return null;
  }
}

function writeSubmissionSummaryCache() {
  try {
    const key = submissionSummaryCacheKey();
    if (!key) return;
    localStorage.setItem(key, JSON.stringify({
      total: Number(state.submissionsTotal) || 0,
      total_pages: Math.max(1, Number(state.submissionsTotalPages) || 1),
      page: Math.max(1, Number(state.submissionView?.page) || 1),
      per_page: Math.max(1, Number(state.submissionView?.perPage) || 20),
      loaded_at: Math.max(0, Number(state.submissionsLoadedAt) || Date.now()),
    }));
  } catch (error) {
    // Ignore storage failures.
  }
}

function applyCachedSubmissionSummary() {
  const cached = readSubmissionSummaryCache();
  if (!cached) return false;
  state.submissions = [];
  state.submissionsTotal = Math.max(0, Number(cached.total) || 0);
  state.submissionsTotalPages = Math.max(1, Number(cached.total_pages) || 1);
  state.submissionsLoadedAt = Math.max(0, Number(cached.loaded_at) || 0);
  state.submissionView.page = Math.max(1, Number(cached.page) || state.submissionView.page || 1);
  state.submissionView.perPage = Math.max(1, Number(cached.per_page) || state.submissionView.perPage || 20);
  return true;
}

function submissionListUrl() {
  const params = new URLSearchParams();
  const username = String(state.submissionView?.username || "").trim();
  const caseId = String(state.submissionView?.caseId || "").trim();
  const displayCaseName = String(state.submissionView?.displayCaseName || "").trim();
  const sortBy = state.submissionView?.sortBy === "score" ? "score" : "created_at";
  const sortOrder = state.submissionView?.sortOrder === "asc" ? "asc" : "desc";
  const page = Math.max(1, Number(state.submissionView?.page) || 1);
  const perPage = Math.max(1, Math.min(100, Number(state.submissionView?.perPage) || 20));
  if (username) params.set("username", username);
  if (caseId) params.set("case_id", caseId);
  if (displayCaseName) params.set("display_case_name", displayCaseName);
  params.set("sort_by", sortBy);
  params.set("sort_order", sortOrder);
  params.set("page", String(page));
  params.set("per_page", String(perPage));
  return `/api/submissions?${params.toString()}`;
}

function applySubmissionListResponse(data) {
  const items = Array.isArray(data?.submissions) ? data.submissions : [];
  const total = Number(data?.total);
  const totalPages = Number(data?.total_pages);
  const page = Number(data?.page);
  const perPage = Number(data?.per_page);
  state.submissions = items;
  state.submissionTestSetFilters = Array.isArray(data?.test_set_filters) ? data.test_set_filters : [];
  state.submissionsLoadedAt = Date.now();
  state.submissionsTotal = Number.isFinite(total) ? total : items.length;
  state.submissionsTotalPages = Math.max(1, Number.isFinite(totalPages) ? totalPages : 1);
  state.submissionView.page = Math.max(1, Number.isFinite(page) ? page : state.submissionView.page || 1);
  state.submissionView.perPage = Math.max(1, Number.isFinite(perPage) ? perPage : state.submissionView.perPage || 20);
}

function applyBootstrapResponse(data) {
  if (data?.user) state.user = data.user;
  state.config = data?.config || {};
  state.profile = data?.profile || null;
  applyTestSetsResponse({ test_sets: state.config?.test_sets || [] });
  applyCasesResponse({ cases: data?.cases || [] });
  writeCasesCache();
  state.submissions = [];
  if (!applyCachedSubmissionSummary()) {
    state.submissionsTotal = 0;
    state.submissionsTotalPages = 1;
    state.submissionsLoadedAt = 0;
  }
  if (!applyCachedLeaderboard()) {
    state.leaderboard = [];
    state.leaderboardCaseCount = 0;
    state.testSetLeaderboardCaseCount = 0;
    state.leaderboardLoadedAt = 0;
  }
}

async function loadInitialData(options = {}) {
  const includeSubmissions = options.includeSubmissions === true;
  const allowCachedCases = options.useCachedCases !== false;
  const hasCachedCases = allowCachedCases && applyCachedCases();
  const [config, profileData, caseData, submissionData] = await Promise.all([
    api("/api/config"),
    api("/api/profile"),
    hasCachedCases ? Promise.resolve(null) : api("/api/cases"),
    includeSubmissions ? api(submissionListUrl()) : Promise.resolve(null),
  ]);
  state.config = config;
  state.profile = profileData.profile;
  applyTestSetsResponse({ test_sets: config?.test_sets || [] });
  if (caseData) {
    applyCasesResponse(caseData);
    writeCasesCache();
  }
  if (submissionData) {
    applySubmissionListResponse(submissionData);
    writeSubmissionSummaryCache();
  } else if (!includeSubmissions) {
    state.submissions = [];
    if (!applyCachedSubmissionSummary()) {
      state.submissionsTotal = 0;
      state.submissionsTotalPages = 1;
      state.submissionsLoadedAt = 0;
    }
  }
  if (!applyCachedLeaderboard()) {
    state.leaderboard = [];
    state.leaderboardCaseCount = 0;
    state.testSetLeaderboardCaseCount = 0;
    state.leaderboardLoadedAt = 0;
  }
  if (hasCachedCases) refreshCases({ rerender: false }).catch(() => {});
}

async function refreshCases(options = {}) {
  if (!state.token) return null;
  if (state.casesLoadingPromise) return state.casesLoadingPromise;
  const request = (async () => {
    const data = await api("/api/cases");
    applyCasesResponse(data);
    writeCasesCache();
    if (options.rerender && typeof OJApp.renderCurrentView === "function") OJApp.renderCurrentView();
    return data;
  })();
  state.casesLoadingPromise = request;
  try {
    return await request;
  } finally {
    if (state.casesLoadingPromise === request) state.casesLoadingPromise = null;
  }
}

async function refreshTestSets(options = {}) {
  if (!state.token) return null;
  if (state.testSetsLoadingPromise) return state.testSetsLoadingPromise;
  const request = (async () => {
    const data = await api("/api/test-sets");
    applyTestSetsResponse(data);
    if (options.rerender && typeof OJApp.renderCurrentView === "function") OJApp.renderCurrentView();
    return data;
  })();
  state.testSetsLoadingPromise = request;
  try {
    return await request;
  } finally {
    if (state.testSetsLoadingPromise === request) state.testSetsLoadingPromise = null;
  }
}

async function refreshSubmissions(options = {}) {
  if (!state.token) return;
  if (options.resetPage) state.submissionView.page = 1;
  if (Number.isFinite(Number(options.page))) state.submissionView.page = Math.max(1, Number(options.page));
  if (Number.isFinite(Number(options.perPage))) state.submissionView.perPage = Math.max(1, Number(options.perPage));
  const requestId = (state.submissionsRequestId || 0) + 1;
  state.submissionsRequestId = requestId;
  if (options.clearItems) state.submissions = [];
  const request = (async () => {
    const data = await api(submissionListUrl());
    if (requestId !== state.submissionsRequestId) return data;
    applySubmissionListResponse(data);
    writeSubmissionSummaryCache();
    if (state.route.name === "submissions" && typeof OJApp.renderSubmissionTable === "function") OJApp.renderSubmissionTable();
    else if (state.route.name === "overview" && typeof OJApp.renderOverview === "function") OJApp.renderOverview();
    return data;
  })();
  state.submissionsLoadingPromise = request;
  if (state.route.name === "submissions" && typeof OJApp.renderSubmissionTable === "function") OJApp.renderSubmissionTable();
  try {
    return await request;
  } finally {
    if (state.submissionsRequestId === requestId) state.submissionsLoadingPromise = null;
    if (state.route.name === "submissions" && typeof OJApp.renderSubmissionTable === "function") OJApp.renderSubmissionTable();
  }
}

async function refreshLeaderboard(options = {}) {
  if (!state.token) return;
  const request = (async () => {
    const data = await api(leaderboardUrl(options.limit));
    applyLeaderboardResponse(data);
    writeLeaderboardCache();
    if (typeof OJApp.renderSidebarLeaderboard === "function") OJApp.renderSidebarLeaderboard();
    if (options.rerenderShell && typeof OJApp.renderShell === "function") OJApp.renderShell();
    return data;
  })();
  state.leaderboardLoadingPromise = request;
  try {
    return await request;
  } finally {
    if (state.leaderboardLoadingPromise === request) state.leaderboardLoadingPromise = null;
  }
}

async function maybeRefreshLeaderboard(options = {}) {
  if (!state.token || state.leaderboardLoadingPromise) return null;
  const maxAgeMs = Math.max(1000, Number(options.maxAgeMs) || 120000);
  const fresh = leaderboardCacheFresh(maxAgeMs);
  if (!options.force && fresh) return null;
  return refreshLeaderboard(options);
}

  Object.assign(OJApp, {
    applyBootstrapResponse,
    loadInitialData,
    refreshCases,
    refreshTestSets,
    refreshSubmissions,
    refreshLeaderboard,
    maybeRefreshLeaderboard,
  });
})();
