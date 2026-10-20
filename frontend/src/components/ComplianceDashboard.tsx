import { useState, useEffect } from "react";
import {
  listJurisdictions,
  createOrg,
  listEntities,
  createEntity,
  listLicenses,
  createLicense,
  listDeadlines,
  runWorkflow,
  listTasks,
  listApprovals,
  decideApproval,
  verifyAudit,
  listRegulatorySources,
  createRegulatorySource,
  ingestRegulation,
  listRegulationVersions,
  listReviewQueue,
  decideObligation,
  type Jurisdiction,
  type Org,
  type Entity,
  type License,
  type Deadline,
  type Task,
  type Approval,
  type WorkflowResult,
  type RegulationSource,
  type RegulationVersion,
  type IngestResult,
  type Obligation,
} from "../api";
import { getApiKey } from "../api";

type Tab =
  | "dashboard"
  | "licenses"
  | "deadlines"
  | "tasks"
  | "approvals"
  | "regulations"
  | "review"
  | "audit";

export function ComplianceDashboard() {
  const [tab, setTab] = useState<Tab>("dashboard");
  const [orgs, setOrgs] = useState<Org[]>([]);
  const [currentOrg, setCurrentOrg] = useState<Org | null>(null);
  const [entities, setEntities] = useState<Entity[]>([]);
  const [currentEntity, setCurrentEntity] = useState<Entity | null>(null);
  const [jurisdictions, setJurisdictions] = useState<Jurisdiction[]>([]);
  const [licenses, setLicenses] = useState<License[]>([]);
  const [deadlines, setDeadlines] = useState<Deadline[]>([]);
  const [tasks, setTasks] = useState<Task[]>([]);
  const [approvals, setApprovals] = useState<Approval[]>([]);
  const [workflowResult, setWorkflowResult] = useState<WorkflowResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [newOrgName, setNewOrgName] = useState("");
  const [newEntityName, setNewEntityName] = useState("");
  const [newEntityState, setNewEntityState] = useState("CA");
  const [newLicense, setNewLicense] = useState({
    license_type: "MTL",
    authority: "",
    jurisdiction_id: "",
    expires_on: "",
  });
  const [decisionRationale, setDecisionRationale] = useState("");

  // Phase 2 — regulatory monitoring
  const [sources, setSources] = useState<RegulationSource[]>([]);
  const [versions, setVersions] = useState<RegulationVersion[]>([]);
  const [versionsCitation, setVersionsCitation] = useState("");
  const [reviewQueue, setReviewQueue] = useState<Obligation[]>([]);
  const [reviewRationale, setReviewRationale] = useState<Record<string, string>>({});
  const [ingestResult, setIngestResult] = useState<IngestResult | null>(null);
  const [sourceForm, setSourceForm] = useState({
    jurisdiction_code: "US-CA",
    name: "",
    url: "",
  });
  const [ingestForm, setIngestForm] = useState({
    jurisdiction_code: "US-CA",
    source_url: "",
    citation: "",
    title: "",
    publisher: "",
  });

  const apiKey = getApiKey();

  useEffect(() => {
    loadJurisdictions();
  }, []);

  async function loadJurisdictions() {
    if (!apiKey) return;
    try {
      const j = await listJurisdictions(apiKey);
      setJurisdictions(j);
    } catch (e) {
      setError(e instanceof Error ? e.message : "failed to load jurisdictions");
    }
  }

  async function loadEntities(orgId: string) {
    if (!apiKey) return;
    try {
      const e = await listEntities(orgId, apiKey);
      setEntities(e);
    } catch (e) {
      setError(e instanceof Error ? e.message : "failed to load entities");
    }
  }

  async function loadLicenses(entityId: string) {
    if (!apiKey) return;
    try {
      const l = await listLicenses(entityId, apiKey);
      setLicenses(l);
    } catch (e) {
      setError(e instanceof Error ? e.message : "failed to load licenses");
    }
  }

  async function loadDeadlines() {
    if (!apiKey) return;
    try {
      const d = await listDeadlines(90, apiKey);
      setDeadlines(d);
    } catch (e) {
      setError(e instanceof Error ? e.message : "failed to load deadlines");
    }
  }

  async function loadTasks() {
    if (!apiKey) return;
    try {
      const t = await listTasks(apiKey);
      setTasks(t);
    } catch (e) {
      setError(e instanceof Error ? e.message : "failed to load tasks");
    }
  }

  async function loadApprovals() {
    if (!apiKey) return;
    try {
      const a = await listApprovals(apiKey);
      setApprovals(a);
    } catch (e) {
      setError(e instanceof Error ? e.message : "failed to load approvals");
    }
  }

  async function loadSources() {
    if (!apiKey) return;
    try {
      setSources(await listRegulatorySources(apiKey));
    } catch (e) {
      setError(e instanceof Error ? e.message : "failed to load sources");
    }
  }

  async function loadReviewQueue() {
    if (!apiKey) return;
    try {
      setReviewQueue(await listReviewQueue(apiKey));
    } catch (e) {
      setError(e instanceof Error ? e.message : "failed to load review queue");
    }
  }

  async function loadVersions(citation: string) {
    if (!apiKey || !citation.trim()) return;
    try {
      setVersions(await listRegulationVersions(citation.trim(), apiKey));
      setVersionsCitation(citation.trim());
    } catch (e) {
      setError(e instanceof Error ? e.message : "failed to load versions");
    }
  }

  /** Poll a citation's versions until indexing settles (or we give up). */
  async function pollVersions(citation: string, attempts = 12) {
    if (!apiKey) return;
    for (let i = 0; i < attempts; i++) {
      await new Promise((r) => setTimeout(r, 8000));
      try {
        const v = await listRegulationVersions(citation, apiKey);
        setVersions(v);
        setVersionsCitation(citation);
        if (v.every((x) => x.index_status !== "PENDING")) return;
      } catch {
        return;
      }
    }
  }

  async function handleCreateSource() {
    if (!apiKey || !sourceForm.name.trim() || !sourceForm.url.trim()) return;
    setLoading(true);
    setError(null);
    try {
      await createRegulatorySource(
        {
          jurisdiction_code: sourceForm.jurisdiction_code,
          name: sourceForm.name.trim(),
          url: sourceForm.url.trim(),
        },
        apiKey,
      );
      setSourceForm({ jurisdiction_code: sourceForm.jurisdiction_code, name: "", url: "" });
      await loadSources();
    } catch (e) {
      setError(e instanceof Error ? e.message : "failed to create source");
    } finally {
      setLoading(false);
    }
  }

  async function handleIngest() {
    if (!apiKey || !ingestForm.citation.trim() || !ingestForm.source_url.trim()) return;
    setLoading(true);
    setError(null);
    setIngestResult(null);
    try {
      const result = await ingestRegulation(
        {
          jurisdiction_code: ingestForm.jurisdiction_code,
          source_url: ingestForm.source_url.trim(),
          citation: ingestForm.citation.trim(),
          title: ingestForm.title.trim() || ingestForm.citation.trim(),
          publisher: ingestForm.publisher.trim() || undefined,
        },
        apiKey,
      );
      setIngestResult(result);
      await loadVersions(ingestForm.citation);
      // Indexing runs in the background; watch it settle.
      if (result.index_status === "PENDING") {
        void pollVersions(ingestForm.citation);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "failed to ingest regulation");
    } finally {
      setLoading(false);
    }
  }

  async function handleDecideObligation(id: string, decision: "APPROVED" | "REJECTED") {
    if (!apiKey) return;
    setLoading(true);
    setError(null);
    try {
      await decideObligation(id, decision, reviewRationale[id] ?? "", apiKey);
      setReviewQueue((prev) => prev.filter((o) => o.id !== id));
      setReviewRationale((prev) => {
        const next = { ...prev };
        delete next[id];
        return next;
      });
    } catch (e) {
      setError(e instanceof Error ? e.message : "failed to record decision");
    } finally {
      setLoading(false);
    }
  }

  async function handleCreateOrg() {
    if (!newOrgName.trim() || !apiKey) return;
    setLoading(true);
    setError(null);
    try {
      const org = await createOrg(newOrgName.trim(), "fintech", apiKey);
      setOrgs((prev) => [...prev, org]);
      setCurrentOrg(org);
      setNewOrgName("");
      await loadEntities(org.id);
    } catch (e) {
      setError(e instanceof Error ? e.message : "failed to create org");
    } finally {
      setLoading(false);
    }
  }

  async function handleCreateEntity() {
    if (!newEntityName.trim() || !currentOrg || !apiKey) return;
    setLoading(true);
    setError(null);
    try {
      const entity = await createEntity(currentOrg.id, newEntityName.trim(), newEntityState, apiKey);
      setEntities((prev) => [...prev, entity]);
      setCurrentEntity(entity);
      setNewEntityName("");
      await loadLicenses(entity.id);
    } catch (e) {
      setError(e instanceof Error ? e.message : "failed to create entity");
    } finally {
      setLoading(false);
    }
  }

  async function handleCreateLicense() {
    if (!currentEntity || !newLicense.jurisdiction_id || !newLicense.expires_on || !apiKey) return;
    setLoading(true);
    setError(null);
    try {
      const lic = await createLicense(currentEntity.id, {
        license_type: newLicense.license_type,
        authority: newLicense.authority || "Regulator",
        jurisdiction_id: newLicense.jurisdiction_id,
        expires_on: newLicense.expires_on,
      }, apiKey);
      setLicenses((prev) => [...prev, lic]);
      setNewLicense({ license_type: "MTL", authority: "", jurisdiction_id: "", expires_on: "" });
    } catch (e) {
      setError(e instanceof Error ? e.message : "failed to create license");
    } finally {
      setLoading(false);
    }
  }

  async function handleRunWorkflow() {
    if (!currentOrg || !apiKey) return;
    setLoading(true);
    setError(null);
    try {
      const result = await runWorkflow(currentOrg.id, currentEntity?.id, apiKey);
      setWorkflowResult(result);
      await loadDeadlines();
      await loadTasks();
    } catch (e) {
      setError(e instanceof Error ? e.message : "workflow failed");
    } finally {
      setLoading(false);
    }
  }

  async function handleDecideApproval(approvalId: string, decision: "APPROVED" | "REJECTED") {
    if (!apiKey) return;
    setLoading(true);
    setError(null);
    try {
      await decideApproval(approvalId, decision, decisionRationale, apiKey);
      setDecisionRationale("");
      await loadApprovals();
    } catch (e) {
      setError(e instanceof Error ? e.message : "decision failed");
    } finally {
      setLoading(false);
    }
  }

  const tabs: { id: Tab; label: string }[] = [
    { id: "dashboard", label: "Dashboard" },
    { id: "licenses", label: "Licenses" },
    { id: "deadlines", label: "Deadlines" },
    { id: "tasks", label: "Tasks" },
    { id: "approvals", label: "Approvals" },
    { id: "regulations", label: "Regulations" },
    { id: "review", label: "Review Queue" },
    { id: "audit", label: "Audit" },
  ];

  return (
    <div className="compliance-dashboard">
      {/* Tab bar */}
      <div className="comp-tabs">
        {tabs.map((t) => (
          <button
            key={t.id}
            className={`comp-tab ${tab === t.id ? "active" : ""}`}
            onClick={() => {
              setTab(t.id);
              setError(null);
              if (t.id === "deadlines") loadDeadlines();
              if (t.id === "tasks") loadTasks();
              if (t.id === "approvals") loadApprovals();
              if (t.id === "regulations") loadSources();
              if (t.id === "review") loadReviewQueue();
            }}
          >
            {t.label}
          </button>
        ))}
      </div>

      {error && <div className="error-banner">{error}</div>}

      {/* Dashboard tab */}
      {tab === "dashboard" && (
        <div className="comp-panel">
          <h2>Compliance Dashboard</h2>

          {/* Org selector / creator */}
          <div className="comp-section">
            <h3>Organization</h3>
            {orgs.length > 0 && (
              <select
                value={currentOrg?.id ?? ""}
                onChange={(e) => {
                  const org = orgs.find((o) => o.id === e.target.value);
                  setCurrentOrg(org ?? null);
                  if (org) loadEntities(org.id);
                }}
              >
                <option value="">Select org…</option>
                {orgs.map((o) => (
                  <option key={o.id} value={o.id}>
                    {o.legal_name}
                  </option>
                ))}
              </select>
            )}
            <div className="inline-form">
              <input
                type="text"
                placeholder="New org name"
                value={newOrgName}
                onChange={(e) => setNewOrgName(e.target.value)}
              />
              <button className="btn-primary" onClick={handleCreateOrg} disabled={loading || !newOrgName.trim()}>
                Create
              </button>
            </div>
          </div>

          {/* Entity selector / creator */}
          {currentOrg && (
            <div className="comp-section">
              <h3>Legal Entity</h3>
              {entities.length > 0 && (
                <select
                  value={currentEntity?.id ?? ""}
                  onChange={(e) => {
                    const ent = entities.find((en) => en.id === e.target.value);
                    setCurrentEntity(ent ?? null);
                    if (ent) loadLicenses(ent.id);
                  }}
                >
                  <option value="">Select entity…</option>
                  {entities.map((e) => (
                    <option key={e.id} value={e.id}>
                      {e.name} ({e.state})
                    </option>
                  ))}
                </select>
              )}
              <div className="inline-form">
                <input
                  type="text"
                  placeholder="New entity name"
                  value={newEntityName}
                  onChange={(e) => setNewEntityName(e.target.value)}
                />
                <select value={newEntityState} onChange={(e) => setNewEntityState(e.target.value)}>
                  <option value="CA">CA</option>
                  <option value="NY">NY</option>
                  <option value="TX">TX</option>
                  <option value="FL">FL</option>
                  <option value="IL">IL</option>
                </select>
                <button className="btn-primary" onClick={handleCreateEntity} disabled={loading || !newEntityName.trim()}>
                  Create
                </button>
              </div>
            </div>
          )}

          {/* Workflow trigger */}
          {currentOrg && (
            <div className="comp-section">
              <h3>Run Compliance Check</h3>
              <button className="btn-primary" onClick={handleRunWorkflow} disabled={loading}>
                {loading ? "Running…" : "Run Deadline Check"}
              </button>
              {workflowResult && (
                <div className="workflow-result">
                  <p><strong>Status:</strong> {workflowResult.status}</p>
                  <p><strong>Tasks created:</strong> {workflowResult.tasks_created}</p>
                  <p><strong>Overdue:</strong> {workflowResult.overdue_count}</p>
                  <p><strong>Escalated:</strong> {workflowResult.escalated_count}</p>
                  {workflowResult.upcoming_deadlines.length > 0 && (
                    <ul>
                      {workflowResult.upcoming_deadlines.map((d, i) => (
                        <li key={i}>
                          {d.license_type} — expires {d.expires_on} ({d.days_until_deadline} days) — escalation level {d.escalation_level}
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {/* Licenses tab */}
      {tab === "licenses" && (
        <div className="comp-panel">
          <h2>Licenses</h2>
          {currentEntity ? (
            <>
              <div className="comp-section">
                <h3>Add License</h3>
                <div className="inline-form">
                  <select
                    value={newLicense.license_type}
                    onChange={(e) => setNewLicense({ ...newLicense, license_type: e.target.value })}
                  >
                    <option value="MTL">MTL</option>
                    <option value="lending">Lending</option>
                    <option value="broker_dealer">Broker-Dealer</option>
                  </select>
                  <input
                    type="text"
                    placeholder="Authority (e.g. CA DFPI)"
                    value={newLicense.authority}
                    onChange={(e) => setNewLicense({ ...newLicense, authority: e.target.value })}
                  />
                  <select
                    value={newLicense.jurisdiction_id}
                    onChange={(e) => setNewLicense({ ...newLicense, jurisdiction_id: e.target.value })}
                  >
                    <option value="">Jurisdiction…</option>
                    {jurisdictions.map((j) => (
                      <option key={j.id} value={j.id}>
                        {j.code} — {j.name}
                      </option>
                    ))}
                  </select>
                  <input
                    type="date"
                    value={newLicense.expires_on}
                    onChange={(e) => setNewLicense({ ...newLicense, expires_on: e.target.value })}
                  />
                  <button className="btn-primary" onClick={handleCreateLicense} disabled={loading}>
                    Add
                  </button>
                </div>
              </div>
              {licenses.length > 0 ? (
                <table className="comp-table">
                  <thead>
                    <tr>
                      <th>Type</th>
                      <th>Authority</th>
                      <th>Expires</th>
                      <th>Status</th>
                    </tr>
                  </thead>
                  <tbody>
                    {licenses.map((l) => (
                      <tr key={l.id}>
                        <td>{l.license_type}</td>
                        <td>{l.authority}</td>
                        <td>{l.expires_on ?? "—"}</td>
                        <td>
                          <span className={`status-badge ${l.status.toLowerCase()}`}>
                            {l.status}
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              ) : (
                <div className="empty-state">No licenses yet. Add one above.</div>
              )}
            </>
          ) : (
            <div className="empty-state">Select an organization and entity first.</div>
          )}
        </div>
      )}

      {/* Deadlines tab */}
      {tab === "deadlines" && (
        <div className="comp-panel">
          <h2>Upcoming Deadlines</h2>
          {deadlines.length > 0 ? (
            <table className="comp-table">
              <thead>
                <tr>
                  <th>License</th>
                  <th>Expires</th>
                  <th>Days Left</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {deadlines.map((d, i) => (
                  <tr key={i} className={d.days_until_expiry <= 7 ? "urgent" : d.days_until_expiry <= 30 ? "warning" : ""}>
                    <td>{d.license_type}</td>
                    <td>{d.expires_on}</td>
                    <td>{d.days_until_expiry}</td>
                    <td>
                      <span className={`status-badge ${d.status.toLowerCase()}`}>
                        {d.status}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <div className="empty-state">No upcoming deadlines. Run a compliance check first.</div>
          )}
        </div>
      )}

      {/* Tasks tab */}
      {tab === "tasks" && (
        <div className="comp-panel">
          <h2>Remediation Tasks</h2>
          {tasks.length > 0 ? (
            <table className="comp-table">
              <thead>
                <tr>
                  <th>Title</th>
                  <th>Status</th>
                  <th>Due Date</th>
                  <th>Escalation</th>
                </tr>
              </thead>
              <tbody>
                {tasks.map((t) => (
                  <tr key={t.id}>
                    <td>{t.title}</td>
                    <td>
                      <span className={`status-badge ${t.status.toLowerCase()}`}>
                        {t.status}
                      </span>
                    </td>
                    <td>{t.due_date}</td>
                    <td>{t.escalation_level > 0 ? `Level ${t.escalation_level}` : "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <div className="empty-state">No tasks. Run a compliance check to generate tasks.</div>
          )}
        </div>
      )}

      {/* Approvals tab */}
      {tab === "approvals" && (
        <div className="comp-panel">
          <h2>Pending Approvals</h2>
          {approvals.length > 0 ? (
            <div>
              {approvals.map((a) => (
                <div key={a.id} className="approval-card">
                  <div className="approval-header">
                    <span className="approval-subject">{a.subject_type}: {a.subject_id}</span>
                    <span className="approval-decision">{a.decision}</span>
                  </div>
                  <div className="approval-body">
                    <textarea
                      placeholder="Rationale (optional)"
                      value={decisionRationale}
                      onChange={(e) => setDecisionRationale(e.target.value)}
                      rows={2}
                    />
                    <div className="approval-actions">
                      <button
                        className="btn-primary"
                        onClick={() => handleDecideApproval(a.id, "APPROVED")}
                        disabled={loading}
                      >
                        Approve
                      </button>
                      <button
                        className="btn-danger"
                        onClick={() => handleDecideApproval(a.id, "REJECTED")}
                        disabled={loading}
                      >
                        Reject
                      </button>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="empty-state">No pending approvals.</div>
          )}
        </div>
      )}

      {/* Regulations tab */}
      {tab === "regulations" && (
        <div className="comp-panel">
          <h2>Regulatory Sources</h2>
          <p className="hint">
            Sources are fetched on a schedule. Ingesting stores an immutable, versioned
            copy of the text and indexes it for citation-backed retrieval.
          </p>

          <div className="comp-section">
            <h3>Add a source</h3>
            <div className="comp-form-row">
              <select
                value={sourceForm.jurisdiction_code}
                onChange={(e) =>
                  setSourceForm({ ...sourceForm, jurisdiction_code: e.target.value })
                }
              >
                {jurisdictions.map((j) => (
                  <option key={j.id} value={j.code}>{j.code} — {j.name}</option>
                ))}
              </select>
              <input
                placeholder="Source name (e.g. CA DFPI MTA)"
                value={sourceForm.name}
                onChange={(e) => setSourceForm({ ...sourceForm, name: e.target.value })}
              />
              <input
                placeholder="https://regulator.example/statute"
                value={sourceForm.url}
                onChange={(e) => setSourceForm({ ...sourceForm, url: e.target.value })}
              />
              <button className="btn-primary" onClick={handleCreateSource} disabled={loading}>
                Add source
              </button>
            </div>
          </div>

          <div className="comp-section">
            <h3>Monitored sources ({sources.length})</h3>
            {sources.length > 0 ? (
              <table className="comp-table">
                <thead>
                  <tr><th>Name</th><th>URL</th><th>Last fetched</th><th>Status</th></tr>
                </thead>
                <tbody>
                  {sources.map((s) => (
                    <tr key={s.id}>
                      <td>{s.name}</td>
                      <td className="mono truncate">{s.url}</td>
                      <td>{s.last_fetched_at ? new Date(s.last_fetched_at).toLocaleString() : "never"}</td>
                      <td>{s.active ? "active" : "paused"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : (
              <div className="empty-state">No sources registered yet.</div>
            )}
          </div>

          <div className="comp-section">
            <h3>Ingest a regulation</h3>
            <div className="comp-form-grid">
              <input
                placeholder="Citation (e.g. Cal. Fin. Code § 2030)"
                value={ingestForm.citation}
                onChange={(e) => setIngestForm({ ...ingestForm, citation: e.target.value })}
              />
              <input
                placeholder="Title"
                value={ingestForm.title}
                onChange={(e) => setIngestForm({ ...ingestForm, title: e.target.value })}
              />
              <input
                placeholder="https://regulator.example/statute.pdf"
                value={ingestForm.source_url}
                onChange={(e) => setIngestForm({ ...ingestForm, source_url: e.target.value })}
              />
              <input
                placeholder="Publisher (optional)"
                value={ingestForm.publisher}
                onChange={(e) => setIngestForm({ ...ingestForm, publisher: e.target.value })}
              />
              <select
                value={ingestForm.jurisdiction_code}
                onChange={(e) =>
                  setIngestForm({ ...ingestForm, jurisdiction_code: e.target.value })
                }
              >
                {jurisdictions.map((j) => (
                  <option key={j.id} value={j.code}>{j.code} — {j.name}</option>
                ))}
              </select>
              <button className="btn-primary" onClick={handleIngest} disabled={loading}>
                {loading ? "Ingesting…" : "Ingest & index"}
              </button>
            </div>

            {ingestResult && (
              <div className="ingest-result">
                <div>
                  <strong>{ingestResult.changed ? "New version stored" : "No change detected"}</strong>
                  {ingestResult.regulation_version_id && (
                    <span className="mono"> — v{ingestResult.version_no}</span>
                  )}
                </div>
                <div className="hint">{ingestResult.change_summary}</div>
                <div>
                  Index: <span className={`status-badge ${ingestResult.index_status.toLowerCase()}`}>
                    {ingestResult.index_status}
                  </span>
                  {ingestResult.chunks_created > 0 && (
                    <span className="hint"> · {ingestResult.chunks_created} chunks</span>
                  )}
                </div>
              </div>
            )}
          </div>

          <div className="comp-section">
            <h3>Versions</h3>
            <div className="comp-form-row">
              <input
                placeholder="Citation"
                value={versionsCitation}
                onChange={(e) => setVersionsCitation(e.target.value)}
              />
              <button onClick={() => loadVersions(versionsCitation)} disabled={!apiKey}>
                Look up
              </button>
            </div>
            {versions.length > 0 ? (
              <table className="comp-table">
                <thead>
                  <tr>
                    <th>Ver</th><th>Title</th><th>SHA-256</th><th>Index</th><th>Effective</th>
                  </tr>
                </thead>
                <tbody>
                  {versions.map((v) => (
                    <tr key={v.id}>
                      <td>v{v.version_no}</td>
                      <td>{v.title}</td>
                      <td className="mono truncate">{v.content_sha256.slice(0, 12)}</td>
                      <td>
                        <span className={`status-badge ${v.index_status.toLowerCase()}`}>
                          {v.index_status}
                        </span>
                        {v.index_error && (
                          <div className="hint error-text">{v.index_error.slice(0, 120)}</div>
                        )}
                      </td>
                      <td>{v.effective_date ?? "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : (
              <div className="empty-state">No versions loaded.</div>
            )}
          </div>
        </div>
      )}

      {/* Review Queue tab */}
      {tab === "review" && (
        <div className="comp-panel">
          <h2>Obligation Review Queue</h2>
          <p className="hint">
            Proposed obligations start as <em>potentially relevant</em>. Only a human
            approval promotes one to <em>confirmed</em>; rejection records it as not applicable.
          </p>
          {reviewQueue.length > 0 ? (
            <div>
              {reviewQueue.map((o) => (
                <div key={o.id} className="approval-card">
                  <div className="approval-header">
                    <span className="approval-subject">{o.citation || "Uncited"}</span>
                    <span className="status-badge potentially_relevant">
                      {o.applicability.replace(/_/g, " ").toLowerCase()}
                    </span>
                  </div>
                  <div className="approval-body">
                    <p>{o.normalized_text}</p>
                    {o.citation_chunk_ids.length > 0 && (
                      <div className="hint mono">
                        cites {o.citation_chunk_ids.length} chunk
                        {o.citation_chunk_ids.length === 1 ? "" : "s"}
                      </div>
                    )}
                    <textarea
                      placeholder="Rationale (recorded with the decision)"
                      value={reviewRationale[o.id] ?? ""}
                      onChange={(e) =>
                        setReviewRationale({ ...reviewRationale, [o.id]: e.target.value })
                      }
                      rows={2}
                    />
                    <div className="approval-actions">
                      <button
                        className="btn-primary"
                        onClick={() => handleDecideObligation(o.id, "APPROVED")}
                        disabled={loading}
                      >
                        Confirm obligation
                      </button>
                      <button
                        className="btn-danger"
                        onClick={() => handleDecideObligation(o.id, "REJECTED")}
                        disabled={loading}
                      >
                        Not applicable
                      </button>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="empty-state">Nothing to review.</div>
          )}
        </div>
      )}

      {/* Audit tab */}
      {tab === "audit" && (
        <div className="comp-panel">
          <h2>Audit Chain Verification</h2>
          <button
            className="btn-primary"
            onClick={async () => {
              if (!apiKey) return;
              setLoading(true);
              try {
                const result = await verifyAudit(apiKey);
                setError(null);
                alert(`Audit: ${result.status} — ${result.events_checked} events checked`);
              } catch (e) {
                setError(e instanceof Error ? e.message : "audit verify failed");
              } finally {
                setLoading(false);
              }
            }}
            disabled={loading || !apiKey}
          >
            {loading ? "Verifying…" : "Verify Audit Chain"}
          </button>
        </div>
      )}
    </div>
  );
}