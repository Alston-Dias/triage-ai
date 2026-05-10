export const SEVERITY_META = {
  critical: { label: 'CRIT', text: '#FF3B30', bg: 'rgba(255,59,48,0.10)', border: 'rgba(255,59,48,0.35)' },
  high:     { label: 'HIGH', text: '#FF9F0A', bg: 'rgba(255,159,10,0.10)', border: 'rgba(255,159,10,0.35)' },
  medium:   { label: 'MED',  text: '#0A84FF', bg: 'rgba(10,132,255,0.10)', border: 'rgba(10,132,255,0.35)' },
  low:      { label: 'LOW',  text: '#30D158', bg: 'rgba(48,209,88,0.10)', border: 'rgba(48,209,88,0.35)' },
};

export const PRIORITY_META = {
  P1: { text: '#FF3B30', bg: 'rgba(255,59,48,0.12)', border: 'rgba(255,59,48,0.45)' },
  P2: { text: '#FF9F0A', bg: 'rgba(255,159,10,0.12)', border: 'rgba(255,159,10,0.45)' },
  P3: { text: '#0A84FF', bg: 'rgba(10,132,255,0.12)', border: 'rgba(10,132,255,0.45)' },
  P4: { text: '#30D158', bg: 'rgba(48,209,88,0.12)', border: 'rgba(48,209,88,0.45)' },
};

export function relTime(iso) {
  if (!iso) return '';
  const t = new Date(iso).getTime();
  const diff = Math.floor((Date.now() - t) / 1000);
  if (diff < 60) return `${diff}s ago`;
  if (diff < 3600) return `${Math.floor(diff/60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff/3600)}h ago`;
  return `${Math.floor(diff/86400)}d ago`;
}
