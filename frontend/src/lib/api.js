import axios from 'axios';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
export const API = `${BACKEND_URL}/api`;

export const api = axios.create({ baseURL: API, timeout: 60000 });

export const fetchAlerts = (status) => api.get('/alerts', { params: status ? { status } : {} }).then(r => r.data);
export const fetchIncidents = () => api.get('/incidents').then(r => r.data);
export const fetchIncident = (id) => api.get(`/incidents/${id}`).then(r => r.data);
export const fetchAnalytics = () => api.get('/analytics/summary').then(r => r.data);
export const runTriage = (alert_ids) => api.post('/triage', { alert_ids }).then(r => r.data);
export const resolveAlerts = (alert_ids) => api.post('/alerts/resolve-bulk', { alert_ids }).then(r => r.data);
export const seedData = () => api.post('/seed').then(r => r.data);
export const simulateAlert = () => api.post('/alerts/simulate').then(r => r.data);
