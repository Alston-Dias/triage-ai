import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { toast, Toaster } from 'sonner';
import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ReferenceLine, ResponsiveContainer,
} from 'recharts';
import {
  ShieldAlert, AlertTriangle, Activity, RefreshCw, CheckCircle2, Clock, Eye,
  TrendingUp, Cpu, MemoryStick, Database, Gauge, ListChecks, Sparkles,
} from 'lucide-react';
import {
  fetchPredictiveIncidents, fetchPredictiveSummary, fetchPredictiveTrend,
  triggerPredictiveTriage, resolvePredictiveIncident, acknowledgePredictiveIncident,
  predictiveWSUrl,
} from '../../lib/api';

const METRIC_LABEL = {
  cpu_usage: 'CPU',
  memory_usage: 'Memory',
  db_connections: 'DB Conns',
  api_latency_ms: 'p95 Latency',
  queue_depth: 'Queue Depth',
};
const METRIC_UNIT = {
  cpu_usage: '%', memory_usage: '%', db_connections: '', api_latency_ms: 'ms', queue_depth: '',
};
const METRIC_ICON = {
  cpu_usage: Cpu, memory_usage: MemoryStick, db_connections: Database,
  api_latency_ms: Gauge, queue_depth: ListChecks,
};

function riskTone(score) {
  if (score >= 80) return { bg: 'bg-[#FF3B30]/10', border: 'border-[#FF3B30]/40', text: 'text-[#FF3B30]', dot: 'bg-[#FF3B30]', label: 'CRITICAL' };
  if (score >= 65) return { bg: 'bg-[#FF9F0A]/10', border: 'border-[#FF9F0A]/40', text: 'text-[#FF9F0A]', dot: 'bg-[#FF9F0A]', label: 'HIGH' };
  if (score >= 50) return { bg: 'bg-[#D4AF37]/10', border: 'border-[#D4AF37]/40', text: 'text-[#D4AF37]', dot: 'bg-[#D4AF37]', label: 'ELEVATED' };
  return { bg: 'bg-[#30D158]/10', border: 'border-[#30D158]/40', text: 'text-[#30D158]', dot: 'bg-[#30D158]', label: 'HEALTHY' };
}

function fmtEta(mins) {
  if (mins == null) return '—';
  if (mins < 60) return `${mins}m`;
  const h = Math.floor(mins / 60);
  const m = mins % 60;
  return m ? `${h}h ${m}m` : `${h}h`;
}

function fmtRelative(iso) {
  if (!iso) return '';
  const diff = (Date.now() - new Date(iso).getTime()) / 60000;
  if (diff < 1) return 'just now';
  if (diff < 60) return `${Math.round(diff)}m ago`;
  return `${Math.round(diff / 60)}h ago`;
}

// ---------------- Subcomponents ----------------

