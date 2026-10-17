import { useState, useEffect, useRef } from "react";
import {
  fetchHealth,
  fetchTools,
  fetchThread,
  chat,
  getApiKey,
  type Message,
  type ToolEntry,
  type Health,
} from "./api";
import { ApiKeyBar } from "./components/ApiKeyBar";
import { MessageList } from "./components/MessageList";
import { ToolsPanel } from "./components/ToolsPanel";
import { ThreadList } from "./components/ThreadList";
import { Composer } from "./components/Composer";

export default function App() {
  const [health, setHealth] = useState<Health | null>(null);
  const [healthErr, setHealthErr] = useState<string | null>(null);
  const [apiKey, setApiKeyState] = useState<string | null>(getApiKey());
  const [tools, setTools] = useState<ToolEntry[]>([]);
  const [toolsErr, setToolsErr] = useState<string | null>(null);
  const [threads, setThreads] = useState<Array<{ id: string }>>([]);
  const [currentThreadId, setCurrentThreadId] = useState<string | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    loadHealth();
    loadTools();
    const t = setInterval(loadHealth, 15000);
    return () => clearInterval(t);
  }, []);

  async function loadHealth() {
    try {
      const h = await fetchHealth();
      setHealth(h);
      setHealthErr(null);
    } catch (e) {
      setHealthErr(e instanceof Error ? e.message : "health check failed");
    }
  }

  async function loadTools() {
    if (!apiKey) {
      setTools([]);
      setToolsErr(null);
      return;
    }
    try {
      const t = await fetchTools(apiKey);
      setTools(t);
      setToolsErr(null);
    } catch (e) {
      setToolsErr(e instanceof Error ? e.message : "could not load tools");
      setTools([]);
    }
  }

  useEffect(() => {
    loadTools();
  }, [apiKey]);

  async function loadThread(id: string) {
    if (!apiKey) return;
    setLoading(true);
    setError(null);
    try {
      const msgs = await fetchThread(id, apiKey);
      setMessages(msgs);
      setCurrentThreadId(id);
    } catch (e) {
      setError(e instanceof Error ? e.message : "could not load thread");
    } finally {
      setLoading(false);
    }
  }

  function selectThread(id: string) {
    loadThread(id);
  }

  function startNewThread() {
    setCurrentThreadId(null);
    setMessages([]);
    setError(null);
  }

  async function handleSend(message: string) {
    if (!apiKey) {
      setError("Please set your API key first.");
      return;
    }
    setLoading(true);
    setError(null);
    const optimistic: Message = { role: "user", content: message };
    setMessages((prev) => [...prev, optimistic]);
    scrollToBottom();
    try {
      const res = await chat(message, currentThreadId ?? undefined, apiKey);
      const assistant: Message = {
        role: "assistant",
        content: res.response,
        tool_calls: res.tool_calls,
      };
      setMessages((prev) => [...prev, assistant]);
      if (res.thread_id && res.thread_id !== currentThreadId) {
        setCurrentThreadId(res.thread_id);
        setThreads((prev) =>
          prev.some((t) => t.id === res.thread_id) ? prev : [...prev, { id: res.thread_id }],
        );
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "send failed");
      setMessages((prev) =>
        prev.filter(
          (m) =>
            !(
              m.role === "user" &&
              m.content === message &&
              prev.indexOf(m) === prev.length - 1
            ),
        ),
      );
    } finally {
      setLoading(false);
      scrollToBottom();
    }
  }

  function scrollToBottom() {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }

  useEffect(() => {
    scrollToBottom();
  }, [messages, currentThreadId]);

  let healthText = "checking…";
  if (healthErr) healthText = `unreachable (${healthErr})`;
  else if (health) {
    healthText = `${health.status} · db:${health.database} · inference:${health.inference_configured}`;
  }

  let threadLabel: React.ReactNode;
  if (currentThreadId) {
    threadLabel = (
      <>
        <span className="tid-label">thread:</span>{" "}
        <span className="tid-value">{currentThreadId}</span>
      </>
    );
  } else {
    threadLabel = <span className="tid-none">no active thread</span>;
  }

  return (
    <div className="app">
      <header className="app-header">
        <div className="app-title">agent-api</div>
        <div className="health-chip" title={healthText}>
          {healthErr ? "● unreachable" : health?.status === "ok" ? "● ok" : "● degraded"}
        </div>
      </header>

      <div className="app-body">
        <aside className="sidebar">
          <section className="panel">
            <h2>Conversation</h2>
            <button
              className="btn btn-new"
              onClick={startNewThread}
              disabled={!apiKey}
            >
              + new conversation
            </button>
            <ThreadList
              threads={threads}
              currentThreadId={currentThreadId}
              onSelect={selectThread}
              onNew={startNewThread}
            />
          </section>
          <section className="panel">
            <h2>Tools</h2>
            {toolsErr && <div className="err">{toolsErr}</div>}
            <ToolsPanel tools={tools} />
          </section>
        </aside>

        <main className="main">
          <div className="toolbar">
            <ApiKeyBar
              apiKey={apiKey}
              setApiKeyState={setApiKeyState}
              onValidate={loadTools}
            />
            <div className="thread-id">{threadLabel}</div>
          </div>

          <div className="messages-wrap" ref={scrollRef}>
            <MessageList messages={messages} currentThreadId={currentThreadId} />
            {error && <div className="err">{error}</div>}
          </div>

          <Composer onSend={handleSend} disabled={loading || !apiKey} />
        </main>
      </div>

      <footer className="app-footer">{healthText}</footer>
    </div>
  );
}
