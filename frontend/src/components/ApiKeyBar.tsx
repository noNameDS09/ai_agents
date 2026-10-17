import { useState, useEffect } from "react";
import { setApiKey, clearApiKey } from "../api";

export function ApiKeyBar({
  apiKey,
  setApiKeyState,
  onValidate,
}: {
  apiKey: string | null;
  setApiKeyState: (k: string | null) => void;
  onValidate: () => Promise<void>;
}) {
  const [input, setInput] = useState(apiKey ?? "");
  const [show, setShow] = useState(!Boolean(apiKey));

  useEffect(() => {
    setInput(apiKey ?? "");
  }, [apiKey]);

  const handleSave = (e: React.FormEvent) => {
    e.preventDefault();
    const trimmed = input.trim();
    if (!trimmed) return;
    setApiKey(trimmed);
    setApiKeyState(trimmed);
    setShow(false);
    onValidate();
  };

  if (!show) {
    return (
      <div className="api-key-set">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <rect x="3" y="11" width="18" height="11" rx="2" ry="2" />
          <path d="M7 11V7a5 5 0 0 1 10 0v4" />
        </svg>
        Key set ({mask(apiKey ?? "")})
        <button
          className="btn-change"
          onClick={() => {
            clearApiKey();
            setApiKeyState(null);
            setShow(true);
          }}
        >
          change
        </button>
      </div>
    );
  }

  return (
    <form onSubmit={handleSave} className="api-key-form">
      <label>
        X-API-Key
        <input
          type="password"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="enter backend API key"
          autoComplete="off"
          autoFocus
        />
      </label>
      <button type="submit" className="btn-primary">
        Save
      </button>
    </form>
  );
}

function mask(k: string): string {
  if (!k) return "";
  if (k.length <= 8) return "•".repeat(k.length);
  return k.slice(0, 4) + "•".repeat(Math.max(0, k.length - 8)) + k.slice(-4);
}
