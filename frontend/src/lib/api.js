import axios from 'axios';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
export const API = `${BACKEND_URL}/api`;

// ---------------------------------------------------------------------------
// Proxy routing params (e.g. "?app=<uuid>")
// ---------------------------------------------------------------------------
// Some deployment proxies (e.g. solution3.demopersistent.com) use query-string
// routing. The browser drops the query string when fetching sub-resources,
// which causes 503s on /api/* and /static/* requests. To keep API calls
// working we capture the params present on initial page load and replay them
// on every outgoing request.
const INITIAL_QUERY = (() => {
  try {
    return new URLSearchParams(window.location.search);
  } catch {
    return new URLSearchParams();
  }
})();

export const getRoutingQueryString = () => {
  const s = INITIAL_QUERY.toString();
  return s ? `?${s}` : '';
};

export const api = axios.create({ baseURL: API, timeout: 90000 });

api.interceptors.request.use((config) => {
  const token = localStorage.getItem('triage_token');
  if (token) config.headers.Authorization = `Bearer ${token}`;

  // Merge proxy routing params into config.params without overriding any
  // request-specific value the caller already supplied.
  if (INITIAL_QUERY.toString()) {
    const merged = { ...config.params };
    INITIAL_QUERY.forEach((value, key) => {
      if (merged[key] === undefined) merged[key] = value;
    });
    config.params = merged;
  }
  return config;
});

api.interceptors.response.use(
  (r) => r,
  (err) => {
    if (err?.response?.status === 401 && !window.location.pathname.startsWith('/login')) {
      localStorage.removeItem('triage_token');
      localStorage.removeItem('triage_user');
      window.location.href = '/login';
    }
    return Promise.reject(err);
  }
);

// Auth
export const login = (email, password) => api.post('/auth/login', { email, password }).then(r => r.data);
export const me = () => api.get('/auth/me').then(r => r.data);
export const listUsers = () => api.get('/auth/users').then(r => r.data);
export const fetchSystemLLM = () => api.get('/system/llm').then(r => r.data);

// Alerts
export const fetchAlerts = (status) => api.get('/alerts', { params: status ? { status } : {} }).then(r => r.data);
export const fetchUnattended = () => api.get('/alerts/unattended').then(r => r.data);
export const seedData = () => api.post('/seed').then(r => r.data);
export const ageAlerts = () => api.post('/demo/age-alerts').then(r => r.data);
export const simulateAlert = () => api.post('/alerts/simulate').then(r => r.data);
export const resolveAlerts = (alert_ids) => api.post('/alerts/resolve-bulk', { alert_ids }).then(r => r.data);

// Triage
export const runTriage = (alert_ids) => api.post('/triage', { alert_ids }).then(r => r.data);

// Incidents
export const fetchIncidents = (scope) => api.get('/incidents', { params: scope ? { scope } : {} }).then(r => r.data);
export const fetchIncident = (id) => api.get(`/incidents/${id}`).then(r => r.data);
export const pickupIncident = (id) => api.post(`/incidents/${id}/pickup`).then(r => r.data);
export const addCollaborator = (id, email) => api.post(`/incidents/${id}/collaborators`, { email }).then(r => r.data);
export const postUpdate = (id, text) => api.post(`/incidents/${id}/updates`, { text }).then(r => r.data);
export const resolveIncident = (id) => api.post(`/incidents/${id}/resolve`).then(r => r.data);

// Chat
export const fetchChat = (id) => api.get(`/incidents/${id}/chat`).then(r => r.data);
export const sendChat = (id, text) => api.post(`/incidents/${id}/chat`, { text }).then(r => r.data);

// Sources
export const fetchSources = () => api.get('/sources').then(r => r.data);
export const addSource = (data) => api.post('/sources', data).then(r => r.data);
export const deleteSource = (id) => api.delete(`/sources/${id}`).then(r => r.data);
export const toggleSource = (id) => api.patch(`/sources/${id}`).then(r => r.data);

