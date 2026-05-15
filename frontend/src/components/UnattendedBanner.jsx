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
    <div data-testid="unattended-banner" className="border-b border-[#FF9F0A]/30 bg-[#FF9F0A]/[0.08] px-8 py-3 flex items-center gap-3">
      <AlertTriangle size={15} strokeWidth={2} color="#FF9F0A" />
      <span className="text-sm text-[#FF9F0A] font-medium">
        SLA breach — {data.count} alert{data.count > 1 ? 's' : ''} unattended for over {data.threshold_days} days
      </span>
      <span className="ml-auto text-xs text-neutral-400 truncate max-w-md hidden md:block">
        {data.alerts.slice(0, 2).map(a => a.title).join(' · ')}
      </span>
      <button onClick={() => setHidden(true)} className="p-1 rounded hover:bg-[#FF9F0A]/10 text-neutral-400 hover:text-white" data-testid="dismiss-unattended-banner">
        <X size={14} />
      </button>
    </div>
  );
}
