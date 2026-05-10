import axios from 'axios';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
export const API = `${BACKEND_URL}/api`;

export const api = axios.create({ baseURL: API, timeout: 90000 });

api.interceptors.request.use((config) => {
  const token = localStorage.getItem('triage_token');
  if (token) config.headers.Authorization = `Bearer ${token}`;
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
