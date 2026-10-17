import { useCallback } from "react";

export function ThreadList({
  threads,
  currentThreadId,
  onSelect,
  onNew,
}: {
  threads: Array<{ id: string }>;
  currentThreadId: string | null;
  onSelect: (id: string) => void;
  onNew: () => void;
}) {
  const handleNew = useCallback(() => {
    onNew();
  }, [onNew]);

  return (
    <div className="panel">
      <div className="panel-header">
        <h2>Conversations</h2>
        <button className="btn-new" onClick={handleNew}>
          + new
        </button>
      </div>
      <ul>
        {threads.length === 0 && (
          <li className="empty">No conversations yet.</li>
        )}
        {threads.map((t) => (
          <li
            key={t.id}
            className={`thread ${t.id === currentThreadId ? "active" : ""}`}
            onClick={() => onSelect(t.id)}
          >
            {t.id}
          </li>
        ))}
      </ul>
    </div>
  );
}
