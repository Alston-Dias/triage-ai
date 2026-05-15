import React, { useState, useEffect, useMemo } from 'react';
import { useSonarQubeData } from '../hooks/useSonarQubeData';
import { RefreshCw, AlertCircle, CheckCircle2, XCircle, Code2, Bug, Shield, Sparkles, TrendingUp, Copy, User, Search, Filter } from 'lucide-react';
import { Card } from '../components/ui/card';
import { Badge } from '../components/ui/badge';
import IssueDetailSheet from '../components/IssueDetailSheet';
import SonarSummaryBar from '../components/SonarSummaryBar';
import CodeQualityScansPanel from '../components/CodeQualityScansPanel';
import { Toaster } from 'sonner';
import { listUsers } from '../lib/api';
import { severityBucket, BUCKET_BADGE_CLASS, BUCKET_LABEL } from '../lib/severity';

/**
 * MetricCard - Displays a single quality metric
 */
const MetricCard = ({ title, value, rating, label, suffix, showProgress, progressValue, icon: Icon }) => {
  const getRatingColor = (rating) => {
    const colors = {
      'A': 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30',
      'B': 'bg-lime-500/10 text-lime-400 border-lime-500/30',
      'C': 'bg-yellow-500/10 text-yellow-400 border-yellow-500/30',
      'D': 'bg-orange-500/10 text-orange-400 border-orange-500/30',
      'E': 'bg-red-500/10 text-red-400 border-red-500/30'
    };
    return colors[rating] || colors['A'];
  };

  const getProgressColor = (value, isInverse = false) => {
    if (isInverse) {
      // For duplications - lower is better
      if (value <= 3) return 'bg-emerald-500';
      if (value <= 5) return 'bg-yellow-500';
      return 'bg-red-500';
    } else {
      // For coverage - higher is better
      if (value >= 80) return 'bg-emerald-500';
      if (value >= 70) return 'bg-yellow-500';
      return 'bg-red-500';
    }
  };

  return (
    <Card className="bg-[#0d0d0d] border-[#1f1f1f] p-5 hover:border-[#D4AF37]/30 transition-all">
      <div className="flex items-start justify-between mb-3">
        <div className="flex items-center gap-2">
          {Icon && <Icon size={16} className="text-neutral-500" />}
          <span className="text-xs font-medium text-neutral-400 uppercase tracking-wider">{title}</span>
        </div>
        {rating && (
          <Badge className={`${getRatingColor(rating)} border text-xs font-bold px-2 py-0.5`}>
            {rating}
          </Badge>
        )}
      </div>
      <div className="text-3xl font-bold text-white mb-2">
        {value}{suffix || ''}
      </div>
      {showProgress && (
        <div className="h-1.5 bg-[#161616] rounded-full overflow-hidden mb-2">
          <div 
            className={`h-full ${getProgressColor(progressValue || value, title === 'Duplications')} transition-all duration-700`}
            style={{ width: `${Math.min(progressValue || value, 100)}%` }}
          />
        </div>
      )}
      <div className="text-xs text-neutral-500">{label}</div>
    </Card>
  );
};

/**
 * QualityMetrics - Grid of quality metric cards
 */
const QualityMetrics = ({ metrics }) => {
  if (!metrics) return null;

  const metricsList = [
    {
      title: 'Bugs',
      value: metrics.bugs?.value || 0,
      rating: metrics.bugs?.rating,
      label: 'Issues Found',
      icon: Bug
    },
    {
      title: 'Vulnerabilities',
      value: metrics.vulnerabilities?.value || 0,
      rating: metrics.vulnerabilities?.rating,
      label: 'Security Issues',
      icon: Shield
    },
    {
      title: 'Code Smells',
      value: metrics.codeSmells?.value || 0,
      rating: metrics.codeSmells?.rating,
      label: 'Maintainability',
      icon: Sparkles
    },
    {
      title: 'Coverage',
      value: metrics.coverage?.value || 0,
      rating: null,
      label: metrics.coverage?.percentage || '0%',
      suffix: '%',
      showProgress: true,
      progressValue: metrics.coverage?.value,
      icon: TrendingUp
    },
    {
      title: 'Duplications',
      value: metrics.duplications?.value || 0,
      rating: null,
      label: metrics.duplications?.percentage || '0%',
      suffix: '%',
      showProgress: true,
      progressValue: metrics.duplications?.value,
      icon: Copy
    },
    {
      title: 'Lines of Code',
      value: metrics.lines?.value?.toLocaleString() || 0,
      rating: null,
      label: 'Total Lines',
      icon: Code2
    }
  ];

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
      {metricsList.map((metric) => (
        <MetricCard key={metric.title} {...metric} />
      ))}
    </div>
  );
};

