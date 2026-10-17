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
        API key set ({mask(apiKey ?? "")}){" "}
        <button
          onClick={() => {
            clearApiKey();
            setApiKeyState(null);
            setShow(true);
          }}
          className="btn-text"
        >
          change
        </button>
      </div>
    );
  }

  return (
    <form onSubmit={handleSave} className="api-key-form">
      <label>
        X-API-Key{" "}
        <input
          type="password"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="enter backend API key"
          autoComplete="off"
        />
      </label>
      <button type="submit" className="btn-save">
        save
      </button>
    </form>
  );
}

function mask(k: string): string {
  if (!k) return "";
  return k.slice(0, 4) + "•".repeat(Math.max(0, k.length - 8)) + k.slice(-4);
}
