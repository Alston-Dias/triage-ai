import React, { useMemo } from 'react';
import { SeverityBadge, SourceBadge } from './Badges';
import { relTime } from '../lib/format';
import { MapPin, Box as Cube } from 'lucide-react';

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

  const SEVS = ['critical','high','medium','low'];

  return (
    <div className="flex flex-col h-full">
      {/* Filters */}
      <div className="flex items-center justify-between border-b border-[#1f1f1f] px-4 py-3 gap-3">
        <div className="flex items-center gap-2">
          {SEVS.map(s => {
            const active = severityFilter.has(s);
            return (
              <button
                key={s}
                data-testid={`severity-filter-${s}`}
                onClick={() => onFilterChange(s)}
                className={`px-2 py-1 text-[10px] tracking-[0.18em] uppercase border transition-colors ${active ? 'border-white text-white bg-[#161616]' : 'border-[#262626] text-neutral-500 hover:border-[#404040] hover:text-neutral-300'}`}>
                {s}
              </button>
            );
          })}
        </div>
        <div className="flex items-center gap-2 text-[10px] tracking-[0.2em] uppercase">
          <button data-testid="alert-select-all" onClick={toggleAll} className="px-2 py-1 border border-[#262626] hover:border-[#404040] text-neutral-300">
            {allSelected ? 'NONE' : 'ALL'}
          </button>
          <span className="text-neutral-500">{selected.size}/{filtered.length} SEL</span>
        </div>
      </div>

      {/* Feed */}
      <div className="flex-1 overflow-auto">
        {filtered.length === 0 && (
          <div className="p-8 text-center text-neutral-500 text-xs tracking-widest uppercase">// No alerts in scope</div>
        )}
        {filtered.map((a, i) => {
          const isSel = selected.has(a.id);
          return (
            <div
              key={a.id}
              data-testid={`alert-row-${a.id}`}
              onClick={() => onToggle(a.id)}
              style={{ animationDelay: `${Math.min(i,12)*30}ms` }}
              className={`group border-b border-[#1a1a1a] px-4 py-3 cursor-pointer transition-colors animate-slide-up ${isSel ? 'bg-[#141414]' : 'hover:bg-[#101010]'}`}>
              <div className="flex items-start gap-3">
                <input
                  type="checkbox"
                  checked={isSel}
                  readOnly
                  data-testid={`alert-checkbox-${a.id}`}
                  className="mt-1 accent-[#D4AF37] w-3.5 h-3.5"
                />
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <SeverityBadge severity={a.severity} />
                    <SourceBadge source={a.source} />
                    <span className="text-[10px] text-neutral-500 tracking-wider">{a.id}</span>
                    <span className="ml-auto text-[10px] text-neutral-500">{relTime(a.timestamp)}</span>
                  </div>
                  <div className="mt-1.5 text-sm text-white truncate">{a.title}</div>
                  <div className="mt-1 flex items-center gap-3 text-[11px] text-neutral-500">
                    <span className="flex items-center gap-1"><Cube size={11} /> {a.service}</span>
                    <span className="flex items-center gap-1"><MapPin size={11} /> {a.region}</span>
                    {a.status !== 'active' && <span className="uppercase tracking-wider text-neutral-600">· {a.status}</span>}
                  </div>
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