/**
 * IssueItem - Single code quality issue (clickable → opens detail sheet)
 */
const IssueItem = ({ issue, onClick }) => {
  const getTypeColor = (type) => {
    const colors = {
      'BUG': 'bg-red-500/10 text-red-400 border-red-500/30',
      'VULNERABILITY': 'bg-orange-500/10 text-orange-400 border-orange-500/30',
      'CODE_SMELL': 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30',
      'SECURITY_HOTSPOT': 'bg-blue-500/10 text-blue-400 border-blue-500/30'
    };
    return colors[type] || colors['CODE_SMELL'];
  };

  const getSeverityColor = (severity) => {
    const colors = {
      'BLOCKER': 'bg-red-600/20 text-red-300 border-red-600/40',
      'CRITICAL': 'bg-orange-600/20 text-orange-300 border-orange-600/40',
      'MAJOR': 'bg-yellow-600/20 text-yellow-300 border-yellow-600/40',
      'MINOR': 'bg-blue-600/20 text-blue-300 border-blue-600/40',
      'INFO': 'bg-neutral-600/20 text-neutral-300 border-neutral-600/40'
    };
    return colors[severity] || colors['INFO'];
  };

  const getStatusColor = (status) => {
    const colors = {
      'OPEN': 'bg-neutral-500/10 text-neutral-300 border-neutral-500/30',
      'CLAIMED': 'bg-blue-500/10 text-blue-300 border-blue-500/30',
      'IN_PROGRESS': 'bg-[#D4AF37]/15 text-[#D4AF37] border-[#D4AF37]/40',
      'FIXED': 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30',
      'WONT_FIX': 'bg-slate-500/15 text-slate-300 border-slate-500/40'
    };
    return colors[status] || colors['OPEN'];
  };

  return (
    <button
      type="button"
      onClick={() => onClick(issue.key)}
      data-testid={`issue-row-${issue.key}`}
      className="w-full text-left border border-[#1f1f1f] rounded-lg p-4 hover:border-[#D4AF37]/40 hover:bg-[#D4AF37]/[0.03] transition-all bg-[#0d0d0d] focus:outline-none focus:ring-1 focus:ring-[#D4AF37]/40"
    >
      <div className="flex items-center gap-2 mb-3 flex-wrap">
        <Badge className={`${getTypeColor(issue.type)} border text-[10px] font-semibold px-2 py-0.5`}>
          {issue.type.replace('_', ' ')}
        </Badge>
        <Badge className={`${getSeverityColor(issue.severity)} border text-[10px] font-semibold px-2 py-0.5`}>
          {issue.severity}
        </Badge>
        {(() => {
          const b = severityBucket(issue.severity);
          return (
            <Badge
              className={`${BUCKET_BADGE_CLASS[b]} border text-[10px] font-semibold px-2 py-0.5`}
              data-testid={`issue-row-bucket-${issue.key}`}
              title={`Simplified bucket — ${BUCKET_LABEL[b]}`}
            >
              {BUCKET_LABEL[b]}
            </Badge>
          );
        })()}
        <Badge className={`${getStatusColor(issue.status)} border text-[10px] font-bold px-2 py-0.5`}>
          {issue.status?.replace('_', ' ') || 'OPEN'}
        </Badge>
        {issue.assignee && (
          <Badge className="bg-[#161616] text-neutral-300 border-[#262626] border text-[10px] px-2 py-0.5 inline-flex items-center gap-1">
            <User size={10} />
            {issue.assignee.split('@')[0]}
          </Badge>
        )}
      </div>
      <div className="text-sm text-white font-medium mb-3">{issue.title || issue.message}</div>
      <div className="flex items-center gap-4 text-xs text-neutral-500">
        <span className="flex items-center gap-1">
          <Code2 size={12} />
          {issue.component}
        </span>
        {issue.line && (
          <span>Line {issue.line}</span>
        )}
        <span className="ml-auto">{issue.effort}</span>
      </div>
    </button>
  );
};

