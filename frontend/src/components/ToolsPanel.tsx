export function ToolsPanel({ tools }: { tools: Array<{ name: string; description: string; parameters: Record<string, unknown> }> }) {
  return (
    <div className="panel">
      <h2>Tools</h2>
      <ul>
        {tools.map((t) => {
          const params = t.parameters && t.parameters.properties
            ? Object.keys(t.parameters.properties as Record<string, unknown>)
            : [];
          return (
            <li key={t.name}>
              <strong>{t.name}</strong>{" "}
              <span className="desc">{t.description}</span>
              {params.length > 0 && (
                <div className="args">args: {params.join(", ")}</div>
              )}
            </li>
          );
        })}
      </ul>
    </div>
  );
}
