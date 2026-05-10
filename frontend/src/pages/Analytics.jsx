import React, { useEffect, useState } from 'react';
import { fetchAnalytics } from '../lib/api';
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, LineChart, Line, CartesianGrid } from 'recharts';
import { LineChart as ChartLine, Activity as Pulse, AlertTriangle as Warning, CheckCircle } from 'lucide-react';

const SEV_COLOR = { critical: '#FF3B30', high: '#FF9F0A', medium: '#0A84FF', low: '#30D158' };

export default function Analytics() {
  const [data, setData] = useState(null);

  useEffect(() => {
    fetchAnalytics().then(setData);
    const t = setInterval(() => fetchAnalytics().then(setData), 10000);
    return () => clearInterval(t);
  }, []);

  if (!data) return <div className="p-8 text-xs text-neutral-500 tracking-widest uppercase">// Loading metrics...</div>;

  return (
    <div className="p-6">
      <div className="text-[10px] tracking-[0.3em] text-neutral-500 uppercase">Telemetry</div>
      <h1 className="font-display text-3xl font-black tracking-tighter mt-1 mb-6">ANALYTICS DASHBOARD</h1>

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-0 border border-[#1f1f1f] mb-6" data-testid="kpi-grid">
        <Kpi label="Total Alerts" value={data.totals.alerts} icon={Pulse} accent="#D4AF37" />
        <Kpi label="Active" value={data.totals.active_alerts} icon={Warning} accent="#FF9F0A" />
        <Kpi label="Incidents" value={data.totals.incidents} icon={ChartLine} accent="#0A84FF" />
        <Kpi label="Open" value={data.totals.open_incidents} icon={CheckCircle} accent="#30D158" last />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-0 border border-[#1f1f1f]">
        <div className="border-b lg:border-b-0 lg:border-r border-[#1f1f1f] p-4">
          <div className="text-[10px] tracking-[0.25em] uppercase text-neutral-400 mb-1">Alert volume by source</div>
          <div className="font-display font-bold text-lg mb-3">SIGNAL DISTRIBUTION</div>
          <div className="h-64">
            <ResponsiveContainer>
              <BarChart data={data.by_source}>
                <CartesianGrid strokeDasharray="3 3" stroke="#1f1f1f" vertical={false} />
                <XAxis dataKey="source" stroke="#71717A" fontSize={10} tickLine={false} axisLine={{stroke:'#262626'}} />
                <YAxis stroke="#71717A" fontSize={10} tickLine={false} axisLine={{stroke:'#262626'}} />
                <Tooltip contentStyle={{background:'#0a0a0a', border:'1px solid #262626', fontSize:11, fontFamily:'JetBrains Mono'}} />
                <Bar dataKey="count" fill="#D4AF37" />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>

        <div className="p-4">
          <div className="text-[10px] tracking-[0.25em] uppercase text-neutral-400 mb-1">MTTR trend · last 7 days</div>
          <div className="font-display font-bold text-lg mb-3">RESOLUTION VELOCITY</div>
          <div className="h-64">
            <ResponsiveContainer>
              <LineChart data={data.mttr_trend}>
                <CartesianGrid strokeDasharray="3 3" stroke="#1f1f1f" vertical={false} />
                <XAxis dataKey="day" stroke="#71717A" fontSize={10} tickLine={false} axisLine={{stroke:'#262626'}} tickFormatter={(d)=>d.slice(5)} />
                <YAxis stroke="#71717A" fontSize={10} tickLine={false} axisLine={{stroke:'#262626'}} />
                <Tooltip contentStyle={{background:'#0a0a0a', border:'1px solid #262626', fontSize:11, fontFamily:'JetBrains Mono'}} />
                <Line type="monotone" dataKey="mttr" stroke="#0A84FF" strokeWidth={2} dot={{fill:'#0A84FF', r:3}} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-0 border border-[#1f1f1f] border-t-0">
        <div className="border-b lg:border-b-0 lg:border-r border-[#1f1f1f] p-4">
          <div className="text-[10px] tracking-[0.25em] uppercase text-neutral-400 mb-3">Severity breakdown</div>
          <div className="space-y-2">
            {data.by_severity.map(s => (
              <div key={s.severity} className="flex items-center gap-3">
                <span className="text-[10px] uppercase tracking-widest w-16" style={{color: SEV_COLOR[s.severity]}}>{s.severity}</span>
                <div className="flex-1 h-2 bg-[#161616] relative">
                  <div className="absolute top-0 left-0 h-full" style={{width: `${Math.min(100, s.count*10)}%`, background: SEV_COLOR[s.severity]}} />
                </div>
                <span className="text-xs font-mono text-neutral-300 w-8 text-right">{s.count}</span>
              </div>
            ))}
          </div>
        </div>

        <div className="p-4">
          <div className="text-[10px] tracking-[0.25em] uppercase text-neutral-400 mb-3">Top recent incidents</div>
          {data.top_incidents.length === 0 && <div className="text-xs text-neutral-500">No incidents yet</div>}
          {data.top_incidents.map(inc => (
            <div key={inc.id} className="border-b border-[#161616] py-2 last:border-b-0">
              <div className="flex items-center gap-2">
                <span className="text-[10px] font-mono text-neutral-500">{inc.id}</span>
                <span className="ml-auto text-[10px] uppercase tracking-widest" style={{color: SEV_COLOR[inc.priority === 'P1' ? 'critical' : inc.priority === 'P2' ? 'high' : inc.priority === 'P3' ? 'medium' : 'low']}}>{inc.priority}</span>
              </div>
              <div className="text-xs text-neutral-300 truncate mt-1">{inc.title}</div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function Kpi({ label, value, icon: Icon, accent, last }) {
  return (
    <div className={`p-5 ${!last ? 'border-r border-[#1f1f1f]' : ''}`}>
      <div className="flex items-center gap-2">
        <Icon size={14} color={accent} />
        <span className="text-[10px] tracking-[0.2em] uppercase text-neutral-500">{label}</span>
      </div>
      <div className="font-display font-black text-4xl tracking-tighter mt-2" style={{color: accent}}>{value}</div>
    </div>
  );
}
