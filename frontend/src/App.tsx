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
  }, [messages, currentThreadId, loading]);

  let healthStatus = "checking…";
  if (healthErr) healthStatus = `unreachable (${healthErr})`;
  else if (health) {
    healthStatus = `${health.status} · db:${health.database} · inference:${health.inference_configured}`;
  }

  let healthDotClass = "health-dot";
  if (healthErr) healthDotClass += " error";
  else if (health?.status === "ok") healthDotClass += " ok";
  else if (health) healthDotClass += " degraded";

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
        <div className="app-logo">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M12 2L2 7l10 5 10-5-10-5z" />
            <path d="M2 17l10 5 10-5" />
            <path d="M2 12l10 5 10-5" />
          </svg>
          <span>agent-api</span>
        </div>
        <div className="app-header-right">
          <div className="health-chip" title={healthStatus}>
            <span className={healthDotClass} />
            {healthErr ? "unreachable" : health?.status === "ok" ? "healthy" : "degraded"}
          </div>
          <ApiKeyBar
            apiKey={apiKey}
            setApiKeyState={setApiKeyState}
            onValidate={loadTools}
          />
        </div>
      </header>

      <div className="app-body">
        <aside className="sidebar">
          <section className="sidebar-section">
            <div className="sidebar-header">
              <h2 className="sidebar-title">Conversations</h2>
            </div>
            <button
              className="btn-new-thread"
              onClick={startNewThread}
              disabled={!apiKey}
            >
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <line x1="12" y1="5" x2="12" y2="19" />
                <line x1="5" y1="12" x2="19" y2="12" />
              </svg>
              New conversation
            </button>
            <ThreadList
              threads={threads}
              currentThreadId={currentThreadId}
              onSelect={selectThread}
              onNew={startNewThread}
            />
          </section>
          <section className="sidebar-section grow">
            <div className="sidebar-header">
              <h2 className="sidebar-title">Tools</h2>
            </div>
            {toolsErr && <div className="error-banner">{toolsErr}</div>}
            <ToolsPanel tools={tools} />
          </section>
        </aside>

        <main className="main">
          <div className="toolbar">
            <div className="thread-id-display">{threadLabel}</div>
          </div>

          <div className="messages-wrap" ref={scrollRef}>
            {messages.length === 0 && !loading ? (
              <div className="empty-state-main">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
                </svg>
                <h3>Start a conversation</h3>
                <p>
                  {apiKey
                    ? "Ask anything — the agent can use tools like calculator, time, and knowledge base."
                    : "Enter your API key above to get started."}
                </p>
              </div>
            ) : (
              <>
                <MessageList messages={messages} currentThreadId={currentThreadId} />
                {loading && (
                  <div className="typing-indicator">
                    <span />
                    <span />
                    <span />
                  </div>
                )}
              </>
            )}
            {error && <div className="error-banner">{error}</div>}
          </div>

          <Composer onSend={handleSend} disabled={loading || !apiKey} />
        </main>
      </div>

      <footer className="app-footer">
        <span>{healthStatus}</span>
        {currentThreadId && (
          <>
            <span>·</span>
            <span>{messages.length} messages</span>
          </>
        )}
      </footer>
    </div>
  );
}
