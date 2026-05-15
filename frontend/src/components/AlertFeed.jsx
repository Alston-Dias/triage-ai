import React, { useMemo } from 'react';
import { SeverityBadge, SourceBadge } from './Badges';
import { relTime } from '../lib/format';
import { MapPin, Box as Cube, Inbox } from 'lucide-react';

const SEV_ORDER = { critical: 0, high: 1, medium: 2, low: 3 };

export default function AlertFeed({ alerts, selected, onToggle, severityFilter, onFilterChange }) {
  const filtered = useMemo(() => {
    return alerts
      .filter(a => severityFilter.size === 0 || severityFilter.has(a.severity))
      .sort((a, b) => (SEV_ORDER[a.severity] - SEV_ORDER[b.severity]) || (b.timestamp || '').localeCompare(a.timestamp || ''));
  }, [alerts, severityFilter]);

  const allSelected = filtered.length > 0 && filtered.every(a => selected.has(a.id));
  const toggleAll = () => {
    if (allSelected) filtered.forEach(a => selected.has(a.id) && onToggle(a.id));
    else filtered.forEach(a => !selected.has(a.id) && onToggle(a.id));
  };

  const SEVS = [
    { key: 'critical', label: 'Critical', color: '#FF3B30' },
    { key: 'high',     label: 'High',     color: '#FF9F0A' },
    { key: 'medium',   label: 'Medium',   color: '#0A84FF' },
    { key: 'low',      label: 'Low',      color: '#30D158' },
  ];

  return (
    <div className="flex flex-col h-full">
      {/* Filter bar */}
      <div className="flex items-center justify-between px-6 py-3 border-b border-[#1f1f1f] gap-3 flex-wrap">
        <div className="flex items-center gap-2">
          <span className="text-xs text-neutral-500 mr-1">Filter:</span>
          {SEVS.map(s => {
            const active = severityFilter.has(s.key);
            return (
              <button
                key={s.key}
                data-testid={`severity-filter-${s.key}`}
                onClick={() => onFilterChange(s.key)}
                className={`px-2.5 py-1 rounded-md text-xs font-medium transition-colors border ${active ? 'border-white/30 bg-white/5 text-white' : 'border-transparent text-neutral-400 hover:bg-white/5 hover:text-neutral-200'}`}>
                <span className="inline-block w-1.5 h-1.5 rounded-full mr-1.5" style={{ background: s.color }} />
                {s.label}
              </button>
            );
          })}
        </div>
        <div className="flex items-center gap-3 text-xs">
          <button data-testid="alert-select-all" onClick={toggleAll}
                  className="px-3 py-1 rounded-md border border-[#262626] hover:border-[#404040] text-neutral-300 transition-colors">
            {allSelected ? 'Deselect all' : 'Select all'}
          </button>
          <span className="text-neutral-500"><span className="text-[#D4AF37] font-semibold">{selected.size}</span> / {filtered.length} selected</span>
        </div>
      </div>

      {/* Feed */}
      <div className="flex-1 overflow-auto px-6 py-3">
        {filtered.length === 0 && (
          <div className="flex flex-col items-center justify-center py-16 text-neutral-500">
            <Inbox size={32} strokeWidth={1.5} className="mb-3 opacity-40" />
            <div className="text-sm">No alerts in scope</div>
            <div className="text-xs text-neutral-600 mt-1">Try clearing filters or click "Seed Demo"</div>
          </div>
        )}
        <div className="space-y-2">
          {filtered.map((a, i) => {
            const isSel = selected.has(a.id);
            return (
              <div
                key={a.id}
                data-testid={`alert-row-${a.id}`}
                onClick={() => onToggle(a.id)}
                style={{ animationDelay: `${Math.min(i, 12) * 25}ms` }}
                className={`group rounded-lg border cursor-pointer animate-slide-up hover-lift px-4 py-3 ${isSel ? 'border-[#D4AF37]/40 bg-[#D4AF37]/5' : 'border-[#1f1f1f] bg-[#0d0d0d] hover:border-[#2a2a2a]'}`}>
                <div className="flex items-start gap-3">
                  <input
                    type="checkbox"
                    checked={isSel}
                    readOnly
                    data-testid={`alert-checkbox-${a.id}`}
                    className="mt-1 accent-[#D4AF37] w-4 h-4"
                  />
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <SeverityBadge severity={a.severity} />
                      <SourceBadge source={a.source} />
                      <span className="text-[11px] text-neutral-600 font-mono">{a.id}</span>
                      <span className="ml-auto text-[11px] text-neutral-500">{relTime(a.timestamp)}</span>
                    </div>
                    <div className="mt-2 text-sm text-white font-medium leading-snug">{a.title}</div>
                    <div className="mt-1.5 flex items-center gap-4 text-xs text-neutral-500">
                      <span className="flex items-center gap-1.5"><Cube size={12} strokeWidth={1.75} /> {a.service}</span>
                      <span className="flex items-center gap-1.5"><MapPin size={12} strokeWidth={1.75} /> {a.region}</span>
                      {a.status !== 'active' && <span className="text-neutral-600">· {a.status}</span>}
                    </div>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
