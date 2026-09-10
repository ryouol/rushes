"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import {
  Check,
  Database,
  HardDrive,
  RefreshCw,
  ShieldCheck,
  Users,
  X,
} from "lucide-react";
import { api, elapsed, type Workspace } from "@/lib/api";

type SettingsData = {
  storage_root: string;
  output_root: string;
  disk_free_bytes: number;
  source_roots: string[];
  gemini_configured: boolean;
  gemini_model: string;
  transcription_model: string;
  embedding_model: string;
  compute_backend: "local" | "modal";
  temporal_connected: boolean;
  media_tools_available: boolean;
  balance_milli: number;
  credits_per_minute: number;
  max_analysis_credits: number;
};
type UsageData = {
  unique_source_duration_us: number;
  metrics: {
    kind: string;
    duration_us: number;
    bytes: number;
    input_tokens: number;
    output_tokens: number;
    attempts: number;
  }[];
  ledger: {
    id: string;
    kind: string;
    delta_milli: number;
    balance_milli: number;
    description: string;
    created_at: string;
  }[];
};
type Member = { id: string; email: string; name: string; role: string };

export function SettingsView({ workspace }: { workspace: Workspace }) {
  const [config, setConfig] = useState<SettingsData | null>(null),
    [usage, setUsage] = useState<UsageData | null>(null),
    [members, setMembers] = useState<Member[]>([]);
  const [error, setError] = useState(""),
    [notice, setNotice] = useState(""),
    [busy, setBusy] = useState(false);
  const base = `/workspaces/${workspace.id}`;
  const refreshRequest = useRef<AbortController | null>(null);
  const refresh = useCallback(async () => {
    refreshRequest.current?.abort();
    const request = new AbortController();
    refreshRequest.current = request;
    const options = { signal: request.signal };
    setBusy(true);
    setError("");
    try {
      const [config, usage, members] = await Promise.all([
        api<SettingsData>(`${base}/settings`, options),
        api<UsageData>(`${base}/usage`, options),
        workspace.role === "owner"
          ? api<Member[]>(`${base}/members`, options)
          : Promise.resolve([]),
      ]);
      if (request.signal.aborted) return;
      setConfig(config);
      setUsage(usage);
      setMembers(members);
    } catch (e) {
      if (!request.signal.aborted) setError((e as Error).message);
    } finally {
      if (!request.signal.aborted) setBusy(false);
    }
  }, [base, workspace.role]);
  useEffect(() => {
    void refresh();
    return () => refreshRequest.current?.abort();
  }, [refresh]);
  return (
    <section>
      <div className="page-heading">
        <div>
          <span className="eyebrow">WORKSPACE</span>
          <h1>Settings & usage</h1>
          <p>Local storage, processing services, and workspace access.</p>
        </div>
        <button
          className="secondary"
          disabled={busy}
          onClick={() => void refresh()}
        >
          <RefreshCw size={16} />
          {busy ? "Refreshing…" : "Refresh"}
        </button>
      </div>
      {error && (
        <p className="notice danger" role="alert">
          {error}
        </p>
      )}
      {notice && (
        <p className="notice" role="status">
          {notice}
        </p>
      )}
      {!config ? (
        <p className="muted" role="status">
          Checking processing services…
        </p>
      ) : (
        <>
          <div className="settings-grid">
            <section className="settings-card">
              <div className="section-heading">
                <HardDrive size={23} />
                <h2>Server storage</h2>
              </div>
              <p className="storage-number">
                {(config.disk_free_bytes / 1024 ** 3).toFixed(1)}
                <span> GB free</span>
              </p>
              <dl>
                <dt>Private working files</dt>
                <dd>{config.storage_root}</dd>
                <dt>Export folder</dt>
                <dd>{config.output_root}</dd>
              </dl>
              <p className="small muted">
                Originals stay at their selected source locations. File-picker
                uploads are copied into private working storage.
              </p>
              <h3>Configured source roots</h3>
              {config.source_roots.length ? (
                <ul className="root-list">
                  {config.source_roots.map((root) => (
                    <li key={root}>{root}</li>
                  ))}
                </ul>
              ) : (
                <p className="small muted">
                  No source roots configured. Use the file picker to import
                  footage, or ask the instance operator to configure a source
                  folder on the server for indexing without copying.
                </p>
              )}
            </section>
            <section className="settings-card">
              <div className="section-heading">
                <Database size={23} />
                <h2>Processing</h2>
              </div>
              <div className="service-row">
                <span>Temporal connection</span>
                <strong
                  className={
                    config.temporal_connected ? "service-ok" : "service-missing"
                  }
                >
                  {config.temporal_connected ? "Connected" : "Disconnected"}
                </strong>
              </div>
              <div className="service-row">
                <span>FFmpeg & ffprobe</span>
                <strong
                  className={
                    config.media_tools_available
                      ? "service-ok"
                      : "service-missing"
                  }
                >
                  {config.media_tools_available ? "Available" : "Missing"}
                </strong>
              </div>
              <div className="service-row">
                <span>Gemini analysis</span>
                <strong
                  className={
                    config.gemini_configured ? "service-ok" : "service-missing"
                  }
                >
                  {config.gemini_configured ? "Configured" : "Needs API key"}
                </strong>
              </div>
              <dl>
                <dt>Video analyzer</dt>
                <dd>{config.gemini_model}</dd>
                <dt>Speech and embedding compute</dt>
                <dd>
                  {config.compute_backend === "modal"
                    ? "Modal"
                    : "RUSHES server"}
                </dd>
                <dt>Speech transcription</dt>
                <dd>
                  faster-whisper · {config.transcription_model} · CPU int8
                </dd>
                <dt>Text embedding</dt>
                <dd>{config.embedding_model}</dd>
              </dl>
              {!config.gemini_configured && (
                <p className="small muted">
                  Ask the instance operator to configure Gemini access. Then
                  review the estimate for any source you want to analyze.
                  Derived video and transcript context are sent to Google.
                </p>
              )}
              {config.compute_backend === "modal" && (
                <p className="small muted">
                  Derived audio, worklog text and search queries are sent to
                  private Modal functions for processing.
                </p>
              )}
            </section>
          </div>
          <section className="settings-card">
            <div className="section-heading">
              <div>
                <h2>Processing credits</h2>
                <p className="muted small">
                  Credits provided by this instance. No checkout or live
                  payments.
                </p>
              </div>
              <strong className="credit-balance">
                {(config.balance_milli / 1000).toLocaleString()}
                <span> credits available</span>
              </strong>
            </div>
            <div className="credit-rules">
              <span>{config.credits_per_minute} credit per footage minute</span>
              <span>
                {config.max_analysis_credits} credit limit per analysis request
              </span>
              <span>Internal activity retries do not add customer debits</span>
            </div>
            <p className="small muted">
              Credits are reserved before analysis and settled against confirmed
              work. A lost provider response can have an uncertain billing
              outcome; RUSHES records that state and avoids automatic repeats.
            </p>
          </section>
          {usage && (
            <section className="settings-card">
              <div className="section-heading">
                <h2>Measured usage</h2>
                <span className="timecode">
                  UNIQUE SOURCE {elapsed(usage.unique_source_duration_us)}
                </span>
              </div>
              {usage.metrics.length ? (
                <div className="table-scroll">
                  <table>
                    <thead>
                      <tr>
                        <th>Operation</th>
                        <th>Duration</th>
                        <th>Recorded bytes</th>
                        <th>Input tokens</th>
                        <th>Output tokens</th>
                        <th>Attempts</th>
                      </tr>
                    </thead>
                    <tbody>
                      {usage.metrics.map((metric) => (
                        <tr key={metric.kind}>
                          <td>{metric.kind}</td>
                          <td className="timecode">
                            {elapsed(metric.duration_us)}
                          </td>
                          <td>{(metric.bytes / 1024 ** 2).toFixed(1)} MB</td>
                          <td>{metric.input_tokens.toLocaleString()}</td>
                          <td>{metric.output_tokens.toLocaleString()}</td>
                          <td>{metric.attempts}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <p className="muted">Usage appears after your first import.</p>
              )}
              <h3>Credit ledger</h3>
              <div className="ledger-list">
                {usage.ledger.map((entry) => (
                  <div key={entry.id}>
                    <div>
                      <strong>{entry.description}</strong>
                      <span>{new Date(entry.created_at).toLocaleString()}</span>
                    </div>
                    <strong>
                      {entry.delta_milli >= 0 ? "+" : ""}
                      {(entry.delta_milli / 1000).toLocaleString()}
                    </strong>
                    <span>
                      {(entry.balance_milli / 1000).toLocaleString()} remaining
                    </span>
                  </div>
                ))}
              </div>
            </section>
          )}
          {workspace.role === "owner" && (
            <section className="settings-card">
              <div className="section-heading">
                <Users size={23} />
                <h2>Workspace members</h2>
              </div>
              <p className="small muted">
                Owners manage access. Editors can import, correct, organize, and
                export. Viewers can review footage and download completed
                exports.
              </p>
              <div className="members-list">
                {members.map((member) => (
                  <div key={member.id}>
                    <div>
                      <strong>{member.name}</strong>
                      <span>{member.email}</span>
                    </div>
                    <span className="state">{member.role}</span>
                    {member.role !== "owner" && (
                      <button
                        className="icon-button"
                        aria-label={`Remove access for ${member.email}`}
                        onClick={async () => {
                          try {
                            await api(`${base}/members/${member.id}`, {
                              method: "DELETE",
                            });
                            await refresh();
                            setNotice("Workspace access removed.");
                          } catch (e) {
                            setError((e as Error).message);
                          }
                        }}
                      >
                        <X size={17} />
                      </button>
                    )}
                  </div>
                ))}
              </div>
              <form
                className="member-form"
                onSubmit={async (event) => {
                  event.preventDefault();
                  const form = event.currentTarget,
                    data = new FormData(form);
                  setBusy(true);
                  try {
                    await api(`${base}/members`, {
                      method: "POST",
                      body: JSON.stringify({
                        email: data.get("email"),
                        role: data.get("role"),
                      }),
                    });
                    form.reset();
                    await refresh();
                    setNotice("Workspace membership saved. No email was sent.");
                  } catch (e) {
                    setError((e as Error).message);
                  } finally {
                    setBusy(false);
                  }
                }}
              >
                <label className="field">
                  <span>Existing account email</span>
                  <input
                    name="email"
                    type="email"
                    required
                    placeholder="editor@example.com"
                  />
                </label>
                <label className="field">
                  <span>Role</span>
                  <select name="role">
                    <option value="editor">Editor</option>
                    <option value="viewer">Viewer</option>
                  </select>
                </label>
                <button className="primary" disabled={busy}>
                  <ShieldCheck size={16} />
                  Save access
                </button>
              </form>
            </section>
          )}
          <section className="settings-card">
            <h2>Privacy & analytics</h2>
            <p className="muted small">
              Analytics are disabled. Session cookies keep your account signed
              in. The Privacy and Terms pages are clearly marked drafts awaiting
              business review.
            </p>
          </section>
        </>
      )}
    </section>
  );
}
