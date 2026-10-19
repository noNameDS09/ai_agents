/** Same-origin API client for the agent backend. */

const BASE = "";

type ChatResponse = {
  thread_id: string;
  response: string;
  tool_calls: Array<{ name: string; arguments: unknown }>;
  steps: number;
};

type ToolEntry = {
  name: string;
  description: string;
  parameters: Record<string, unknown>;
};

type Health = {
  status: string;
  database: string;
  inference_configured: boolean;
};

type Message = {
  role: "user" | "assistant";
  content: string;
  tool_calls?: Array<{ name: string; arguments: unknown }> | null;
  created_at?: string | null;
};

export async function fetchHealth(): Promise<Health> {
  const res = await fetch(`${BASE}/health`);
  if (!res.ok) throw new Error(`health ${res.status}`);
  return res.json();
}

export async function fetchTools(apiKey?: string): Promise<ToolEntry[]> {
  const h: Record<string, string> = { "Content-Type": "application/json" };
  if (apiKey) h["X-API-Key"] = apiKey;
  const res = await fetch(`${BASE}/v1/tools`, { headers: h });
  if (res.status === 401) throw new Error("unauthorized");
  if (!res.ok) throw new Error(`tools ${res.status}`);
  const json = await res.json();
  return json.tools ?? [];
}

export async function fetchThread(threadId: string, apiKey?: string): Promise<Message[]> {
  const h: Record<string, string> = { "Content-Type": "application/json" };
  if (apiKey) h["X-API-Key"] = apiKey;
  const res = await fetch(`${BASE}/v1/threads/${encodeURIComponent(threadId)}`, {
    headers: h,
  });
  if (res.status === 404) return [];
  if (!res.ok) throw new Error(`thread ${res.status}`);
  const json = await res.json();
  return json.messages ?? [];
}

export async function chat(
  message: string,
  threadId?: string,
  apiKey?: string,
): Promise<ChatResponse> {
  const h: Record<string, string> = { "Content-Type": "application/json" };
  if (apiKey) h["X-API-Key"] = apiKey;
  const body: Record<string, unknown> = { message };
  if (threadId) body.thread_id = threadId;
  const res = await fetch(`${BASE}/v1/chat`, {
    method: "POST",
    headers: h,
    body: JSON.stringify(body),
  });
  const text = await res.text();
  let json: unknown = null;
  try {
    json = JSON.parse(text);
  } catch {
    // ignore
  }
  if (!res.ok) {
    const detail = (json as { detail?: string } | null)?.detail ?? `error ${res.status}`;
    throw new Error(detail);
  }
  return json as ChatResponse;
}

export function getApiKey(): string | null {
  return localStorage.getItem("agent_api_key");
}

export function setApiKey(key: string): void {
  localStorage.setItem("agent_api_key", key);
}

export function clearApiKey(): void {
  localStorage.removeItem("agent_api_key");
}

/* ---------- Compliance API ---------- */

export type Org = { id: string; legal_name: string; industry?: string | null };
export type Entity = { id: string; name: string; state?: string | null; status: string };
export type Jurisdiction = { id: string; code: string; name: string; country: string; regime: string };
export type License = {
  id: string;
  license_type: string;
  authority: string;
  expires_on: string | null;
  status: string;
  renewal_window_days: number;
};
export type Deadline = {
  license_id: string;
  license_type: string;
  expires_on: string;
  days_until_expiry: number;
  status: string;
};
export type Task = {
  id: string;
  title: string;
  description?: string | null;
  status: string;
  due_date: string;
  escalation_level: number;
  owner_user_id?: string | null;
};
export type Approval = {
  id: string;
  subject_type: string;
  subject_id: string;
  decision: string;
  reviewer_user_id: string;
  rationale?: string | null;
  decided_at: string;
};
export type WorkflowResult = {
  thread_id: string;
  status: string;
  agents_invoked: string[];
  tasks_created: number;
  overdue_count: number;
  escalated_count: number;
  upcoming_deadlines: Array<{
    license_id: string;
    license_type: string;
    expires_on: string;
    deadline: string;
    days_until_deadline: number;
    escalation_level: number;
    status: string;
  }>;
};

