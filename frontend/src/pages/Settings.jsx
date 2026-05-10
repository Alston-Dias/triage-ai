import React from 'react';
import { CloudUpload as CloudArrowUp, Bell, Brain, Shield, CheckCircle } from 'lucide-react';

const SOURCES = [
  { name: 'AWS CloudWatch', desc: 'Lambda → SNS → API Gateway webhook', enabled: true },
  { name: 'Datadog', desc: 'Webhook with HMAC-SHA256 signature', enabled: true },
  { name: 'PagerDuty V2', desc: 'Trigger / acknowledge / resolve adapter', enabled: true },
  { name: 'Grafana 9+', desc: 'Unified alerting webhook receiver', enabled: true },
  { name: 'Prometheus Alertmanager', desc: 'Webhook receiver adapter', enabled: false },
];

export default function Settings() {
  return (
    <div className="p-6 max-w-4xl">
      <div className="text-[10px] tracking-[0.3em] text-neutral-500 uppercase">Configuration</div>
      <h1 className="font-display text-3xl font-black tracking-tighter mt-1 mb-6">SYSTEM SETTINGS</h1>

      <Section title="Alert Sources" icon={CloudArrowUp}>
        {SOURCES.map(s => (
          <div key={s.name} className="flex items-center justify-between border-b border-[#161616] py-3 last:border-b-0">
            <div>
              <div className="text-sm text-neutral-100">{s.name}</div>
              <div className="text-[11px] text-neutral-500 mt-0.5">{s.desc}</div>
            </div>
            <span className="flex items-center gap-1.5 text-[10px] tracking-widest uppercase" style={{color: s.enabled ? '#30D158' : '#71717A'}}>
              {s.enabled && <CheckCircle size={11} fill="currentColor" />}
              {s.enabled ? 'Connected' : 'Disabled'}
            </span>
          </div>
        ))}
      </Section>

      <Section title="AI Engine" icon={Brain}>
        <Row label="Model" value="claude-sonnet-4-5-20250929" />
        <Row label="Provider" value="Anthropic via Emergent Universal Key" />
        <Row label="Mode" value="Structured JSON · 3 hypotheses · 3-phase remediation" />
      </Section>

      <Section title="Notifications" icon={Bell}>
        <Row label="Slack" value="Not configured" muted />
        <Row label="Microsoft Teams" value="Not configured" muted />
        <Row label="In-App Toasts" value="Enabled" />
      </Section>

      <Section title="Security" icon={Shield}>
        <Row label="Multi-tenancy" value="Single-tenant (MVP)" muted />
        <Row label="SSO" value="Disabled · roadmap" muted />
        <Row label="Rate Limiting" value="Disabled · roadmap" muted />
      </Section>
    </div>
  );
}

function Section({ title, icon: Icon, children }) {
  return (
    <section className="border border-[#1f1f1f] mb-4">
      <div className="px-4 py-3 border-b border-[#1f1f1f] flex items-center gap-2">
        <Icon size={14} color="#D4AF37" />
        <h2 className="text-[11px] tracking-[0.25em] uppercase text-neutral-300 font-display font-bold">{title}</h2>
      </div>
      <div className="px-4 py-2">{children}</div>
    </section>
  );
}
function Row({ label, value, muted }) {
  return (
    <div className="flex items-center justify-between border-b border-[#161616] py-2.5 last:border-b-0">
      <div className="text-[11px] tracking-[0.18em] uppercase text-neutral-500">{label}</div>
      <div className={`text-xs font-mono ${muted ? 'text-neutral-500' : 'text-neutral-100'}`}>{value}</div>
    </div>
  );
}
