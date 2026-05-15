/**
 * Severity helpers for the SonarQube Code Quality dashboard.
 *
 * SonarQube reports five granular severities (BLOCKER / CRITICAL / MAJOR / MINOR / INFO).
 * For the at-a-glance dashboard we collapse those into 3 simple buckets:
 *
 *   BLOCKER, CRITICAL  →  HIGH    (red)
 *   MAJOR              →  MEDIUM  (amber)
 *   MINOR, INFO        →  LOW     (blue)
 *
 * Keep this file in sync with `SONAR_SEVERITY_BUCKET` in backend/server.py.
 */

const BUCKET_MAP = {
  BLOCKER: 'HIGH',
  CRITICAL: 'HIGH',
  MAJOR: 'MEDIUM',
  MINOR: 'LOW',
  INFO: 'LOW',
};

/** Returns the simplified bucket for a raw SonarQube severity. */
export const severityBucket = (severity) => {
  if (!severity) return 'LOW';
  return BUCKET_MAP[String(severity).toUpperCase()] || 'LOW';
};

/**
 * Tailwind classes for the simplified bucket badge.
 * We intentionally use light backgrounds with strong text so the badges work
 * well next to the existing Sonar severity icons.
 */
export const BUCKET_BADGE_CLASS = {
  HIGH:   'bg-red-100 text-red-700 border-red-200',
  MEDIUM: 'bg-amber-100 text-amber-800 border-amber-200',
  LOW:    'bg-blue-100 text-blue-700 border-blue-200',
};

/** Hex used by the SonarSummaryBar dots and the trend sparkline. */
export const BUCKET_DOT_COLOR = {
  BLOCKER: '#7c3aed', // purple — emphasised separately from HIGH
  HIGH:    '#dc2626',
  MEDIUM:  '#d97706',
  LOW:     '#2563eb',
};

/** Human-friendly bucket label. */
export const BUCKET_LABEL = {
  HIGH:   'High',
  MEDIUM: 'Medium',
  LOW:    'Low',
};

/** Format raw minutes as "Xh Ymin" / "Ymin" / "Xh". */
export const formatEffortMinutes = (minutes) => {
  const m = Math.max(0, Math.round(Number(minutes) || 0));
  if (m === 0) return '0min';
  const h = Math.floor(m / 60);
  const r = m % 60;
  if (h && r) return `${h}h ${r}min`;
  if (h) return `${h}h`;
  return `${r}min`;
};

/** Issue type → tailwind chip class (kept here so chips look consistent across pages). */
export const TYPE_BADGE_CLASS = {
  BUG:              'bg-red-50 text-red-700 border-red-200',
  VULNERABILITY:    'bg-purple-50 text-purple-700 border-purple-200',
  CODE_SMELL:       'bg-amber-50 text-amber-800 border-amber-200',
  SECURITY_HOTSPOT: 'bg-orange-50 text-orange-700 border-orange-200',
};