/**
 * IssuesList - List of code quality issues with filter bar + search + summary chips.
 *
 * Filtering is done client-side (the dataset is small and the UX needs to be
 * snappy). The backend `/sonarqube/issues` endpoint also accepts equivalent
 * query params for future API consumers / when the dataset grows.
 */
const IssuesList = ({
  issuesData,
  onIssueClick,
  users,
  filters,
  onFilterChange,
  filteredIssues,
}) => {
  if (!issuesData) return null;

  const { total, breakdown } = issuesData;
  const visible = filteredIssues || [];

  const stats = [
    { label: 'Bugs', value: breakdown?.bugs || 0, color: 'text-red-400' },
    { label: 'Vulnerabilities', value: breakdown?.vulnerabilities || 0, color: 'text-orange-400' },
    { label: 'Code Smells', value: breakdown?.codeSmells || 0, color: 'text-emerald-400' },
    { label: 'Hotspots', value: breakdown?.securityHotspots || 0, color: 'text-blue-400' }
  ];

  const selectClass =
    'bg-[#0a0a0a] border border-[#262626] focus:border-[#D4AF37] text-xs text-neutral-200 rounded-md px-2 py-1.5 outline-none';

  const handle = (key) => (e) => onFilterChange({ ...filters, [key]: e.target.value });

  // Build assignee dropdown options from issues that actually have assignees + the user dir.
  const knownAssignees = Array.from(new Set([
    ...visible.map((i) => i.assignee).filter(Boolean),
    ...(users || []).map((u) => u.email),
  ]));

  return (
    <Card className="bg-[#0d0d0d] border-[#1f1f1f] p-6">
      <div className="flex items-center justify-between mb-4 gap-3 flex-wrap">
        <h3 className="font-display font-bold text-lg">
          Issues ({visible.length}
          {visible.length !== total && <span className="text-neutral-500 font-normal"> of {total}</span>})
        </h3>
      </div>

      {/* Filter + search strip */}
      <div
        className="flex items-center gap-2 flex-wrap mb-5 p-3 rounded-lg border border-[#1f1f1f] bg-[#0A0A0A]"
        data-testid="sonar-filter-strip"
      >
        <div className="relative flex-1 min-w-[200px]">
          <Search size={12} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-neutral-500" />
          <input
            type="text"
            placeholder="Search by title, file, rule…"
            value={filters.q}
            onChange={handle('q')}
            data-testid="sonar-search-input"
            className="w-full pl-7 pr-3 py-1.5 bg-[#0a0a0a] border border-[#262626] focus:border-[#D4AF37] outline-none rounded-md text-xs text-white"
          />
        </div>
        <Filter size={12} className="text-neutral-500 ml-1" />
        <select value={filters.bucket} onChange={handle('bucket')} data-testid="sonar-filter-bucket" className={selectClass}>
          <option value="">All severities</option>
          <option value="HIGH">High</option>
          <option value="MEDIUM">Medium</option>
          <option value="LOW">Low</option>
        </select>
        <select value={filters.type} onChange={handle('type')} data-testid="sonar-filter-type" className={selectClass}>
          <option value="">All types</option>
          <option value="BUG">Bug</option>
          <option value="VULNERABILITY">Vulnerability</option>
          <option value="CODE_SMELL">Code Smell</option>
          <option value="SECURITY_HOTSPOT">Security Hotspot</option>
        </select>
        <select value={filters.status} onChange={handle('status')} data-testid="sonar-filter-status" className={selectClass}>
          <option value="">All statuses</option>
          <option value="OPEN">Open</option>
          <option value="CLAIMED">Claimed</option>
          <option value="IN_PROGRESS">In Progress</option>
          <option value="FIXED">Fixed</option>
          <option value="WONT_FIX">Won't Fix</option>
        </select>
        <select value={filters.assignee} onChange={handle('assignee')} data-testid="sonar-filter-assignee" className={selectClass}>
          <option value="">All assignees</option>
          <option value="unassigned">Unassigned</option>
          {knownAssignees.map((email) => (
            <option key={email} value={email}>{email}</option>
          ))}
        </select>
        {(filters.q || filters.bucket || filters.type || filters.status || filters.assignee) && (
          <button
            type="button"
            onClick={() => onFilterChange({ q: '', bucket: '', type: '', status: '', assignee: '' })}
            data-testid="sonar-filter-clear"
            className="text-[11px] text-neutral-400 hover:text-white underline underline-offset-2"
          >
            Clear
          </button>
        )}
      </div>

      <div className="grid grid-cols-4 gap-4 mb-6 p-4 bg-[#0A0A0A] rounded-lg border border-[#1f1f1f]">
        {stats.map((stat) => (
          <div key={stat.label} className="text-center">
            <div className={`text-2xl font-bold ${stat.color}`}>{stat.value}</div>
            <div className="text-xs text-neutral-500 mt-1">{stat.label}</div>
          </div>
        ))}
      </div>

      <div className="space-y-3" data-testid="sonar-issues-list">
        {visible.length === 0 && (
          <div className="text-center text-xs text-neutral-500 py-8">
            No issues match the current filters.
          </div>
        )}
        {visible.map((issue) => (
          <IssueItem key={issue.key} issue={issue} onClick={onIssueClick} />
        ))}
      </div>
    </Card>
  );
};

