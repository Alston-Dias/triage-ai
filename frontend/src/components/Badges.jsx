import React from 'react';
import { SEVERITY_META, PRIORITY_META } from '../lib/format';

export function SeverityBadge({ severity }) {
  const m = SEVERITY_META[severity] || SEVERITY_META.low;
  return (
    <span
      data-testid={`severity-badge-${severity}`}
      className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-md text-[11px] font-semibold tracking-wide font-mono"
      style={{ color: m.text, background: m.bg, border: `1px solid ${m.border}` }}>
      <span className="w-1.5 h-1.5 rounded-full" style={{ background: m.text }} />
      {m.label}
    </span>
  );
}

export function PriorityBadge({ priority }) {
  const m = PRIORITY_META[priority] || PRIORITY_META.P3;
  return (
    <span
      data-testid={`priority-badge-${priority}`}
      className="inline-flex items-center px-2.5 py-0.5 rounded-md text-xs font-bold tracking-wide font-mono"
      style={{ color: m.text, background: m.bg, border: `1px solid ${m.border}` }}>
      {priority}
    </span>
  );
}

export function SourceBadge({ source }) {
  return (
    <span className="inline-flex items-center px-2 py-0.5 rounded-md text-[11px] tracking-wide border border-[#2a2a2a] text-neutral-400 font-mono">
      {source}
    </span>
  );
}

export function StatusPill({ status }) {
  const map = {
    active:    { c: '#FF9F0A', t: 'Active' },
    resolved:  { c: '#71717A', t: 'Resolved' },
    noise:     { c: '#0A84FF', t: 'Noise' },
    open:      { c: '#FF3B30', t: 'Open' },
    triaging:  { c: '#D4AF37', t: 'Triaging' },
    in_progress:{c: '#0A84FF', t: 'In Progress' },
  };
  const m = map[status] || { c: '#71717A', t: status };
  return (
    <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-md text-[11px] font-medium" style={{ color: m.c, background: `${m.c}10`, border: `1px solid ${m.c}30` }}>
      <span className="w-1.5 h-1.5 rounded-full" style={{ background: m.c }} />
      {m.t}
    </span>
  );
}