// Analytics
export const fetchAnalytics = () => api.get('/analytics/summary').then(r => r.data);

// SonarQube — Code Quality issue workflow
export const fetchSonarIssue = (key) =>
  api.get(`/sonarqube/issues/${key}`).then(r => r.data);
export const claimSonarIssue = (key) =>
  api.post(`/sonarqube/issues/${key}/claim`).then(r => r.data);
export const assignSonarIssue = (key, email) =>
  api.post(`/sonarqube/issues/${key}/assign`, { email }).then(r => r.data);
export const updateSonarIssueStatus = (key, status) =>
  api.patch(`/sonarqube/issues/${key}/status`, { status }).then(r => r.data);

// SonarQube AI remediation assistant
export const fetchSonarIssueChat = (key) =>
  api.get(`/sonarqube/issues/${key}/chat`).then(r => r.data);
export const sendSonarIssueChat = (key, text, intent) =>
  api.post(`/sonarqube/issues/${key}/chat`, intent ? { text, intent } : { text }).then(r => r.data);

// SonarQube — F-02 enhanced dashboard
/** Generate a fix proposal (explanation + unified diff + confidence) for an issue. */
export const generateSonarFix = (key) =>
  api.post(`/sonarqube/issues/${key}/generate-fix`).then(r => r.data);
/** List comments on a SonarQube issue. */
export const fetchSonarIssueComments = (key) =>
  api.get(`/sonarqube/issues/${key}/comments`).then(r => r.data);
/** Add a comment to a SonarQube issue. */
export const addSonarIssueComment = (key, text) =>
  api.post(`/sonarqube/issues/${key}/comments`, { text }).then(r => r.data);
/** 7-day mock trend (bugs/vulns/smells per day). */
export const fetchSonarTrend = (days = 7) =>
  api.get(`/sonarqube/trend`, { params: { days } }).then(r => r.data);
/** Tells the UI whether the backend is on mock data or a live SonarQube instance. */
export const fetchSonarConfig = () =>
  api.get('/sonarqube/config').then(r => r.data);

// F-01 — CI/CD tools & deployment correlation
export const fetchCICDTools = () => api.get('/cicd/tools').then(r => r.data);
export const addCICDTool = (data) => api.post('/cicd/tools', data).then(r => r.data);
export const updateCICDTool = (id, data) => api.patch(`/cicd/tools/${id}`, data).then(r => r.data);
export const deleteCICDTool = (id) => api.delete(`/cicd/tools/${id}`).then(r => r.data);
export const testCICDTool = (id) => api.post(`/cicd/tools/${id}/test`).then(r => r.data);
export const syncAllCICD = () => api.post('/cicd/sync-all').then(r => r.data);
export const fetchIncidentDeployments = (id, params = {}) =>
  api.get(`/incidents/${id}/deployments`, { params }).then(r => r.data);

// F-02 — Predictive Triage
export const triggerPredictiveTriage = () => api.post('/predictive-triage').then(r => r.data);
export const fetchPredictiveIncidents = (params = {}) =>
  api.get('/predictive-incidents', { params }).then(r => r.data);
export const fetchPredictiveSummary = () =>
  api.get('/predictive-services/summary').then(r => r.data);
export const fetchPredictiveTrend = (id, points = 120) =>
  api.get(`/predictive-incidents/${id}/trend`, { params: { points } }).then(r => r.data);
export const resolvePredictiveIncident = (id) =>
  api.patch(`/predictive-incidents/${id}/resolve`).then(r => r.data);
export const acknowledgePredictiveIncident = (id) =>
  api.patch(`/predictive-incidents/${id}/acknowledge`).then(r => r.data);

// WebSocket URL helper for predictive alerts (browser opens this directly)
export const predictiveWSUrl = () => {
  const base = (process.env.REACT_APP_BACKEND_URL || '').replace(/^http/, 'ws');
  const token = localStorage.getItem('triage_token') || '';
  return `${base}/api/ws/predictive-alerts${token ? `?token=${encodeURIComponent(token)}` : ''}`;
};
