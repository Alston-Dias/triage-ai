import React, { useEffect, useMemo, useState, useCallback, useRef } from 'react';
import {
  Plus,
  Github,
  Upload as UploadIcon,
  Plug,
  RefreshCw,
  Trash2,
  AlertTriangle,
  Bug,
  Shield,
  Sparkles,
  X,
  ChevronRight,
  Loader2,
  ExternalLink,
  FileCode2,
  Wand2,
  Eye,
  EyeOff,
  Power,
  Database,
} from 'lucide-react';
import { Card } from '../components/ui/card';
import { Badge } from '../components/ui/badge';
import { toast, Toaster } from 'sonner';
import {
  cqListScans,
  cqGetScan,
  cqDeleteScan,
  cqGetScanIssues,
  cqScanGithub,
  cqScanUpload,
  cqListIntegrations,
  cqCreateIntegration,
  cqDeleteIntegration,
  cqUpdateIntegration,
  cqSyncIntegration,
  cqGenerateFix,
  cqSeedDemo,
  SEVERITY_COLORS,
  TYPE_COLORS,
  TYPE_LABEL,
  PROVIDER_LABEL,
} from '../lib/codeQualityApi';
import { useActiveModel } from '../hooks/useActiveModel';

// ============================================================================
// Helpers
// ============================================================================
const fmtTime = (iso) => {
  if (!iso) return '—';
  try {
    return new Date(iso).toLocaleString();
  } catch {
    return iso;
  }
};

const StatusBadge = ({ status }) => {
  const map = {
    queued: 'bg-neutral-500/15 text-neutral-300 border-neutral-500/30',
    scanning: 'bg-sky-500/15 text-sky-300 border-sky-500/30',
    done: 'bg-emerald-500/15 text-emerald-300 border-emerald-500/30',
    failed: 'bg-red-500/15 text-red-300 border-red-500/30',
  };
  return (
    <Badge className={`${map[status] || map.queued} border text-[10px] uppercase tracking-wider font-semibold px-2 py-0.5`}>
      {status === 'scanning' && <Loader2 size={10} className="inline-block animate-spin mr-1" />}
      {status}
    </Badge>
  );
};

const SourceIcon = ({ source }) => {
  if (source === 'github') return <Github size={14} className="text-neutral-400" />;
  if (source === 'upload') return <UploadIcon size={14} className="text-neutral-400" />;
  return <Plug size={14} className="text-neutral-400" />;
};

