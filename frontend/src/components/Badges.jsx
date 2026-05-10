import React from 'react';
import { SEVERITY_META, PRIORITY_META } from '../lib/format';

export function SeverityBadge({ severity }) {
  const m = SEVERITY_META[severity] || SEVERITY_META.low;
  return (
    <span
      data-testid={`severity-badge-${severity}`}
      className="inline-flex items-center px-1.5 py-0.5 text-[10px] font-bold tracking-[0.18em] font-mono"
      style={{ color: m.text, background: m.bg, border: `1px solid ${m.border}` }}>
      {m.label}
    </span>
  );
}

export function PriorityBadge({ priority }) {
  const m = PRIORITY_META[priority] || PRIORITY_META.P3;
  return (
    <span
      data-testid={`priority-badge-${priority}`}
      className="inline-flex items-center px-2 py-0.5 text-[11px] font-bold tracking-[0.18em] font-mono"
      style={{ color: m.text, background: m.bg, border: `1px solid ${m.border}` }}>
      {priority}
    </span>
  );
}

export function SourceBadge({ source }) {
  return (
    <span className="inline-flex items-center px-1.5 py-0.5 text-[10px] tracking-[0.15em] uppercase border border-[#2a2a2a] text-neutral-400 font-mono">
      {source}
    </span>
  );
}

export function StatusPill({ status }) {
  const map = {
    active:    { c: '#FF9F0A', t: 'ACTIVE' },
    resolved:  { c: '#71717A', t: 'RESOLVED' },
    noise:     { c: '#0A84FF', t: 'NOISE' },
    open:      { c: '#FF3B30', t: 'OPEN' },
    triaging:  { c: '#D4AF37', t: 'TRIAGING' },
  };
  const m = map[status] || { c: '#71717A', t: status?.toUpperCase() };
  return (
    <span className="inline-flex items-center gap-1.5 text-[10px] tracking-[0.18em] uppercase">
      <span className="w-1.5 h-1.5 rounded-full" style={{background: m.c}} />
      <span style={{color: m.c}}>{m.t}</span>
    </span>
  );
}
