export function MessageList({
  messages,
  currentThreadId,
}: {
  messages: Array<{
    role: "user" | "assistant";
    content: string;
    tool_calls?: Array<{ name: string; arguments: unknown }> | null;
    created_at?: string | null;
  }>;
  currentThreadId: string | null;
}) {
  return (
    <div className="messages">
      {messages.length === 0 ? (
        <div className="empty">
          {currentThreadId ? "No messages yet." : "Select or start a conversation."}
        </div>
      ) : (
        messages.map((m, i) => (
          <div key={i} className={`msg ${m.role}`}>
            <div className="msg-role">{m.role === "user" ? "You" : "Assistant"}</div>
            <div className="msg-content">{m.content}</div>
            {m.tool_calls && m.tool_calls.length > 0 && (
              <div className="msg-tools">
                {m.tool_calls.map((tc, j) => (
                  <div key={j} className="tool-call">
                    <span className="tool-name">{tc.name}</span>
                    <span className="tool-args">
                      {JSON.stringify(tc.arguments)}
                    </span>
                  </div>
                ))}
              </div>
            )}
            {m.created_at && (
              <div className="msg-time">{new Date(m.created_at).toLocaleString()}</div>
            )}
          </div>
        ))
      )}
    </div>
  );
}
