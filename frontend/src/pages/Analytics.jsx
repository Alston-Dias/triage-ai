import React, { useEffect, useState } from 'react';
import { fetchAnalytics } from '../lib/api';
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, LineChart, Line, CartesianGrid } from 'recharts';
import { LineChart as ChartLine, Activity, AlertTriangle, CheckCircle } from 'lucide-react';

const SEV_COLOR = { critical: '#FF3B30', high: '#FF9F0A', medium: '#0A84FF', low: '#30D158' };
const PRI_TO_SEV = { P1: 'critical', P2: 'high', P3: 'medium', P4: 'low' };

export default function Analytics() {
  const [data, setData] = useState(null);

  useEffect(() => {
    fetchAnalytics().then(setData);
    const t = setInterval(() => fetchAnalytics().then(setData), 10000);
    return () => clearInterval(t);
  }, []);

  if (!data) return <div className="px-8 py-12 text-sm text-neutral-500">Loading metrics…</div>;

  return (
    <div className="px-8 py-6">
      <div className="mb-6">
        <div className="text-xs text-neutral-500 mb-1">Telemetry</div>
        <h2 className="font-display text-3xl font-black tracking-tight">Analytics Dashboard</h2>
      </div>

      {/* KPIs */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 mb-6" data-testid="kpi-grid">
        <Kpi label="Total alerts"   value={data.totals.alerts}         icon={Activity}     accent="#D4AF37" />
        <Kpi label="Active alerts"  value={data.totals.active_alerts}  icon={AlertTriangle} accent="#FF9F0A" />
        <Kpi label="Incidents"      value={data.totals.incidents}      icon={ChartLine}    accent="#0A84FF" />
        <Kpi label="Open incidents" value={data.totals.open_incidents} icon={CheckCircle}  accent="#30D158" />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
        <Card title="Signal distribution" subtitle="Alert volume by source">
          <div className="h-64 -mx-2">
            <ResponsiveContainer>
              <BarChart data={data.by_source}>
                <CartesianGrid strokeDasharray="3 3" stroke="#1f1f1f" vertical={false} />
                <XAxis dataKey="source" stroke="#71717A" fontSize={11} tickLine={false} axisLine={{stroke:'#262626'}} />
                <YAxis stroke="#71717A" fontSize={11} tickLine={false} axisLine={{stroke:'#262626'}} />
                <Tooltip contentStyle={{background:'#0a0a0a', border:'1px solid #262626', borderRadius:8, fontSize:12}} />
                <Bar dataKey="count" fill="#D4AF37" radius={[4,4,0,0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </Card>

        <Card title="Resolution velocity" subtitle="MTTR trend · last 7 days">
          <div className="h-64 -mx-2">
            <ResponsiveContainer>
              <LineChart data={data.mttr_trend}>
                <CartesianGrid strokeDasharray="3 3" stroke="#1f1f1f" vertical={false} />
                <XAxis dataKey="day" stroke="#71717A" fontSize={11} tickLine={false} axisLine={{stroke:'#262626'}} tickFormatter={(d)=>d.slice(5)} />
                <YAxis stroke="#71717A" fontSize={11} tickLine={false} axisLine={{stroke:'#262626'}} />
                <Tooltip contentStyle={{background:'#0a0a0a', border:'1px solid #262626', borderRadius:8, fontSize:12}} />
                <Line type="monotone" dataKey="mttr" stroke="#0A84FF" strokeWidth={2.5} dot={{fill:'#0A84FF', r:4}} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </Card>

        <Card title="Severity breakdown" subtitle="Across all alerts">
          <div className="space-y-3 py-2">
            {data.by_severity.map(s => {
              const max = Math.max(...data.by_severity.map(x => x.count), 1);
              return (
                <div key={s.severity} className="flex items-center gap-3">
                  <span className="text-xs font-medium w-20 capitalize" style={{color: SEV_COLOR[s.severity]}}>{s.severity}</span>
                  <div className="flex-1 h-2 bg-[#161616] rounded-full overflow-hidden">
                    <div className="h-full rounded-full transition-all" style={{width: `${(s.count/max)*100}%`, background: SEV_COLOR[s.severity]}} />
                  </div>
                  <span className="text-sm font-mono font-semibold text-neutral-200 w-10 text-right">{s.count}</span>
                </div>
              );
            })}
          </div>
        </Card>

        <Card title="Recent incidents" subtitle="Top 5 most recent">
          {data.top_incidents.length === 0 && <div className="text-sm text-neutral-500 py-2">No incidents yet</div>}
          <div className="space-y-2">
            {data.top_incidents.map(inc => (
              <div key={inc.id} className="flex items-center gap-3 py-2 border-b border-[#161616] last:border-b-0">
                <span className="text-[11px] font-mono text-neutral-500">{inc.id}</span>
                <span className="text-sm text-neutral-200 truncate flex-1">{inc.title}</span>
                <span className="text-[11px] px-1.5 py-0.5 rounded font-mono font-semibold" style={{color: SEV_COLOR[PRI_TO_SEV[inc.priority]], background: `${SEV_COLOR[PRI_TO_SEV[inc.priority]]}15`}}>{inc.priority}</span>
              </div>
            ))}
          </div>
        </Card>
      </div>
    </div>
  );
}

function Kpi({ label, value, icon: Icon, accent }) {
  return (
    <div className="rounded-xl border border-[#1f1f1f] bg-[#0a0a0a] p-5 hover-lift">
      <div className="flex items-center justify-between">
        <span className="text-xs text-neutral-500">{label}</span>
        <Icon size={15} strokeWidth={1.75} color={accent} />
      </div>
      <div className="font-display font-black text-3xl tracking-tight mt-2" style={{color: accent}}>{value}</div>
    </div>
  );
}

function Card({ title, subtitle, children }) {
  return (
    <div className="rounded-xl border border-[#1f1f1f] bg-[#0a0a0a] p-5">
      <div className="mb-3">
        <h3 className="font-display font-bold text-base tracking-tight text-white">{title}</h3>
        {subtitle && <div className="text-xs text-neutral-500 mt-0.5">{subtitle}</div>}
      </div>
      {children}
    </div>
  );
}