/**
 * QualityGate - Quality gate status and conditions
 */
const QualityGate = ({ qualityGateData }) => {
  if (!qualityGateData) return null;

  const { qualityGate, conditions } = qualityGateData;
  const isPassed = qualityGate.status === 'PASSED';

  return (
    <Card className="bg-[#0d0d0d] border-[#1f1f1f] p-6">
      <div className="flex items-center justify-between mb-6">
        <h3 className="font-display font-bold text-lg">Quality Gate</h3>
        <Badge className={`${isPassed ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30' : 'bg-red-500/10 text-red-400 border-red-500/30'} border text-sm font-bold px-3 py-1`}>
          {qualityGate.status}
        </Badge>
      </div>

      <div className="space-y-3">
        {conditions.map((condition, idx) => (
          <div 
            key={idx}
            className={`flex items-center justify-between p-4 rounded-lg border ${condition.status === 'PASSED' ? 'border-emerald-500/20 bg-emerald-500/5' : 'border-red-500/20 bg-red-500/5'}`}
          >
            <div className="flex items-center gap-3">
              {condition.status === 'PASSED' ? (
                <CheckCircle2 size={18} className="text-emerald-400" />
              ) : (
                <XCircle size={18} className="text-red-400" />
              )}
              <div>
                <div className="text-sm font-medium text-white">
                  {condition.metric.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase())}
                </div>
                <div className="text-xs text-neutral-500">
                  {condition.operator === 'LESS_THAN' ? 'Must be ≥' : 'Must be ≤'} {condition.threshold}
                </div>
              </div>
            </div>
            <div className="text-xl font-bold text-[#D4AF37]">{condition.actualValue}</div>
          </div>
        ))}
      </div>
    </Card>
  );
};

/**
 * CodeQuality Page - Main SonarQube dashboard
 */
