"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import {
  Database,
  HardDrive,
  RefreshCw,
  ShieldCheck,
  Sparkles,
  Trash2,
  Users,
  X,
} from "lucide-react";
import "./editor.css";
import { storageSize } from "@/lib/format";
import "./settings.css";
import { AppearanceMenu } from "@/components/appearance";
import {
  AnalyticsChoices,
  useAnalyticsConsent,
} from "@/components/analytics-consent";
import { api, elapsed, type Workspace } from "@/lib/api";

type SettingsData = {
  storage_root: string;
  output_root: string;
  disk_free_bytes: number;
  minimum_free_bytes: number;
  usable_storage_bytes: number;
  export_disk_free_bytes: number;
  export_usable_storage_bytes: number;
  export_storage_separate_volume: boolean;
  workspace_file_count: number;
  workspace_project_count: number;
  workspace_uploaded_file_count: number;
  workspace_uploaded_source_bytes: number;
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

export function SettingsView({
  workspace,
  onManageFootage,
  onDeleteWorkspace,
}: {
  workspace: Workspace;
  onManageFootage: () => void;
  onDeleteWorkspace: () => void;
}) {
  const analytics = useAnalyticsConsent();
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
  const allowanceMinutes = config
    ? Math.max(0, config.balance_milli / 1000 / config.credits_per_minute)
    : 0;
  const allowanceLabel =
    allowanceMinutes > 0 && allowanceMinutes < 1
      ? "Less than 1"
      : Math.floor(allowanceMinutes).toLocaleString();
  return (
    <section className="settings-view workspace-settings">
      <div className="page-heading">
        <div>
          <span className="eyebrow">WORKSPACE</span>
          <h1>Settings & usage</h1>
          <p>Storage, AI allowance, and access for {workspace.name}.</p>
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
          {busy
            ? "Loading workspace settings…"
            : "Settings could not load. Use Refresh to try again."}
        </p>
      ) : (
        <>
          <section className="settings-card settings-storage">
            <div className="section-heading">
              <div>
                <h2>
                  <HardDrive size={21} /> Storage
                </h2>
                <p className="muted small">
                  Room for your footage and the files RUSHES creates.
                </p>
              </div>
              <button className="secondary" onClick={onManageFootage}>
                {workspace.role === "viewer"
                  ? "Browse footage"
                  : "Manage footage"}
              </button>
            </div>
            <p className="settings-capacity">
              <strong>{storageSize(config.usable_storage_bytes)}</strong>
              <span>available for new uploads</span>
            </p>
            <p className="settings-explanation">
              Shared by all workspaces on this server, after keeping{" "}
              {storageSize(config.minimum_free_bytes)} free for processing.
              Previews and analysis also need space.
            </p>
            {config.usable_storage_bytes === 0 && (
              <p className="settings-storage-full" role="status">
                There isn’t enough free space for another upload. Manage footage
                you no longer need, or ask the workspace operator for more
                storage.
              </p>
            )}
            {config.export_storage_separate_volume && (
              <p className="settings-explanation settings-export-capacity">
                Exports use a separate drive, with{" "}
                {storageSize(config.export_usable_storage_bytes)} available
                after the same processing reserve.
              </p>
            )}
            <dl className="settings-storage-stats">
              <div>
                <dt>Files in this workspace</dt>
                <dd>{config.workspace_file_count.toLocaleString()}</dd>
              </div>
              <div>
                <dt>Projects</dt>
                <dd>{config.workspace_project_count.toLocaleString()}</dd>
              </div>
              <div>
                <dt>Uploaded videos</dt>
                <dd>{storageSize(config.workspace_uploaded_source_bytes)}</dd>
              </div>
            </dl>
            <p className="settings-explanation small">
              {config.workspace_uploaded_file_count.toLocaleString()} uploaded{" "}
              {config.workspace_uploaded_file_count === 1 ? "file" : "files"}.
              Original uploads only. Previews and exports use extra space. Files
              linked from other folders aren’t included.
            </p>
          </section>
          <section className="settings-card settings-allowance">
            <div className="section-heading">
              <h2>
                <Sparkles size={21} /> AI allowance
              </h2>
              <span
                className={`settings-readiness ${config.gemini_configured && config.temporal_connected && config.media_tools_available ? "is-ready" : ""}`}
              >
                {!config.gemini_configured
                  ? "Needs setup"
                  : !config.temporal_connected || !config.media_tools_available
                    ? "Service unavailable"
                    : "AI is set up"}
              </span>
            </div>
            <p className="settings-capacity settings-allowance-number">
              <strong>{allowanceLabel}</strong>
              <span>
                {allowanceMinutes > 0 && allowanceMinutes < 2
                  ? "minute"
                  : "minutes"}{" "}
                in your workspace allowance
              </span>
            </p>
            <p className="settings-explanation">
              An estimate of the footage you can analyze with your remaining
              allowance. Analyzing a file again uses more allowance; existing
              footage stays available when it runs out.
            </p>
            {!config.gemini_configured ? (
              <p className="settings-guidance">
                Ask the workspace operator to enable AI analysis. You can still
                import and inspect footage.
              </p>
            ) : !config.temporal_connected || !config.media_tools_available ? (
              <p className="settings-guidance">
                Processing is temporarily unavailable. Ask the workspace
                operator to check the service.
              </p>
            ) : allowanceMinutes === 0 ? (
              <p className="settings-guidance">
                Ask the workspace operator for more AI allowance before
                analyzing new footage.
              </p>
            ) : (
              <p className="settings-explanation small">
                Up to{" "}
                {(
                  config.max_analysis_credits / config.credits_per_minute
                ).toLocaleString(undefined, { maximumFractionDigits: 1 })}{" "}
                minutes of footage per analysis request.
              </p>
            )}
          </section>
          {workspace.role === "owner" && (
            <section className="settings-card">
              <div className="section-heading">
                <h2>
                  <Users size={21} /> Workspace members
                </h2>
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
                        disabled={busy}
                        onClick={async () => {
                          if (busy) return;
                          setBusy(true);
                          setError("");
                          setNotice("");
                          try {
                            await api(`${base}/members/${member.id}`, {
                              method: "DELETE",
                            });
                            await refresh();
                            setNotice("Workspace access removed.");
                          } catch (e) {
                            setError((e as Error).message);
                          } finally {
                            setBusy(false);
                          }
                        }}
                      >
                        <X size={17} />
                      </button>
                    )}
                  </div>
                ))}
              </div>
              <details className="settings-add-member">
                <summary>Add a member</summary>
                <form
                  className="member-form"
                  onSubmit={async (event) => {
                    event.preventDefault();
                    if (busy) return;
                    setError("");
                    setNotice("");
                    const form = event.currentTarget,
                      data = new FormData(form);
                    setBusy(true);
                    try {
                      await api(`${base}/members`, {
                        method: "POST",
                        body: JSON.stringify({
                          email: String(data.get("email") || "").trim(),
                          role: data.get("role"),
                        }),
                      });
                      form.reset();
                      await refresh();
                      setNotice(
                        "Workspace membership saved. No email was sent.",
                      );
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
                    {busy ? "Saving…" : "Save access"}
                  </button>
                </form>
              </details>
            </section>
          )}
          <section className="settings-card appearance-settings">
            <div>
              <h2>Appearance</h2>
              <p className="muted small">
                Choose Light, Dark, or follow your system. Your choice stays
                with this browser.
              </p>
            </div>
            <AppearanceMenu />
          </section>
          <details className="settings-advanced settings-support">
            <summary>
              <span>Support details</span>
              <span className="small muted">
                Storage, processing, and usage records
              </span>
            </summary>
            <div className="settings-grid">
              <section className="settings-card">
                <div className="section-heading">
                  <HardDrive size={23} />
                  <h2>Server storage</h2>
                </div>
                <p className="storage-number">
                  {storageSize(config.disk_free_bytes)}
                  <span> free before the reserve</span>
                </p>
                <dl>
                  <dt>Kept free for processing</dt>
                  <dd>{storageSize(config.minimum_free_bytes)}</dd>
                  <dt>Export drive free space</dt>
                  <dd>
                    {storageSize(config.export_disk_free_bytes)}
                    {config.export_storage_separate_volume
                      ? " · separate drive"
                      : " · shared with uploads"}
                  </dd>
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
                      config.temporal_connected
                        ? "service-ok"
                        : "service-missing"
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
                      config.gemini_configured
                        ? "service-ok"
                        : "service-missing"
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
              <h2>Analysis credits</h2>
              <dl>
                <dt>Available balance</dt>
                <dd>
                  {(config.balance_milli / 1000).toLocaleString()} credits
                </dd>
                <dt>Rate per footage minute</dt>
                <dd>{config.credits_per_minute.toLocaleString()} credits</dd>
                <dt>Maximum per analysis request</dt>
                <dd>{config.max_analysis_credits.toLocaleString()} credits</dd>
              </dl>
              <p className="small muted">
                The balance excludes credits reserved for analysis already in
                progress. Unused reservations are returned after settlement.
                Retrying internal processing does not add a new charge. If a
                provider response is lost, RUSHES records the uncertain outcome
                and avoids automatically repeating the request.
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
                <details className="usage-details">
                  <summary>View activity & credit ledger</summary>
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
                              <td>{storageSize(metric.bytes)}</td>
                              <td>{metric.input_tokens.toLocaleString()}</td>
                              <td>{metric.output_tokens.toLocaleString()}</td>
                              <td>{metric.attempts}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  ) : (
                    <p className="muted">
                      Usage appears after your first import.
                    </p>
                  )}
                  <h3>Credit ledger</h3>
                  <div className="ledger-list">
                    {usage.ledger.map((entry) => (
                      <div key={entry.id}>
                        <div>
                          <strong>{entry.description}</strong>
                          <span>
                            {new Date(entry.created_at).toLocaleString()}
                          </span>
                        </div>
                        <strong>
                          {entry.delta_milli >= 0 ? "+" : ""}
                          {(entry.delta_milli / 1000).toLocaleString()}
                        </strong>
                        <span>
                          {(entry.balance_milli / 1000).toLocaleString()}{" "}
                          remaining
                        </span>
                      </div>
                    ))}
                  </div>
                </details>
              </section>
            )}
          </details>
          <section className="settings-card">
            <h2>Privacy & analytics</h2>
            <p className="muted small">
              {!analytics.configured
                ? "Optional analytics are not configured."
                : analytics.choice === "accepted"
                  ? "Optional Google Analytics are allowed in this browser."
                  : "Optional Google Analytics are currently off in this browser."}
            </p>
            <AnalyticsChoices />
            <p className="muted small">
              Session cookies keep your account signed in. Read the{" "}
              <a href="/privacy">Privacy policy</a> and{" "}
              <a href="/terms">Terms</a> for details.
            </p>
          </section>
          {workspace.role === "owner" && (
            <section className="settings-card settings-delete-workspace">
              <div>
                <h2>Delete workspace</h2>
                <p className="muted small">
                  Remove this workspace and its projects. You’ll review what
                  will be removed before confirming.
                </p>
              </div>
              <button className="secondary" onClick={onDeleteWorkspace}>
                <Trash2 size={16} /> Delete workspace
              </button>
            </section>
          )}
        </>
      )}
    </section>
  );
}