// ============================================================================
// New Scan Modal (3 tabs)
// ============================================================================
const NewScanModal = ({ open, onClose, integrations, onScanCreated, onIntegrationCreated, onIntegrationSyncStarted }) => {
  const { model } = useActiveModel();
  const [tab, setTab] = useState('github');
  const [busy, setBusy] = useState(false);

  // Tab 1 – GitHub
  const [repoUrl, setRepoUrl] = useState('');
  const [branch, setBranch] = useState('');
  const [ghToken, setGhToken] = useState('');
  const [showToken, setShowToken] = useState(false);

  // Tab 2 – Upload
  const [file, setFile] = useState(null);
  const [uploadPct, setUploadPct] = useState(0);
  const fileInputRef = useRef(null);

  // Tab 3 – Connect existing
  const [provider, setProvider] = useState('sonarqube');
  const [name, setName] = useState('');
  const [baseUrl, setBaseUrl] = useState('');
  const [token, setToken] = useState('');
  const [projectKey, setProjectKey] = useState('');
  const [org, setOrg] = useState('');
  const [customAuthHeader, setCustomAuthHeader] = useState('Authorization');
  const [customAuthPrefix, setCustomAuthPrefix] = useState('Bearer ');
  const [selectedIntegrationId, setSelectedIntegrationId] = useState('');

  useEffect(() => {
    if (open) {
      // reset light state when modal re-opens
      setUploadPct(0);
      setBusy(false);
    }
  }, [open]);

  if (!open) return null;

  const startGithub = async () => {
    if (!repoUrl.trim()) {
      toast.error('Repo URL is required');
      return;
    }
    setBusy(true);
    try {
      const scan = await cqScanGithub({ repo_url: repoUrl.trim(), branch: branch.trim(), github_token: ghToken.trim() });
      toast.success(`Scan started: ${scan.source_label}`);
      onScanCreated(scan);
      setRepoUrl('');
      setBranch('');
      setGhToken('');
      onClose();
    } catch (e) {
      toast.error(e?.response?.data?.detail || e.message || 'Failed to start GitHub scan');
    } finally {
      setBusy(false);
    }
  };

  const startUpload = async () => {
    if (!file) {
      toast.error('Please choose a .zip file');
      return;
    }
    if (!file.name.toLowerCase().endsWith('.zip')) {
      toast.error('Only .zip files are accepted');
      return;
    }
    if (file.size > 50 * 1024 * 1024) {
      toast.error('Zip exceeds 50 MB cap');
      return;
    }
    setBusy(true);
    setUploadPct(0);
    try {
      const scan = await cqScanUpload(file, setUploadPct);
      toast.success(`Scan started: ${scan.source_label}`);
      onScanCreated(scan);
      setFile(null);
      if (fileInputRef.current) fileInputRef.current.value = '';
      onClose();
    } catch (e) {
      toast.error(e?.response?.data?.detail || e.message || 'Upload failed');
    } finally {
      setBusy(false);
    }
  };

  const saveIntegration = async () => {
    if (!name.trim()) {
      toast.error('Name required');
      return;
    }
    if (!baseUrl.trim()) {
      toast.error('Base URL required');
      return;
    }
    if (!token.trim()) {
      toast.error('Token required');
      return;
    }
    setBusy(true);
    try {
      const payload = {
        name: name.trim(),
        provider,
        base_url: baseUrl.trim(),
        token: token.trim(),
        project_key: projectKey.trim() || null,
        org: org.trim() || null,
        extra: provider === 'custom' ? { auth_header: customAuthHeader || 'Authorization', auth_prefix: customAuthPrefix || '' } : {},
      };
      const integ = await cqCreateIntegration(payload);
      toast.success(`Integration saved: ${integ.name}`);
      onIntegrationCreated(integ);
      setName('');
      setBaseUrl('');
      setToken('');
      setProjectKey('');
      setOrg('');
    } catch (e) {
      toast.error(e?.response?.data?.detail || 'Failed to save integration');
    } finally {
      setBusy(false);
    }
  };

  const syncExisting = async () => {
    if (!selectedIntegrationId) {
      toast.error('Pick an integration to sync');
      return;
    }
    setBusy(true);
    try {
      const scan = await cqSyncIntegration(selectedIntegrationId);
      toast.success(`Sync started: ${scan.source_label}`);
      onIntegrationSyncStarted(scan);
      onClose();
    } catch (e) {
      toast.error(e?.response?.data?.detail || 'Sync failed');
    } finally {
      setBusy(false);
    }
  };

  const tabBtn = (id, label, Icon) => (
    <button
      key={id}
      type="button"
      onClick={() => setTab(id)}
      data-testid={`cq2-tab-${id}`}
      className={`flex items-center gap-2 px-4 py-2.5 text-sm font-medium border-b-2 transition-all ${
        tab === id
          ? 'border-[#D4AF37] text-white'
          : 'border-transparent text-neutral-500 hover:text-neutral-300'
      }`}
    >
      <Icon size={14} />
      {label}
    </button>
  );

  const input = 'w-full bg-[#0A0A0A] border border-[#1f1f1f] rounded-md px-3 py-2 text-sm text-white placeholder:text-neutral-600 focus:outline-none focus:border-[#D4AF37]/50';
  const lbl = 'block text-xs font-medium text-neutral-400 mb-1.5';

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm p-4" onClick={onClose}>
      <div
        className="bg-[#0d0d0d] border border-[#1f1f1f] rounded-xl w-full max-w-2xl max-h-[90vh] overflow-y-auto"
        onClick={(e) => e.stopPropagation()}
        data-testid="cq2-new-scan-modal"
      >
        <div className="flex items-center justify-between px-6 py-4 border-b border-[#1f1f1f]">
          <h3 className="font-display font-bold text-lg text-white flex items-center gap-2">
            <Sparkles size={18} className="text-[#D4AF37]" />
            New Code Quality Scan
          </h3>
          <button onClick={onClose} className="text-neutral-500 hover:text-white" aria-label="Close">
            <X size={18} />
          </button>
        </div>

        <div className="flex border-b border-[#1f1f1f] px-3">
          {tabBtn('github', 'GitHub URL', Github)}
          {tabBtn('upload', 'Upload .zip', UploadIcon)}
          {tabBtn('connect', 'Connect Dashboard', Plug)}
        </div>

        <div className="p-6">
          {/* TAB: GitHub */}
          {tab === 'github' && (
            <div className="space-y-4">
              <div>
                <label className={lbl}>Repository URL</label>
                <input
                  className={input}
                  placeholder="https://github.com/owner/repo"
                  value={repoUrl}
                  onChange={(e) => setRepoUrl(e.target.value)}
                  data-testid="cq2-gh-url"
                />
                <p className="text-[11px] text-neutral-500 mt-1">Public or private. Up to 30 source files will be analyzed by <span className="font-mono">{model}</span>.</p>
              </div>
              <div>
                <label className={lbl}>Branch (optional)</label>
                <input
                  className={input}
                  placeholder="main"
                  value={branch}
                  onChange={(e) => setBranch(e.target.value)}
                  data-testid="cq2-gh-branch"
                />
              </div>
              <div>
                <label className={lbl}>GitHub Personal Access Token (only for private repos)</label>
                <div className="relative">
                  <input
                    type={showToken ? 'text' : 'password'}
                    className={input + ' pr-10'}
                    placeholder="ghp_..."
                    value={ghToken}
                    onChange={(e) => setGhToken(e.target.value)}
                    data-testid="cq2-gh-token"
                  />
                  <button
                    type="button"
                    onClick={() => setShowToken((v) => !v)}
                    className="absolute right-2 top-1/2 -translate-y-1/2 text-neutral-500 hover:text-neutral-300"
                  >
                    {showToken ? <EyeOff size={14} /> : <Eye size={14} />}
                  </button>
                </div>
                <p className="text-[11px] text-neutral-500 mt-1">Token is sent server-side, used only for the clone, and never persisted.</p>
              </div>
              <div className="flex justify-end pt-2">
                <button
                  onClick={startGithub}
                  disabled={busy}
                  data-testid="cq2-gh-submit"
                  className="flex items-center gap-2 px-5 py-2 bg-[#D4AF37] hover:bg-[#D4AF37]/90 text-black text-sm font-semibold rounded-md disabled:opacity-50"
                >
                  {busy ? <Loader2 size={14} className="animate-spin" /> : <Sparkles size={14} />}
                  Run AI Scan
                </button>
              </div>
            </div>
          )}

          {/* TAB: Upload */}
          {tab === 'upload' && (
            <div className="space-y-4">
              <div>
                <label className={lbl}>Code folder (zipped)</label>
                <div className="border border-dashed border-[#1f1f1f] rounded-lg p-6 bg-[#0A0A0A] text-center">
                  <UploadIcon size={28} className="text-neutral-500 mx-auto mb-2" />
                  <p className="text-sm text-neutral-300 mb-1">{file ? file.name : 'Drag & drop or click to choose a .zip'}</p>
                  <p className="text-[11px] text-neutral-500 mb-3">Max 50 MB • Max 2000 files</p>
                  <input
                    ref={fileInputRef}
                    type="file"
                    accept=".zip,application/zip"
                    onChange={(e) => setFile(e.target.files?.[0] || null)}
                    className="hidden"
                    id="cq2-upload-file"
                    data-testid="cq2-upload-input"
                  />
                  <label
                    htmlFor="cq2-upload-file"
                    className="inline-block px-4 py-1.5 text-xs bg-[#161616] hover:bg-[#1f1f1f] text-white rounded-md cursor-pointer"
                  >
                    Choose file
                  </label>
                  {file && (
                    <button
                      onClick={() => {
                        setFile(null);
                        if (fileInputRef.current) fileInputRef.current.value = '';
                      }}
                      className="ml-2 text-[11px] text-neutral-500 hover:text-white"
                    >
                      Remove
                    </button>
                  )}
                </div>
              </div>
              {busy && uploadPct > 0 && uploadPct < 100 && (
                <div>
                  <div className="text-[11px] text-neutral-400 mb-1">Uploading… {uploadPct}%</div>
                  <div className="h-1.5 bg-[#161616] rounded-full overflow-hidden">
                    <div className="h-full bg-[#D4AF37] transition-all" style={{ width: `${uploadPct}%` }} />
                  </div>
                </div>
              )}
              <div className="flex justify-end">
                <button
                  onClick={startUpload}
                  disabled={busy || !file}
                  data-testid="cq2-upload-submit"
                  className="flex items-center gap-2 px-5 py-2 bg-[#D4AF37] hover:bg-[#D4AF37]/90 text-black text-sm font-semibold rounded-md disabled:opacity-50"
                >
                  {busy ? <Loader2 size={14} className="animate-spin" /> : <Sparkles size={14} />}
                  Upload & Scan
                </button>
              </div>
            </div>
          )}

          {/* TAB: Connect Dashboard */}
          {tab === 'connect' && (
            <div className="space-y-5">
              {integrations.length > 0 && (
                <div className="bg-[#0A0A0A] border border-[#1f1f1f] rounded-lg p-4">
                  <div className="text-xs font-semibold text-neutral-300 mb-2">Sync an existing integration</div>
                  <div className="flex gap-2">
                    <select
                      className={input + ' flex-1'}
                      value={selectedIntegrationId}
                      onChange={(e) => setSelectedIntegrationId(e.target.value)}
                      data-testid="cq2-sync-pick"
                    >
                      <option value="">— Choose —</option>
                      {integrations.map((i) => (
                        <option key={i.id} value={i.id}>
                          {PROVIDER_LABEL[i.provider] || i.provider} • {i.name}
                        </option>
                      ))}
                    </select>
                    <button
                      onClick={syncExisting}
                      disabled={busy}
                      data-testid="cq2-sync-btn"
                      className="px-4 py-2 bg-[#D4AF37]/15 hover:bg-[#D4AF37]/25 border border-[#D4AF37]/40 text-[#D4AF37] text-sm font-semibold rounded-md disabled:opacity-50 flex items-center gap-2"
                    >
                      {busy ? <Loader2 size={14} className="animate-spin" /> : <RefreshCw size={14} />}
                      Sync now
                    </button>
                  </div>
                </div>
              )}

              <div className="text-xs font-semibold text-neutral-300">Or add a new scanner</div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className={lbl}>Provider</label>
                  <select className={input} value={provider} onChange={(e) => setProvider(e.target.value)} data-testid="cq2-conn-provider">
                    <option value="sonarqube">SonarQube</option>
                    <option value="sonarcloud">SonarCloud</option>
                    <option value="snyk">Snyk</option>
                    <option value="github_advanced_security">GitHub Advanced Security</option>
                    <option value="semgrep">Semgrep Cloud</option>
                    <option value="custom">Custom (generic)</option>
                  </select>
                </div>
                <div>
                  <label className={lbl}>Name</label>
                  <input
                    className={input}
                    placeholder="My SonarQube prod"
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    data-testid="cq2-conn-name"
                  />
                </div>
              </div>

              <div>
                <label className={lbl}>
                  {provider === 'snyk'
                    ? 'API base URL'
                    : provider === 'github_advanced_security'
                    ? 'API base URL'
                    : provider === 'semgrep'
                    ? 'API base URL'
                    : provider === 'custom'
                    ? 'Full endpoint URL (we will GET it)'
                    : 'Server URL'}
                </label>
                <input
                  className={input}
                  placeholder={
                    provider === 'sonarqube'
                      ? 'https://sonar.mycompany.com'
                      : provider === 'sonarcloud'
                      ? 'https://sonarcloud.io'
                      : provider === 'snyk'
                      ? 'https://api.snyk.io'
                      : provider === 'github_advanced_security'
                      ? 'https://api.github.com'
                      : provider === 'semgrep'
                      ? 'https://semgrep.dev'
                      : 'https://my-scanner.example.com/api/issues'
                  }
                  value={baseUrl}
                  onChange={(e) => setBaseUrl(e.target.value)}
                  data-testid="cq2-conn-baseurl"
                />
              </div>

              <div>
                <label className={lbl}>API Token</label>
                <input
                  type="password"
                  className={input}
                  placeholder="••••••••"
                  value={token}
                  onChange={(e) => setToken(e.target.value)}
                  data-testid="cq2-conn-token"
                />
                <p className="text-[11px] text-neutral-500 mt-1">Token is stored server-side and never returned to the frontend.</p>
              </div>

              {provider !== 'custom' && (
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className={lbl}>
                      {provider === 'sonarqube' || provider === 'sonarcloud'
                        ? 'Project Key'
                        : provider === 'snyk'
                        ? 'Project ID (optional)'
                        : provider === 'github_advanced_security'
                        ? 'Repo (owner/repo)'
                        : 'Deployment slug'}
                    </label>
                    <input
                      className={input}
                      placeholder={provider === 'github_advanced_security' ? 'octocat/Hello-World' : 'my-project'}
                      value={projectKey}
                      onChange={(e) => setProjectKey(e.target.value)}
                      data-testid="cq2-conn-projectkey"
                    />
                  </div>
                  {(provider === 'snyk' || provider === 'sonarcloud') && (
                    <div>
                      <label className={lbl}>Organization</label>
                      <input
                        className={input}
                        placeholder={provider === 'snyk' ? 'org-uuid' : 'my-org'}
                        value={org}
                        onChange={(e) => setOrg(e.target.value)}
                        data-testid="cq2-conn-org"
                      />
                    </div>
                  )}
                </div>
              )}

              {provider === 'custom' && (
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className={lbl}>Auth header</label>
                    <input className={input} value={customAuthHeader} onChange={(e) => setCustomAuthHeader(e.target.value)} />
                  </div>
                  <div>
                    <label className={lbl}>Auth prefix</label>
                    <input className={input} value={customAuthPrefix} onChange={(e) => setCustomAuthPrefix(e.target.value)} placeholder="Bearer " />
                  </div>
                </div>
              )}

              <div className="flex justify-end pt-2">
                <button
                  onClick={saveIntegration}
                  disabled={busy}
                  data-testid="cq2-conn-save"
                  className="flex items-center gap-2 px-5 py-2 bg-[#D4AF37] hover:bg-[#D4AF37]/90 text-black text-sm font-semibold rounded-md disabled:opacity-50"
                >
                  {busy ? <Loader2 size={14} className="animate-spin" /> : <Plug size={14} />}
                  Save Integration
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

// ============================================================================
// Issue Detail Drawer with "Generate Fix"
// ============================================================================
const IssueDrawer = ({ issue, scan, open, onClose, onFixGenerated }) => {
  const { model } = useActiveModel();
  const [genBusy, setGenBusy] = useState(false);
  const [ghRepo, setGhRepo] = useState('');
  const [ghToken, setGhToken] = useState('');
  const [branch, setBranch] = useState('');
  const [snippet, setSnippet] = useState('');
  const [fix, setFix] = useState(null);

  useEffect(() => {
    if (issue) {
      setFix(issue.fix || null);
      setSnippet('');
      // Pre-fill GH repo if the scan was github-sourced
      if (scan?.source === 'github' && scan?.meta?.repo_url) {
        const m = scan.meta.repo_url.match(/github\.com\/([^/]+)\/([^/.]+)/);
        if (m) setGhRepo(`${m[1]}/${m[2]}`);
        if (scan.meta.branch) setBranch(scan.meta.branch);
      }
    }
  }, [issue, scan]);

  if (!open || !issue) return null;

  const runFix = async () => {
    setGenBusy(true);
    try {
      const result = await cqGenerateFix(issue.id, {
        github_repo: ghRepo,
        github_token: ghToken,
        branch,
        user_snippet: snippet,
      });
      setFix(result);
      onFixGenerated && onFixGenerated(issue.id, result);
      toast.success('AI fix generated');
    } catch (e) {
      toast.error(e?.response?.data?.detail || 'Fix generation failed');
    } finally {
      setGenBusy(false);
    }
  };

  const sevClass = SEVERITY_COLORS[issue.severity] || SEVERITY_COLORS.minor;
  const typeClass = TYPE_COLORS[issue.type] || TYPE_COLORS.bug;
  const input = 'w-full bg-[#0A0A0A] border border-[#1f1f1f] rounded-md px-3 py-2 text-sm text-white placeholder:text-neutral-600 focus:outline-none focus:border-[#D4AF37]/50';

  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-black/60 backdrop-blur-sm" onClick={onClose}>
      <div
        className="bg-[#0d0d0d] border-l border-[#1f1f1f] w-full max-w-2xl h-full overflow-y-auto"
        onClick={(e) => e.stopPropagation()}
        data-testid="cq2-issue-drawer"
      >
        <div className="px-6 py-4 border-b border-[#1f1f1f] flex items-center justify-between sticky top-0 bg-[#0d0d0d] z-10">
          <div className="flex items-center gap-2 min-w-0">
            <Badge className={`${typeClass} border text-[10px] uppercase tracking-wider font-semibold`}>{TYPE_LABEL[issue.type] || issue.type}</Badge>
            <Badge className={`${sevClass} border text-[10px] uppercase tracking-wider font-semibold`}>{issue.severity}</Badge>
            <code className="text-[11px] text-neutral-500 truncate">{issue.rule}</code>
          </div>
          <button onClick={onClose} className="text-neutral-500 hover:text-white">
            <X size={18} />
          </button>
        </div>

        <div className="p-6 space-y-5">
          <div>
            <div className="text-sm text-white mb-2 font-medium">{issue.message}</div>
            <div className="text-[11px] text-neutral-500 font-mono flex items-center gap-1">
              <FileCode2 size={11} />
              {issue.file || '—'}:{issue.line}
            </div>
          </div>

          {issue.snippet && (
            <div>
              <div className="text-[11px] uppercase tracking-wider text-neutral-500 mb-1.5">Offending snippet</div>
              <pre className="bg-[#0A0A0A] border border-[#1f1f1f] rounded p-3 text-[12px] text-neutral-300 overflow-x-auto whitespace-pre-wrap">{issue.snippet}</pre>
            </div>
          )}

          {issue.recommendation && (
            <div>
              <div className="text-[11px] uppercase tracking-wider text-neutral-500 mb-1.5">Recommendation</div>
              <div className="text-sm text-neutral-300 bg-[#0A0A0A] border border-[#1f1f1f] rounded p-3">{issue.recommendation}</div>
            </div>
          )}

          {/* Fix generation panel */}
          <div className="bg-[#0A0A0A] border border-[#D4AF37]/20 rounded-lg p-4 space-y-3">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Wand2 size={14} className="text-[#D4AF37]" />
                <div className="text-sm font-semibold text-white">AI Fix <span className="font-mono text-[11px] text-neutral-400">({model})</span></div>
              </div>
            </div>
            <div className="text-[11px] text-neutral-500">
              Provide a GitHub repo (URL/owner-repo) for auto-fetching the full file, OR paste source manually below. Without either, we generate guidance based on the issue context.
            </div>

            <div className="grid grid-cols-2 gap-2">
              <input className={input} placeholder="owner/repo (e.g. octocat/Hello-World)" value={ghRepo} onChange={(e) => setGhRepo(e.target.value)} data-testid="cq2-fix-repo" />
              <input className={input} placeholder="branch (optional)" value={branch} onChange={(e) => setBranch(e.target.value)} />
            </div>
            <input
              className={input}
              type="password"
              placeholder="GitHub PAT (only for private repos)"
              value={ghToken}
              onChange={(e) => setGhToken(e.target.value)}
              data-testid="cq2-fix-token"
            />
            <textarea
              className={input + ' min-h-[80px] font-mono text-[12px]'}
              placeholder="…or paste the source of the affected file here"
              value={snippet}
              onChange={(e) => setSnippet(e.target.value)}
              data-testid="cq2-fix-snippet"
            />
            <button
              onClick={runFix}
              disabled={genBusy}
              data-testid="cq2-fix-generate"
              className="w-full flex items-center justify-center gap-2 px-4 py-2 bg-[#D4AF37] hover:bg-[#D4AF37]/90 text-black text-sm font-semibold rounded-md disabled:opacity-50"
            >
              {genBusy ? <Loader2 size={14} className="animate-spin" /> : <Sparkles size={14} />}
              {fix ? 'Regenerate Fix' : 'Generate Fix'}
            </button>
          </div>

          {fix && (
            <div className="space-y-4">
              <div>
                <div className="text-[11px] uppercase tracking-wider text-neutral-500 mb-1.5">Explanation</div>
                <div className="text-sm text-neutral-200 bg-[#0A0A0A] border border-[#1f1f1f] rounded p-3 whitespace-pre-wrap">{fix.explanation}</div>
              </div>
              {fix.diff && (
                <div>
                  <div className="text-[11px] uppercase tracking-wider text-neutral-500 mb-1.5">Diff</div>
                  <pre className="bg-[#0A0A0A] border border-[#1f1f1f] rounded p-3 text-[12px] text-emerald-300 overflow-x-auto whitespace-pre">{fix.diff}</pre>
                </div>
              )}
              {fix.patched_file && (
                <div>
                  <div className="text-[11px] uppercase tracking-wider text-neutral-500 mb-1.5">Patched file</div>
                  <pre className="bg-[#0A0A0A] border border-[#1f1f1f] rounded p-3 text-[12px] text-neutral-200 overflow-x-auto whitespace-pre">{fix.patched_file}</pre>
                </div>
              )}
              {fix.test_hint && (
                <div className="text-[11px] text-neutral-400 italic">💡 {fix.test_hint}</div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

// ============================================================================
// Integrations Panel (list)
// ============================================================================
const IntegrationsPanel = ({ integrations, onDeleted, onSyncStarted, onUpdated }) => {
  const [busyId, setBusyId] = useState(null);
  const remove = async (i) => {
    if (!window.confirm(`Delete integration "${i.name}"?`)) return;
    setBusyId(i.id);
    try {
      await cqDeleteIntegration(i.id);
      toast.success('Integration removed');
      onDeleted(i.id);
    } catch (e) {
      toast.error(e?.response?.data?.detail || 'Delete failed');
    } finally {
      setBusyId(null);
    }
  };
  const sync = async (i) => {
    if (i.enabled === false) {
      toast.error('Integration is disabled. Enable it first to sync.');
      return;
    }
    setBusyId(i.id);
    try {
      const scan = await cqSyncIntegration(i.id);
      toast.success(`Sync started: ${scan.source_label}`);
      onSyncStarted(scan);
    } catch (e) {
      toast.error(e?.response?.data?.detail || 'Sync failed');
    } finally {
      setBusyId(null);
    }
  };
  const toggle = async (i) => {
    const next = !(i.enabled !== false); // default true if undefined
    setBusyId(i.id);
    try {
      const updated = await cqUpdateIntegration(i.id, { enabled: next });
      toast.success(next ? `${i.name} enabled` : `${i.name} disabled`);
      onUpdated && onUpdated(updated);
    } catch (e) {
      toast.error(e?.response?.data?.detail || 'Toggle failed');
    } finally {
      setBusyId(null);
    }
  };

  if (integrations.length === 0) {
    return (
      <Card className="bg-[#0d0d0d] border-[#1f1f1f] p-5">
        <div className="text-center text-xs text-neutral-500 py-2">
          No scanner integrations yet. Click <span className="text-[#D4AF37]">"+ New Scan" → "Connect Dashboard"</span> to add one.
        </div>
      </Card>
    );
  }

  return (
    <Card className="bg-[#0d0d0d] border-[#1f1f1f] p-5">
      <div className="flex items-center justify-between mb-3">
        <h3 className="font-display font-bold text-base text-white flex items-center gap-2">
          <Plug size={14} className="text-[#D4AF37]" />
          Connected Scanners
        </h3>
        <span className="text-[11px] text-neutral-500">
          {integrations.filter((i) => i.enabled !== false).length} of {integrations.length} enabled
        </span>
      </div>
      <div className="space-y-2" data-testid="cq2-integrations-list">
        {integrations.map((i) => {
          const isEnabled = i.enabled !== false;
          return (
            <div
              key={i.id}
              className={`flex items-center justify-between p-3 bg-[#0A0A0A] border rounded-lg transition ${
                isEnabled ? 'border-[#1f1f1f] hover:border-[#D4AF37]/30' : 'border-[#1f1f1f] opacity-60'
              }`}
              data-testid={`cq2-integ-row-${i.id}`}
            >
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2 flex-wrap">
                  <Badge className="bg-neutral-700/30 text-neutral-200 border border-neutral-600/30 text-[10px] uppercase tracking-wider font-semibold">
                    {PROVIDER_LABEL[i.provider] || i.provider}
                  </Badge>
                  <div className="text-sm text-white font-medium truncate">{i.name}</div>
                  {!isEnabled && (
                    <Badge className="bg-neutral-500/15 text-neutral-300 border border-neutral-500/30 text-[10px] uppercase tracking-wider font-semibold">
                      disabled
                    </Badge>
                  )}
                </div>
                <div className="text-[11px] text-neutral-500 mt-0.5 truncate">
                  {i.base_url} {i.project_key ? `· ${i.project_key}` : ''} {i.last_status ? `· last: ${i.last_status}` : ''}
                </div>
              </div>
              <div className="flex items-center gap-2 flex-shrink-0 ml-3">
                {/* Toggle */}
                <button
                  onClick={() => toggle(i)}
                  disabled={busyId === i.id}
                  data-testid={`cq2-integ-toggle-${i.id}`}
                  className={`relative inline-flex h-5 w-9 items-center rounded-full transition-colors disabled:opacity-50 ${
                    isEnabled ? 'bg-emerald-500/70' : 'bg-neutral-700'
                  }`}
                  aria-label={isEnabled ? 'Disable integration' : 'Enable integration'}
                  title={isEnabled ? 'Disable' : 'Enable'}
                >
                  <span
                    className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${
                      isEnabled ? 'translate-x-4' : 'translate-x-0.5'
                    }`}
                  />
                </button>
                <button
                  onClick={() => sync(i)}
                  disabled={busyId === i.id || !isEnabled}
                  className="flex items-center gap-1.5 text-[11px] px-2.5 py-1 rounded-md bg-[#D4AF37]/10 hover:bg-[#D4AF37]/20 border border-[#D4AF37]/30 text-[#D4AF37] disabled:opacity-40 disabled:cursor-not-allowed"
                  data-testid={`cq2-integ-sync-${i.id}`}
                  title={isEnabled ? 'Sync now' : 'Enable to sync'}
                >
                  {busyId === i.id ? <Loader2 size={11} className="animate-spin" /> : <RefreshCw size={11} />}
                  Sync
                </button>
                <button
                  onClick={() => remove(i)}
                  disabled={busyId === i.id}
                  className="text-neutral-500 hover:text-red-400 disabled:opacity-50 p-1"
                  aria-label="Delete integration"
                  data-testid={`cq2-integ-delete-${i.id}`}
                  title="Delete integration"
                >
                  <Trash2 size={14} />
                </button>
              </div>
            </div>
          );
        })}
      </div>
    </Card>
  );
};

// ============================================================================
// Scan Row + Issues Table
// ============================================================================
const TotalsPill = ({ totals }) => {
  if (!totals || !totals.total) return <span className="text-[11px] text-neutral-500">0 issues</span>;
  return (
    <div className="flex items-center gap-1.5">
      <span className="text-[11px] text-neutral-300 font-semibold">{totals.total}</span>
      {totals.bug > 0 && (
        <span className="text-[10px] px-1.5 py-0.5 rounded bg-red-500/10 text-red-400 border border-red-500/30">
          <Bug size={9} className="inline mr-0.5" />
          {totals.bug}
        </span>
      )}
      {totals.vulnerability > 0 && (
        <span className="text-[10px] px-1.5 py-0.5 rounded bg-purple-500/10 text-purple-400 border border-purple-500/30">
          <Shield size={9} className="inline mr-0.5" />
          {totals.vulnerability}
        </span>
      )}
      {totals.code_smell > 0 && (
        <span className="text-[10px] px-1.5 py-0.5 rounded bg-amber-500/10 text-amber-400 border border-amber-500/30">
          <AlertTriangle size={9} className="inline mr-0.5" />
          {totals.code_smell}
        </span>
      )}
      {totals.security_hotspot > 0 && (
        <span className="text-[10px] px-1.5 py-0.5 rounded bg-pink-500/10 text-pink-400 border border-pink-500/30">
          🔥 {totals.security_hotspot}
        </span>
      )}
    </div>
  );
};

// ============================================================================
// Main panel
// ============================================================================
export default function CodeQualityScansPanel() {
  const { model } = useActiveModel();
  const [scans, setScans] = useState([]);
  const [integrations, setIntegrations] = useState([]);
  const [openScanId, setOpenScanId] = useState(null);
  const [issues, setIssues] = useState([]);
  const [issuesLoading, setIssuesLoading] = useState(false);
  const [activeIssue, setActiveIssue] = useState(null);
  const [showNewModal, setShowNewModal] = useState(false);
  const [loadingList, setLoadingList] = useState(true);
  const [seedBusy, setSeedBusy] = useState(false);

  const refreshAll = useCallback(async () => {
    try {
      const [s, i] = await Promise.all([cqListScans(), cqListIntegrations()]);
      setScans(s);
      setIntegrations(i);
    } catch (e) {
      // 401 handled by interceptor
    } finally {
      setLoadingList(false);
    }
  }, []);

  useEffect(() => {
    refreshAll();
  }, [refreshAll]);

  // Poll scans that are in flight every 5s
  useEffect(() => {
    const hasInFlight = scans.some((s) => s.status === 'queued' || s.status === 'scanning');
    if (!hasInFlight) return undefined;
    const t = setInterval(async () => {
      try {
        const fresh = await cqListScans();
        setScans(fresh);
        // also refresh integrations to update last_status
        const ints = await cqListIntegrations();
        setIntegrations(ints);
      } catch {
        // ignore
      }
    }, 5000);
    return () => clearInterval(t);
  }, [scans]);

  const loadIssues = useCallback(async (scanId) => {
    setIssuesLoading(true);
    setIssues([]);
    try {
      const list = await cqGetScanIssues(scanId);
      setIssues(list);
    } finally {
      setIssuesLoading(false);
    }
  }, []);

  const onOpenScan = (s) => {
    setOpenScanId(s.id);
    if (s.status === 'done') {
      loadIssues(s.id);
    } else {
      setIssues([]);
    }
  };

  const onDeleteScan = async (s) => {
    if (!window.confirm(`Delete scan "${s.source_label}"?`)) return;
    try {
      await cqDeleteScan(s.id);
      toast.success('Scan deleted');
      setScans((prev) => prev.filter((x) => x.id !== s.id));
      if (openScanId === s.id) {
        setOpenScanId(null);
        setIssues([]);
      }
    } catch (e) {
      toast.error('Delete failed');
    }
  };

  const onScanCreated = (scan) => {
    setScans((prev) => [scan, ...prev]);
    setOpenScanId(scan.id);
  };

  const onFixGenerated = (issueId, fix) => {
    setIssues((prev) => prev.map((it) => (it.id === issueId ? { ...it, fix } : it)));
  };

  const openScan = useMemo(() => scans.find((s) => s.id === openScanId) || null, [scans, openScanId]);

  const loadDemo = async (reset) => {
    if (reset && !window.confirm('This will DELETE all your current Code Quality scans, issues and integrations, then load fresh demo data. Continue?')) return;
    setSeedBusy(true);
    try {
      const res = await cqSeedDemo(reset);
      toast.success(`Demo loaded: ${res.scans_added} scans, ${res.issues_added} issues, ${res.integrations_added} integrations`);
      await refreshAll();
    } catch (e) {
      toast.error(e?.response?.data?.detail || 'Failed to load demo data');
    } finally {
      setSeedBusy(false);
    }
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <Card className="bg-[#0d0d0d] border-[#1f1f1f] p-5">
        <div className="flex items-center justify-between flex-wrap gap-3">
          <div>
            <h2 className="font-display font-bold text-xl text-white flex items-center gap-2">
              <Sparkles size={18} className="text-[#D4AF37]" />
              AI Code Quality Scans
            </h2>
            <p className="text-xs text-neutral-500 mt-1">
              Scan a GitHub repo, upload a .zip, or pull issues from your existing scanner — and get <span className="font-mono">{model}</span>-generated fixes.
            </p>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={() => loadDemo(scans.length > 0 || integrations.length > 0)}
              disabled={seedBusy}
              data-testid="cq2-seed-demo-btn"
              className="flex items-center gap-2 px-3 py-2 bg-emerald-500/10 hover:bg-emerald-500/20 border border-emerald-500/30 rounded-md text-xs text-emerald-300 disabled:opacity-50"
              title="Load realistic demo data for client presentations"
            >
              {seedBusy ? <Loader2 size={12} className="animate-spin" /> : <Database size={12} />}
              Load Demo Data
            </button>
            <button
              onClick={refreshAll}
              className="flex items-center gap-2 px-3 py-2 bg-[#161616] hover:bg-[#1f1f1f] border border-[#1f1f1f] rounded-md text-xs text-neutral-300"
            >
              <RefreshCw size={12} />
              Refresh
            </button>
            <button
              onClick={() => setShowNewModal(true)}
              data-testid="cq2-new-scan-btn"
              className="flex items-center gap-2 px-4 py-2 bg-[#D4AF37] hover:bg-[#D4AF37]/90 text-black text-sm font-semibold rounded-md"
            >
              <Plus size={14} />
              New Scan
            </button>
          </div>
        </div>
      </Card>

      {/* Integrations list */}
      <IntegrationsPanel
        integrations={integrations}
        onDeleted={(id) => setIntegrations((prev) => prev.filter((x) => x.id !== id))}
        onUpdated={(updated) =>
          setIntegrations((prev) => prev.map((x) => (x.id === updated.id ? { ...x, ...updated } : x)))
        }
        onSyncStarted={(scan) => {
          setScans((prev) => [scan, ...prev]);
          setOpenScanId(scan.id);
        }}
      />

      {/* Two-pane: scans list + selected scan issues */}
      <div className="grid grid-cols-12 gap-4">
        {/* LEFT: scans list */}
        <Card className="col-span-12 lg:col-span-5 bg-[#0d0d0d] border-[#1f1f1f] p-0 overflow-hidden">
          <div className="flex items-center justify-between px-4 py-3 border-b border-[#1f1f1f]">
            <h3 className="font-display font-bold text-base text-white">Scans</h3>
            <span className="text-[11px] text-neutral-500">{scans.length} total</span>
          </div>
          <div className="max-h-[600px] overflow-y-auto" data-testid="cq2-scans-list">
            {loadingList && (
              <div className="text-center text-xs text-neutral-500 py-10">Loading…</div>
            )}
            {!loadingList && scans.length === 0 && (
              <div className="text-center text-xs text-neutral-500 py-10">
                No scans yet. Click <span className="text-[#D4AF37]">"+ New Scan"</span> to get started.
              </div>
            )}
            {scans.map((s) => (
              <div
                key={s.id}
                className={`px-4 py-3 border-b border-[#161616] cursor-pointer transition ${
                  openScanId === s.id ? 'bg-[#D4AF37]/5 border-l-2 border-l-[#D4AF37]' : 'hover:bg-[#161616]/50'
                }`}
                onClick={() => onOpenScan(s)}
                data-testid={`cq2-scan-row-${s.id}`}
              >
                <div className="flex items-center justify-between gap-2 mb-1.5">
                  <div className="flex items-center gap-2 min-w-0">
                    <SourceIcon source={s.source} />
                    <div className="text-sm text-white truncate font-medium">{s.source_label}</div>
                  </div>
                  <StatusBadge status={s.status} />
                </div>
                <div className="flex items-center justify-between gap-2">
                  <TotalsPill totals={s.totals} />
                  <div className="flex items-center gap-2">
                    <span className="text-[10px] text-neutral-500">{fmtTime(s.created_at)}</span>
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        onDeleteScan(s);
                      }}
                      className="text-neutral-600 hover:text-red-400"
                      aria-label="Delete scan"
                    >
                      <Trash2 size={12} />
                    </button>
                  </div>
                </div>
                {s.error && (
                  <div className="mt-1.5 text-[10px] text-red-400 truncate">⚠ {s.error}</div>
                )}
              </div>
            ))}
          </div>
        </Card>

        {/* RIGHT: issues */}
        <Card className="col-span-12 lg:col-span-7 bg-[#0d0d0d] border-[#1f1f1f] p-0 overflow-hidden">
          <div className="flex items-center justify-between px-4 py-3 border-b border-[#1f1f1f]">
            <h3 className="font-display font-bold text-base text-white">
              {openScan ? <>Issues · <span className="text-neutral-400 font-normal">{openScan.source_label}</span></> : 'Issues'}
            </h3>
            {openScan && openScan.status === 'scanning' && (
              <div className="flex items-center gap-1.5 text-[11px] text-sky-300">
                <Loader2 size={11} className="animate-spin" />
                Analyzing with <span className="font-mono">{model}</span>…
              </div>
            )}
          </div>
          <div className="max-h-[600px] overflow-y-auto" data-testid="cq2-issues-list">
            {!openScan && (
              <div className="text-center text-xs text-neutral-500 py-16">
                ← Select a scan to view its issues
              </div>
            )}
            {openScan && openScan.status === 'failed' && (
              <div className="text-center text-xs text-red-400 py-10">Scan failed: {openScan.error || 'unknown'}</div>
            )}
            {openScan && (openScan.status === 'queued' || openScan.status === 'scanning') && (
              <div className="text-center text-xs text-neutral-500 py-10">
                <Loader2 size={20} className="animate-spin text-[#D4AF37] mx-auto mb-2" />
                Scan in progress… results will appear here.
              </div>
            )}
            {openScan && openScan.status === 'done' && issuesLoading && (
              <div className="text-center text-xs text-neutral-500 py-10">Loading issues…</div>
            )}
            {openScan && openScan.status === 'done' && !issuesLoading && issues.length === 0 && (
              <div className="text-center text-xs text-neutral-500 py-10">
                ✅ No issues found by this scan.
              </div>
            )}
            {issues.map((it) => {
              const sevClass = SEVERITY_COLORS[it.severity] || SEVERITY_COLORS.minor;
              const typeClass = TYPE_COLORS[it.type] || TYPE_COLORS.bug;
              return (
                <div
                  key={it.id}
                  className="px-4 py-3 border-b border-[#161616] hover:bg-[#161616]/50 cursor-pointer transition"
                  onClick={() => setActiveIssue(it)}
                  data-testid={`cq2-issue-${it.id}`}
                >
                  <div className="flex items-center gap-2 mb-1 flex-wrap">
                    <Badge className={`${typeClass} border text-[10px] uppercase tracking-wider font-semibold`}>{TYPE_LABEL[it.type] || it.type}</Badge>
                    <Badge className={`${sevClass} border text-[10px] uppercase tracking-wider font-semibold`}>{it.severity}</Badge>
                    <code className="text-[10px] text-neutral-500">{it.rule}</code>
                    {it.fix && (
                      <Badge className="bg-emerald-500/15 text-emerald-300 border border-emerald-500/30 text-[10px] uppercase tracking-wider font-semibold">
                        <Wand2 size={9} className="inline mr-0.5" /> fix ready
                      </Badge>
                    )}
                  </div>
                  <div className="text-sm text-white mb-1">{it.message}</div>
                  <div className="flex items-center justify-between gap-2 text-[11px] text-neutral-500 font-mono">
                    <span className="truncate flex items-center gap-1">
                      <FileCode2 size={10} />
                      {it.file || '—'}:{it.line}
                    </span>
                    <ChevronRight size={12} className="text-neutral-600 flex-shrink-0" />
                  </div>
                </div>
              );
            })}
          </div>
        </Card>
      </div>

      <NewScanModal
        open={showNewModal}
        onClose={() => setShowNewModal(false)}
        integrations={integrations}
        onScanCreated={onScanCreated}
        onIntegrationCreated={(i) => setIntegrations((prev) => [i, ...prev])}
        onIntegrationSyncStarted={(scan) => {
          setScans((prev) => [scan, ...prev]);
          setOpenScanId(scan.id);
        }}
      />

      <IssueDrawer
        issue={activeIssue}
        scan={openScan}
        open={!!activeIssue}
        onClose={() => setActiveIssue(null)}
        onFixGenerated={onFixGenerated}
      />

      <Toaster theme="dark" position="bottom-right" />
    </div>
  );
}
