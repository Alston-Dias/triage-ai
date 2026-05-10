import React, { useEffect, useState } from 'react';
import { fetchUnattended } from '../lib/api';
import { AlertTriangle, X } from 'lucide-react';

export default function UnattendedBanner() {
  const [data, setData] = useState({ count: 0, alerts: [] });
  const [hidden, setHidden] = useState(false);

  useEffect(() => {
    const load = () => fetchUnattended().then(setData).catch(() => {});
    load();
    const t = setInterval(load, 60000);
    return () => clearInterval(t);
  }, []);

  if (hidden || data.count === 0) return null;

  return (
    <div data-testid="unattended-banner" className="border-b border-[#FF9F0A]/40 bg-[#FF9F0A]/10 px-6 py-2.5 flex items-center gap-3">
      <AlertTriangle size={14} color="#FF9F0A" />
      <span className="text-[11px] tracking-[0.18em] uppercase text-[#FF9F0A]">
        SLA Breach · {data.count} alert{data.count > 1 ? 's' : ''} unattended for &gt; {data.threshold_days} days
      </span>
      <span className="ml-auto text-[10px] text-neutral-400 truncate max-w-md font-mono">
        {data.alerts.slice(0, 3).map(a => a.title).join(' · ')}
      </span>
      <button onClick={() => setHidden(true)} className="text-neutral-400 hover:text-white" data-testid="dismiss-unattended-banner">
        <X size={14} />
      </button>
    </div>
  );
}