export default function CodeQuality() {
  const { summary, issues, qualityGate, trend, config, loading, error, refetch } = useSonarQubeData();
  const [activeIssueKey, setActiveIssueKey] = useState(null);
  const [sheetOpen, setSheetOpen] = useState(false);
  const [users, setUsers] = useState([]);
  const [filters, setFilters] = useState({
    q: '',
    bucket: '',
    type: '',
    status: '',
    assignee: '',
  });

  // Fetch user directory once for the assignee filter dropdown. Best-effort.
  useEffect(() => {
    listUsers().then(setUsers).catch(() => setUsers([]));
  }, []);

  // Client-side filter pipeline. Kept in CodeQuality so the SonarSummaryBar
  // can always show the *unfiltered* project totals.
  const filteredIssues = useMemo(() => {
    const all = issues?.issues || [];
    const q = filters.q.trim().toLowerCase();
    return all.filter((it) => {
      if (filters.bucket && severityBucket(it.severity) !== filters.bucket) return false;
      if (filters.type && (it.type || '').toUpperCase() !== filters.type) return false;
      if (filters.status && (it.status || '').toUpperCase() !== filters.status) return false;
      if (filters.assignee) {
        const a = (it.assignee || '').toLowerCase();
        if (filters.assignee === 'unassigned' ? !!a : a !== filters.assignee.toLowerCase()) return false;
      }
      if (q) {
        const hay = [it.title, it.message, it.component, it.rule, it.description]
          .filter(Boolean).join(' ').toLowerCase();
        if (!hay.includes(q)) return false;
      }
      return true;
    });
  }, [issues, filters]);

  const openIssue = (key) => {
    setActiveIssueKey(key);
    setSheetOpen(true);
  };
  const onSheetOpenChange = (next) => {
    setSheetOpen(next);
    if (!next) {
      // Refresh list to pick up latest assignee/status mutations.
      refetch();
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[400px]">
        <div className="text-center">
          <RefreshCw className="w-8 h-8 animate-spin text-[#D4AF37] mx-auto mb-3" />
          <div className="text-sm text-neutral-400">Loading code quality metrics...</div>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex items-center justify-center min-h-[400px]">
        <Card className="bg-[#0d0d0d] border-red-500/30 p-6 max-w-md">
          <AlertCircle className="w-8 h-8 text-red-400 mx-auto mb-3" />
          <div className="text-center text-sm text-neutral-300">{error}</div>
        </Card>
      </div>
    );
  }

  return (
    <div className="space-y-8 pb-8">
      {/* === Code Quality v2 — user-driven scans + integrations === */}
      <CodeQualityScansPanel />

      <div className="border-t border-[#1f1f1f] pt-6">
        <div className="text-[11px] uppercase tracking-wider text-neutral-500 mb-4 font-semibold">
          Demo project · static SonarQube dashboard
        </div>
      </div>

      {/* Header */}
      <Card className="bg-[#0d0d0d] border-[#1f1f1f] p-6">
        <div className="flex items-center justify-between">
          <div>
            <div className="flex items-center gap-3 mb-2">
              <h2 className="font-display font-bold text-2xl text-white">
                {summary?.projectName || 'TriageAI'}
              </h2>
              <Badge className={`${summary?.qualityGateStatus === 'PASSED' ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30' : 'bg-red-500/10 text-red-400 border-red-500/30'} border font-bold`}>
                {summary?.qualityGateStatus || 'UNKNOWN'}
              </Badge>
            </div>
            <div className="flex items-center gap-4 text-xs text-neutral-500">
              <span>📦 {summary?.projectKey}</span>
              <span>🔖 v{summary?.version}</span>
              <span>📅 {summary?.analysisDate ? new Date(summary.analysisDate).toLocaleString() : 'N/A'}</span>
            </div>
          </div>
          <button
            onClick={refetch}
            className="flex items-center gap-2 px-4 py-2 bg-[#D4AF37]/10 hover:bg-[#D4AF37]/20 border border-[#D4AF37]/30 rounded-lg text-[#D4AF37] text-sm font-medium transition-all"
          >
            <RefreshCw size={14} />
            Refresh
          </button>
        </div>
      </Card>

      {/* F-02 summary strip: bucket counts + tech debt + 7d sparkline + source badge */}
      <SonarSummaryBar
        buckets={issues?.buckets}
        technicalDebtMinutes={issues?.technical_debt_minutes}
        trend={trend}
        config={config}
      />

      {/* Metrics Grid */}
      <QualityMetrics metrics={summary?.metrics} />

      {/* Issues List */}
      <IssuesList
        issuesData={issues}
        filteredIssues={filteredIssues}
        users={users}
        filters={filters}
        onFilterChange={setFilters}
        onIssueClick={openIssue}
      />

      {/* Quality Gate */}
      <QualityGate qualityGateData={qualityGate} />

      {/* Info Banner */}
      <Card className="bg-[#D4AF37]/5 border-[#D4AF37]/20 p-4">
        <div className="text-xs text-neutral-300 text-center">
          💡 Code quality metrics help identify potential root causes of incidents. 
          Track technical debt and maintain high code standards.
        </div>
      </Card>

      {/* Detail drawer */}
      <Toaster theme="dark" position="bottom-right" />
      <IssueDetailSheet
        issueKey={activeIssueKey}
        open={sheetOpen}
        onOpenChange={onSheetOpenChange}
        onChanged={refetch}
      />
    </div>
  );
}