function HighRiskStrip({ summary }) {
  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-3" data-testid="risk-strip">
      {summary.map(s => {
        const tone = riskTone(s.max_risk);
        return (
          <div key={s.service_name} className={`rounded-lg border ${tone.border} ${tone.bg} p-3.5`} data-testid={`risk-card-${s.service_name}`}>
            <div className="flex items-start justify-between">
              <div className="min-w-0">
                <div className="text-[10px] uppercase tracking-wider text-neutral-400">Service</div>
                <div className="font-medium text-sm truncate text-white mt-0.5">{s.service_name}</div>
              </div>
              <div className={`text-xs font-semibold ${tone.text} flex items-center gap-1`}>
                <span className={`w-1.5 h-1.5 rounded-full ${tone.dot} live-dot`} />
                {tone.label}
              </div>
            </div>
            <div className="flex items-end justify-between mt-3">
              <div>
                <div className="text-[10px] text-neutral-500">Risk</div>
                <div className={`font-display font-black text-3xl tracking-tight ${tone.text}`}>{s.max_risk}</div>
              </div>
              <div className="text-right text-[11px] text-neutral-400 leading-tight">
                <div>{s.predictions} prediction{s.predictions === 1 ? '' : 's'}</div>
                <div className="mt-0.5">ETA {fmtEta(s.min_eta)}</div>
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}

function IncidentRow({ inc, active, onSelect, onAck, onResolve }) {
  const tone = riskTone(inc.risk_score);
  const Icon = METRIC_ICON[inc.metric_type] || Activity;
  const unit = METRIC_UNIT[inc.metric_type] || '';
  return (
    <div
      onClick={() => onSelect(inc)}
      data-testid={`prediction-row-${inc.id}`}
      className={`rounded-lg border p-3 cursor-pointer transition-colors ${active
        ? 'border-[#D4AF37]/50 bg-[#D4AF37]/[0.04]'
        : 'border-[#1f1f1f] hover:border-[#2a2a2a] bg-[#0d0d0d]'}`}
    >
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2.5 min-w-0">
          <div className={`w-8 h-8 rounded-md ${tone.bg} border ${tone.border} flex items-center justify-center shrink-0`}>
            <Icon size={15} className={tone.text} strokeWidth={1.75} />
          </div>
          <div className="min-w-0">
            <div className="text-sm font-medium truncate">{inc.service_name}</div>
            <div className="text-[11px] text-neutral-500 truncate">
              {METRIC_LABEL[inc.metric_type] || inc.metric_type} · {inc.current_value}{unit}
              <span className="text-neutral-700"> · baseline </span>
              {inc.expected_value}{unit}
            </div>
          </div>
        </div>
        <div className="text-right shrink-0">
          <div className={`font-display font-black text-xl ${tone.text} leading-none`}>{inc.risk_score}</div>
          <div className="text-[10px] text-neutral-500 mt-0.5">{tone.label}</div>
        </div>
      </div>
      <div className="flex items-center justify-between mt-2.5 text-[11px] text-neutral-500">
        <span className="flex items-center gap-1"><Clock size={11} /> ETA {fmtEta(inc.estimated_time_to_incident)}</span>
        <span>{fmtRelative(inc.created_at)}</span>
      </div>
      {(inc.status === 'open' || inc.status === 'acknowledged') && (
        <div className="flex items-center gap-2 mt-2">
          {inc.status === 'open' && (
            <button
              data-testid={`ack-btn-${inc.id}`}
              onClick={(e) => { e.stopPropagation(); onAck(inc); }}
              className="px-2.5 py-1 rounded-md border border-[#1f1f1f] hover:border-[#D4AF37]/40 hover:text-[#D4AF37] text-[11px] text-neutral-400 transition-colors flex items-center gap-1">
              <Eye size={11} /> Acknowledge
            </button>
          )}
          <button
            data-testid={`resolve-btn-${inc.id}`}
            onClick={(e) => { e.stopPropagation(); onResolve(inc); }}
            className="px-2.5 py-1 rounded-md border border-[#1f1f1f] hover:border-[#30D158]/40 hover:text-[#30D158] text-[11px] text-neutral-400 transition-colors flex items-center gap-1">
            <CheckCircle2 size={11} /> Resolve
          </button>
        </div>
      )}
    </div>
  );
}

function TrendGraph({ trend }) {
  const data = useMemo(() => {
    if (!trend) return [];
    return trend.series.map(s => ({
      t: new Date(s.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      value: s.value,
    }));
  }, [trend]);

  if (!trend) {
    return (
      <div className="h-72 flex items-center justify-center text-sm text-neutral-500">
        Select a prediction to see its trend
      </div>
    );
  }
  const threshold = trend.threshold;
  const tone = riskTone(trend.incident.risk_score);
  return (
    <div>
      <div className="flex items-center justify-between mb-2">
        <div>
          <div className="text-[10px] uppercase tracking-wider text-neutral-500">Metric trend</div>
          <div className="text-sm font-medium">
            {trend.incident.service_name} · {METRIC_LABEL[trend.incident.metric_type] || trend.incident.metric_type}
          </div>
        </div>
        <div className="flex items-center gap-2 text-[11px]">
          <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-sm bg-[#D4AF37]" /> series</span>
          <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-sm bg-[#FF3B30]" /> critical {threshold}{trend.unit}</span>
        </div>
      </div>
      <ResponsiveContainer width="100%" height={260}>
        <AreaChart data={data} margin={{ top: 5, right: 8, left: -10, bottom: 0 }}>
          <defs>
            <linearGradient id="riskFill" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor="#D4AF37" stopOpacity={0.4} />
              <stop offset="95%" stopColor="#D4AF37" stopOpacity={0} />
            </linearGradient>
          </defs>
          <CartesianGrid strokeDasharray="3 3" stroke="#1f1f1f" />
          <XAxis dataKey="t" tick={{ fontSize: 10, fill: '#71717A' }} interval={Math.max(0, Math.floor(data.length / 8))} />
          <YAxis tick={{ fontSize: 10, fill: '#71717A' }} domain={['auto', Math.max(threshold * 1.05, 'auto')]} />
          <Tooltip
            contentStyle={{ background: '#0A0A0A', border: '1px solid #1f1f1f', borderRadius: 6, fontSize: 12 }}
            labelStyle={{ color: '#a3a3a3' }}
            formatter={(v) => [`${v}${trend.unit}`, METRIC_LABEL[trend.incident.metric_type]]}
          />
          <ReferenceLine y={threshold} stroke="#FF3B30" strokeDasharray="4 4" strokeWidth={1.25} />
          <Area type="monotone" dataKey="value" stroke="#D4AF37" strokeWidth={1.75} fillOpacity={1} fill="url(#riskFill)" />
        </AreaChart>
      </ResponsiveContainer>
      <div className="mt-2 flex items-center gap-3 text-[11px] text-neutral-500">
        <span className="flex items-center gap-1"><span className={`w-1.5 h-1.5 rounded-full ${tone.dot}`} />Risk {trend.incident.risk_score}/100</span>
        <span>·</span>
        <span>Anomaly score {trend.incident.anomaly_score?.toFixed?.(3)}</span>
        <span>·</span>
        <span>ETA {fmtEta(trend.incident.estimated_time_to_incident)}</span>
      </div>
    </div>
  );
}

function RecommendationCard({ inc }) {
  if (!inc) return null;
  return (
    <div className="rounded-lg border border-[#1f1f1f] bg-[#0d0d0d] p-4" data-testid="recommendation-card">
      <div className="flex items-center gap-2 mb-2">
        <Sparkles size={14} className="text-[#D4AF37]" />
        <div className="text-[10px] uppercase tracking-wider text-[#D4AF37]">Preventive recommendation · claude-sonnet-4.5</div>
      </div>
      <pre className="text-[12.5px] text-neutral-200 whitespace-pre-wrap leading-relaxed font-mono">
        {inc.recommended_action || '—'}
      </pre>
    </div>
  );
}

function PreventionTimeline({ incidents }) {
  // Sort by ETA (lowest first), then risk
  const items = useMemo(() => {
    const open = incidents.filter(i => i.status === 'open' || i.status === 'acknowledged');
    return [...open].sort((a, b) => {
      const ea = a.estimated_time_to_incident ?? 9999;
      const eb = b.estimated_time_to_incident ?? 9999;
      if (ea !== eb) return ea - eb;
      return b.risk_score - a.risk_score;
    }).slice(0, 8);
  }, [incidents]);
  if (items.length === 0) {
    return <div className="text-xs text-neutral-500 px-1 py-3">No upcoming predicted incidents.</div>;
  }
  return (
    <div className="relative pl-6" data-testid="prevention-timeline">
      <div className="absolute left-2 top-2 bottom-2 w-px bg-[#1f1f1f]" />
      {items.map(inc => {
        const tone = riskTone(inc.risk_score);
        return (
          <div key={inc.id} className="relative py-2.5">
            <span className={`absolute -left-[18px] top-3.5 w-2.5 h-2.5 rounded-full ${tone.dot} border-2 border-[#0A0A0A]`} />
            <div className="flex items-center justify-between gap-3">
              <div className="min-w-0">
                <div className="text-sm font-medium truncate">{inc.service_name}</div>
                <div className="text-[11px] text-neutral-500 truncate">
                  {METRIC_LABEL[inc.metric_type] || inc.metric_type} · ETA {fmtEta(inc.estimated_time_to_incident)}
                </div>
              </div>
              <div className={`text-xs font-semibold ${tone.text}`}>{inc.risk_score}</div>
            </div>
          </div>
        );
      })}
    </div>
  );
}

// ---------------- Main Component ----------------

export default function PredictiveDashboard() {
  const [summary, setSummary] = useState([]);
  const [incidents, setIncidents] = useState([]);
  const [selectedId, setSelectedId] = useState(null);
  const [trend, setTrend] = useState(null);
  const [loading, setLoading] = useState(false);
  const [running, setRunning] = useState(false);
  const wsRef = useRef(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [s, list] = await Promise.all([
        fetchPredictiveSummary(),
        fetchPredictiveIncidents({ status: 'open' }),
      ]);
      setSummary(s);
      setIncidents(list);
      if (!selectedId && list.length > 0) setSelectedId(list[0].id);
    } catch (e) {
      toast.error('Failed to load predictive data');
    } finally {
      setLoading(false);
    }
  }, [selectedId]);

  // Initial load + 30s poll fallback (in case WS misses)
  useEffect(() => {
    load();
    const t = setInterval(load, 30000);
    return () => clearInterval(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // WebSocket
  useEffect(() => {
    let ws;
    try {
      ws = new WebSocket(predictiveWSUrl());
      wsRef.current = ws;
      ws.onmessage = (ev) => {
        try {
          const msg = JSON.parse(ev.data);
          if (msg.event === 'prediction.new') {
            const d = msg.data;
            toast(`${d.service_name} · ${METRIC_LABEL[d.metric_type] || d.metric_type}`, {
              description: `Risk ${d.risk_score}/100 · ETA ${fmtEta(d.estimated_time_to_incident)}`,
              icon: <ShieldAlert size={16} />,
            });
            load();
          } else if (msg.event === 'prediction.resolved') {
            load();
          }
        } catch {}
      };
      ws.onerror = () => { /* silent; we have polling fallback */ };
    } catch {}
    return () => { try { ws && ws.close(); } catch {} };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Load trend when selection changes
  useEffect(() => {
    if (!selectedId) { setTrend(null); return; }
    fetchPredictiveTrend(selectedId).then(setTrend).catch(() => setTrend(null));
  }, [selectedId]);

  const selectedInc = useMemo(
    () => incidents.find(i => i.id === selectedId) || null,
    [incidents, selectedId],
  );

  const handleRun = async () => {
    setRunning(true);
    try {
      const r = await triggerPredictiveTriage();
      toast.success(`Predictor ran · ${r.generated} active predictions`);
      await load();
    } catch (e) {
      toast.error('Predictor run failed: ' + (e?.response?.data?.detail || e.message));
    } finally {
      setRunning(false);
    }
  };

  const handleAck = async (inc) => {
    try {
      await acknowledgePredictiveIncident(inc.id);
      toast.success(`Acknowledged ${inc.service_name}`);
      await load();
    } catch (e) {
      toast.error('Acknowledge failed');
    }
  };

  const handleResolve = async (inc) => {
    try {
      await resolvePredictiveIncident(inc.id);
      toast.success(`Resolved prediction for ${inc.service_name}`);
      await load();
    } catch (e) {
      toast.error('Resolve failed');
    }
  };

  return (
    <div className="p-6 lg:p-8 space-y-5" data-testid="predictive-dashboard">
      <Toaster theme="dark" position="top-right" />

      {/* Header */}
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <div className="flex items-center gap-2 text-[11px] uppercase tracking-wider text-[#D4AF37]">
            <TrendingUp size={13} /> Predictive Triage
          </div>
          <h2 className="font-display font-black text-2xl tracking-tight mt-1">
            Forecast incidents before they happen
          </h2>
          <p className="text-sm text-neutral-400 mt-1 max-w-xl">
            Isolation-Forest anomaly detection on live service metrics, scored 0–100 and explained by Claude.
          </p>
        </div>
        <button
          data-testid="run-predictor-btn"
          onClick={handleRun}
          disabled={running}
          className="px-3.5 py-2 rounded-md border border-[#D4AF37]/40 bg-[#D4AF37]/10 hover:bg-[#D4AF37]/20 text-[#D4AF37] text-sm font-medium flex items-center gap-2 disabled:opacity-60">
          <RefreshCw size={14} className={running ? 'animate-spin' : ''} />
          {running ? 'Scanning…' : 'Run predictor now'}
        </button>
      </div>

      {/* High Risk Services strip */}
      <HighRiskStrip summary={summary} />

      {/* Main grid: incidents list + trend/recommendation + timeline */}
      <div className="grid grid-cols-1 xl:grid-cols-12 gap-4">
        {/* Left: Predicted failures list */}
        <div className="xl:col-span-4 rounded-xl border border-[#1f1f1f] bg-[#0d0d0d] p-4">
          <div className="flex items-center justify-between mb-3">
            <div className="flex items-center gap-2">
              <AlertTriangle size={14} className="text-[#FF9F0A]" />
              <h3 className="text-sm font-semibold">Predicted failures</h3>
              <span className="text-[10px] text-neutral-500">({incidents.length})</span>
            </div>
            {loading && <span className="text-[10px] text-neutral-500 animate-pulse">syncing…</span>}
          </div>
          {incidents.length === 0 ? (
            <div className="text-xs text-neutral-500 px-1 py-8 text-center" data-testid="no-predictions">
              <CheckCircle2 size={28} className="text-[#30D158] mx-auto mb-2" />
              All services within normal envelopes.
            </div>
          ) : (
            <div className="space-y-2 max-h-[640px] overflow-y-auto pr-1">
              {incidents.map(inc => (
                <IncidentRow
                  key={inc.id}
                  inc={inc}
                  active={inc.id === selectedId}
                  onSelect={(i) => setSelectedId(i.id)}
                  onAck={handleAck}
                  onResolve={handleResolve}
                />
              ))}
            </div>
          )}
        </div>

        {/* Center: Trend graph + recommendation */}
        <div className="xl:col-span-5 space-y-4">
          <div className="rounded-xl border border-[#1f1f1f] bg-[#0d0d0d] p-4">
            <TrendGraph trend={trend} />
          </div>
          <RecommendationCard inc={selectedInc} />
        </div>

        {/* Right: Prevention timeline */}
        <div className="xl:col-span-3 rounded-xl border border-[#1f1f1f] bg-[#0d0d0d] p-4">
          <div className="flex items-center gap-2 mb-3">
            <Clock size={14} className="text-[#D4AF37]" />
            <h3 className="text-sm font-semibold">Prevention timeline</h3>
          </div>
          <PreventionTimeline incidents={incidents} />
        </div>
      </div>
    </div>
  );
}
