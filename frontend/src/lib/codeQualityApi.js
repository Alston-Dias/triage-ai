// Code Quality v2 API client
// Talks to the /api/code-quality/* endpoints in backend/code_quality_v2.py.
import { api } from './api';

// -------- Scans --------
export const cqListScans = () => api.get('/code-quality/scans').then((r) => r.data);

export const cqGetScan = (id) => api.get(`/code-quality/scans/${id}`).then((r) => r.data);

export const cqDeleteScan = (id) => api.delete(`/code-quality/scans/${id}`).then((r) => r.data);

export const cqGetScanIssues = (id, filters = {}) =>
  api.get(`/code-quality/scans/${id}/issues`, { params: filters }).then((r) => r.data);

export const cqScanGithub = ({ repo_url, branch, github_token }) =>
  api
    .post('/code-quality/scans/github', { repo_url, branch: branch || null, github_token: github_token || null })
    .then((r) => r.data);

export const cqScanUpload = (file, onProgress) => {
  const form = new FormData();
  form.append('file', file);
  return api
    .post('/code-quality/scans/upload', form, {
      headers: { 'Content-Type': 'multipart/form-data' },
      onUploadProgress: (e) => {
        if (onProgress && e.total) onProgress(Math.round((e.loaded * 100) / e.total));
      },
      timeout: 300000,
    })
    .then((r) => r.data);
};

// -------- Integrations --------
export const cqListIntegrations = () => api.get('/code-quality/integrations').then((r) => r.data);

export const cqCreateIntegration = (payload) =>
  api.post('/code-quality/integrations', payload).then((r) => r.data);

export const cqDeleteIntegration = (id) =>
  api.delete(`/code-quality/integrations/${id}`).then((r) => r.data);

export const cqSyncIntegration = (id) =>
  api.post(`/code-quality/integrations/${id}/sync`).then((r) => r.data);

// -------- Issues --------
export const cqGetIssue = (id) => api.get(`/code-quality/issues/${id}`).then((r) => r.data);

export const cqGenerateFix = (issueId, { github_repo, github_token, branch, user_snippet } = {}) =>
  api
    .post(`/code-quality/issues/${issueId}/fix`, {
      github_repo: github_repo || null,
      github_token: github_token || null,
      branch: branch || null,
      user_snippet: user_snippet || null,
    }, { timeout: 180000 })
    .then((r) => r.data);

// -------- Helpers --------
export const SEVERITY_COLORS = {
  blocker: 'bg-red-500/15 text-red-300 border-red-500/40',
  critical: 'bg-red-500/15 text-red-300 border-red-500/40',
  major: 'bg-orange-500/15 text-orange-300 border-orange-500/40',
  minor: 'bg-yellow-500/15 text-yellow-300 border-yellow-500/40',
  info: 'bg-sky-500/15 text-sky-300 border-sky-500/40',
};

export const TYPE_COLORS = {
  bug: 'bg-red-500/10 text-red-400 border-red-500/30',
  vulnerability: 'bg-purple-500/10 text-purple-400 border-purple-500/30',
  code_smell: 'bg-amber-500/10 text-amber-400 border-amber-500/30',
  security_hotspot: 'bg-pink-500/10 text-pink-400 border-pink-500/30',
};

export const TYPE_LABEL = {
  bug: 'Bug',
  vulnerability: 'Vulnerability',
  code_smell: 'Code Smell',
  security_hotspot: 'Security Hotspot',
};

export const PROVIDER_LABEL = {
  sonarqube: 'SonarQube',
  sonarcloud: 'SonarCloud',
  snyk: 'Snyk',
  github_advanced_security: 'GitHub Advanced Security',
  semgrep: 'Semgrep Cloud',
  custom: 'Custom',
};
