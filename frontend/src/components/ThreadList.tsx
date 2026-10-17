export function ThreadList({
  threads,
  currentThreadId,
  onSelect,
}: {
  threads: Array<{ id: string }>;
  currentThreadId: string | null;
  onSelect: (id: string) => void;
}) {
  if (threads.length === 0) {
    return <div className="empty-state">No conversations yet.</div>;
  }

  return (
    <ul className="thread-list">
      {threads.map((t) => (
        <li
          key={t.id}
          className={`thread-item ${t.id === currentThreadId ? "active" : ""}`}
          onClick={() => onSelect(t.id)}
          title={t.id}
        >
          {t.id}
        </li>
      ))}
    </ul>
  );
}
