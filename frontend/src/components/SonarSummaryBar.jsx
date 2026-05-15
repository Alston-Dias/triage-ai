import React from 'react';
import { BUCKET_DOT_COLOR, formatEffortMinutes } from '../lib/severity';
import { Clock, Database, Cloud } from 'lucide-react';

/**
 * Compact stats strip rendered just above the issues list on the Code Quality page.
 *
 * Shows:
 *   • Blockers · High · Medium · Low counts (driven by /sonarqube/issues `buckets`)
 *   • Total technical debt
 *   • 7-day total-issues sparkline (inline SVG, no extra deps)
 *   • Source badge — MOCK or LIVE: <url>
 */
function Sparkline({ series }) {
  if (!Array.isArray(series) || series.length === 0) {
    return <div className="text-[10px] text-slate-400">No trend data</div>;
  }
  const values = series.map((s) => s.total || 0);
  const max = Math.max(1, ...values);
  const w = 120;
  const h = 28;
  const step = series.length > 1 ? w / (series.length - 1) : 0;
  const points = values
    .map((v, i) => `${(i * step).toFixed(1)},${(h - (v / max) * h).toFixed(1)}`)
    .join(' ');
  return (
    <svg width={w} height={h} viewBox={`0 0 ${w} ${h}`} aria-label="7-day issue trend">
      <polyline
        fill="none"
        stroke="#0f766e"
        strokeWidth="1.5"
        strokeLinejoin="round"
        strokeLinecap="round"
        points={points}
      />
      {/* dot at the last point for emphasis */}
      <circle
        cx={(values.length - 1) * step}
        cy={h - (values[values.length - 1] / max) * h}
        r="2.2"
        fill="#0f766e"
      />
    </svg>
  );
}

function Stat({ color, label, value, dataTestId }) {
  return (
    <div className="flex items-center gap-2" data-testid={dataTestId}>
      <span
        aria-hidden="true"
        className="h-2.5 w-2.5 rounded-full shrink-0"
        style={{ backgroundColor: color }}
      />
      <div className="leading-tight">
        <div className="text-xs uppercase tracking-wide text-slate-500">{label}</div>
        <div className="text-base font-semibold text-slate-800 tabular-nums">{value}</div>
      </div>
    </div>
  );
}

export default function SonarSummaryBar({
  buckets,
  technicalDebtMinutes,
  trend,
  config,
}) {
  const b = buckets || { BLOCKER: 0, HIGH: 0, MEDIUM: 0, LOW: 0 };
  const isLive = config?.source === 'live';

  return (
    <div
      className="rounded-xl border border-slate-200 bg-white shadow-sm px-4 py-3 flex flex-wrap items-center justify-between gap-x-6 gap-y-3"
      data-testid="sonar-summary-bar"
    >
      <div className="flex items-center gap-6 flex-wrap">
        <Stat
          dataTestId="sonar-stat-blocker"
          color={BUCKET_DOT_COLOR.BLOCKER}
          label="Blockers"
          value={b.BLOCKER ?? 0}
        />
        <Stat
          dataTestId="sonar-stat-high"
          color={BUCKET_DOT_COLOR.HIGH}
          label="High"
          value={b.HIGH ?? 0}
        />
        <Stat
          dataTestId="sonar-stat-medium"
          color={BUCKET_DOT_COLOR.MEDIUM}
          label="Medium"
          value={b.MEDIUM ?? 0}
        />
        <Stat
          dataTestId="sonar-stat-low"
          color={BUCKET_DOT_COLOR.LOW}
          label="Low"
          value={b.LOW ?? 0}
        />
        <div className="h-8 w-px bg-slate-200 hidden md:block" />
        <Stat
          dataTestId="sonar-stat-debt"
          color="#0f766e"
          label="Technical debt"
          value={
            <span className="inline-flex items-center gap-1">
              <Clock className="h-3.5 w-3.5 text-slate-400" />
              {formatEffortMinutes(technicalDebtMinutes)}
            </span>
          }
        />
      </div>

      <div className="flex items-center gap-4">
        <div
          className="flex flex-col items-end"
          data-testid="sonar-trend-sparkline"
          title="Total open issues, last 7 days"
        >
          <span className="text-[10px] uppercase tracking-wide text-slate-500">
            Last 7 days
          </span>
          <Sparkline series={trend?.series} />
        </div>

        <span
          className={[
            'inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-medium',
            isLive
              ? 'border-emerald-200 bg-emerald-50 text-emerald-700'
              : 'border-slate-200 bg-slate-50 text-slate-600',
          ].join(' ')}
          data-testid="sonar-source-badge"
          title={
            isLive
              ? `Live: ${config?.base_url || ''}`
              : 'Backend is serving mock SonarQube data — set SONAR_BASE_URL + SONAR_TOKEN to go live.'
          }
        >
          {isLive ? (
            <Cloud className="h-3.5 w-3.5" />
          ) : (
            <Database className="h-3.5 w-3.5" />
          )}
          {isLive ? 'LIVE' : 'MOCK'}
        </span>
      </div>
    </div>
  );
}