export async function complianceFetch(
  path: string,
  options?: RequestInit,
  apiKey?: string,
): Promise<Response> {
  const key = apiKey ?? getApiKey();
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (key) headers["X-API-Key"] = key;
  return fetch(`/v1/compliance${path}`, {
    ...options,
    headers: { ...headers, ...(options?.headers as Record<string, string> ?? {}) },
  });
}

export async function listJurisdictions(apiKey?: string): Promise<Jurisdiction[]> {
  const res = await complianceFetch("/jurisdictions", undefined, apiKey);
  if (!res.ok) throw new Error(`jurisdictions ${res.status}`);
  return res.json();
}

export async function createOrg(legalName: string, industry: string, apiKey?: string): Promise<Org> {
  const res = await complianceFetch("/organizations", {
    method: "POST",
    body: JSON.stringify({ legal_name: legalName, industry }),
  }, apiKey);
  if (!res.ok) throw new Error(`create org ${res.status}`);
  return res.json();
}

export async function listEntities(orgId: string, apiKey?: string): Promise<Entity[]> {
  const res = await complianceFetch(`/organizations/${orgId}/entities`, undefined, apiKey);
  if (!res.ok) throw new Error(`entities ${res.status}`);
  return res.json();
}

export async function createEntity(
  orgId: string,
  name: string,
  state?: string,
  apiKey?: string,
): Promise<Entity> {
  const res = await complianceFetch(`/organizations/${orgId}/entities`, {
    method: "POST",
    body: JSON.stringify({ name, state }),
  }, apiKey);
  if (!res.ok) throw new Error(`create entity ${res.status}`);
  return res.json();
}

export async function listLicenses(entityId: string, apiKey?: string): Promise<License[]> {
  const res = await complianceFetch(`/entities/${entityId}/licenses`, undefined, apiKey);
  if (!res.ok) throw new Error(`licenses ${res.status}`);
  return res.json();
}

export async function createLicense(
  entityId: string,
  data: { license_type: string; authority: string; jurisdiction_id: string; expires_on?: string },
  apiKey?: string,
): Promise<License> {
  const res = await complianceFetch(`/entities/${entityId}/licenses`, {
    method: "POST",
    body: JSON.stringify(data),
  }, apiKey);
  if (!res.ok) throw new Error(`create license ${res.status}`);
  return res.json();
}

export async function listDeadlines(daysAhead = 90, apiKey?: string): Promise<Deadline[]> {
  const res = await complianceFetch(`/licenses/deadlines?days_ahead=${daysAhead}`, undefined, apiKey);
  if (!res.ok) throw new Error(`deadlines ${res.status}`);
  return res.json();
}

export async function runWorkflow(
  orgId: string,
  entityId?: string,
  apiKey?: string,
): Promise<WorkflowResult> {
  const res = await complianceFetch("/workflows/run", {
    method: "POST",
    body: JSON.stringify({
      workflow_type: "license_deadline_check",
      org_id: orgId,
      entity_id: entityId,
    }),
  }, apiKey);
  if (!res.ok) throw new Error(`workflow ${res.status}`);
  return res.json();
}

export async function listTasks(apiKey?: string): Promise<Task[]> {
  const res = await complianceFetch("/tasks", undefined, apiKey);
  if (!res.ok) throw new Error(`tasks ${res.status}`);
  return res.json();
}

export async function listApprovals(apiKey?: string): Promise<Approval[]> {
  const res = await complianceFetch("/approvals/pending", undefined, apiKey);
  if (!res.ok) throw new Error(`approvals ${res.status}`);
  return res.json();
}

export async function decideApproval(
  approvalId: string,
  decision: "APPROVED" | "REJECTED",
  rationale: string,
  apiKey?: string,
): Promise<Approval> {
  const res = await complianceFetch(`/approvals/${approvalId}/decide`, {
    method: "POST",
    body: JSON.stringify({ decision, rationale }),
  }, apiKey);
  if (!res.ok) throw new Error(`decide ${res.status}`);
  return res.json();
}

export async function verifyAudit(apiKey?: string): Promise<{ status: string; events_checked: number; first_break: unknown }> {
  const res = await complianceFetch("/audit/verify", undefined, apiKey);
  if (!res.ok) throw new Error(`audit verify ${res.status}`);
  return res.json();
}

export type { Message, ToolEntry, Health, ChatResponse };
