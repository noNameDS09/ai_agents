export function ToolsPanel({
  tools,
}: {
  tools: Array<{
    name: string;
    description: string;
    parameters: Record<string, unknown>;
  }>;
}) {
  if (tools.length === 0) {
    return <div className="empty-state">No tools loaded.</div>;
  }

  return (
    <div>
      {tools.map((t) => {
        const params =
          t.parameters && t.parameters.properties
            ? Object.keys(t.parameters.properties as Record<string, unknown>)
            : [];
        return (
          <div key={t.name} className="tool-card">
            <div className="tool-name">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z" />
              </svg>
              {t.name}
            </div>
            <div className="tool-desc">{t.description}</div>
            {params.length > 0 && (
              <div className="tool-args">args: {params.join(", ")}</div>
            )}
          </div>
        );
      })}
    </div>
  );
}
