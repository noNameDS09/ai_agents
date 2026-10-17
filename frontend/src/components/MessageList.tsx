import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

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
    <>
      {messages.map((m, i) => (
        <div key={i} className={`msg ${m.role}`}>
          <div className="msg-role">
            {m.role === "user" ? "You" : "Assistant"}
          </div>
          <div className="msg-content">
            {m.role === "assistant" ? (
              <ReactMarkdown remarkPlugins={[remarkGfm]}>
                {m.content}
              </ReactMarkdown>
            ) : (
              <span style={{ whiteSpace: "pre-wrap" }}>{m.content}</span>
            )}
          </div>
          {m.tool_calls && m.tool_calls.length > 0 && (
            <div className="msg-tools">
              {m.tool_calls.map((tc, j) => (
                <span key={j} className="tool-call">
                  <span className="tool-name">{tc.name}</span>
                  <span className="tool-args">
                    {typeof tc.arguments === "object"
                      ? JSON.stringify(tc.arguments)
                      : String(tc.arguments)}
                  </span>
                </span>
              ))}
            </div>
          )}
          {m.created_at && (
            <div className="msg-time">
              {new Date(m.created_at).toLocaleTimeString([], {
                hour: "2-digit",
                minute: "2-digit",
              })}
            </div>
          )}
        </div>
      ))}
    </>
  );
}
