import { useState, useCallback, useEffect } from 'react';
import { api } from '../lib/api';

/**
 * Custom hook for fetching SonarQube data
 * Uses the shared `api` axios instance so we hit REACT_APP_BACKEND_URL/api
 * with the auth interceptor — never a hardcoded localhost URL.
 *
 * Also pulls the F-02 enhancements (7-day trend + source config) in the same
 * round-trip so the dashboard renders the sparkline + LIVE/MOCK badge
 * without a second render.
 *
 * @returns {object} - { summary, issues, qualityGate, trend, config, loading, error, refetch }
 */
export const useSonarQubeData = () => {
  const [summary, setSummary] = useState(null);
  const [issues, setIssues] = useState(null);
  const [qualityGate, setQualityGate] = useState(null);
  const [trend, setTrend] = useState(null);
  const [config, setConfig] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const fetchData = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);

      // Fetch all SonarQube data in parallel via the shared api client.
      // Trend + config are best-effort — if they 401/500 we still show the
      // rest of the dashboard.
      const [summaryRes, issuesRes, qualityGateRes, trendRes, configRes] = await Promise.all([
        api.get('/sonarqube/summary'),
        api.get('/sonarqube/issues'),
        api.get('/sonarqube/quality-gate'),
        api.get('/sonarqube/trend', { params: { days: 7 } }).catch(() => ({ data: null })),
        api.get('/sonarqube/config').catch(() => ({ data: null })),
      ]);

      setSummary(summaryRes.data);
      setIssues(issuesRes.data);
      setQualityGate(qualityGateRes.data);
      setTrend(trendRes.data);
      setConfig(configRes.data);
    } catch (fetchError) {
      const status = fetchError?.response?.status;
      const detail = fetchError?.response?.data?.detail;
      const errorMessage = detail
        ? `Failed to fetch code quality data (${status || 'network'}: ${detail})`
        : 'Failed to fetch code quality data';
      setError(errorMessage);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  return {
    summary,
    issues,
    qualityGate,
    trend,
    config,
    loading,
    error,
    refetch: fetchData,
  };
};
