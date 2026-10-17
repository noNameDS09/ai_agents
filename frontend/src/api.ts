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

export type { Message, ToolEntry, Health, ChatResponse };
