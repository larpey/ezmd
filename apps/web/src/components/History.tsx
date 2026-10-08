import { useState } from "react";
import type { HistoryEntry } from "../lib/storage";

interface HistoryProps {
  entries: readonly HistoryEntry[];
  onOpen: (entry: HistoryEntry) => void;
  onClear: () => void;
}

export function History({ entries, onOpen, onClear }: HistoryProps) {
  const [now] = useState(() => Date.now());
  if (entries.length === 0) return null;
  return (
    <details className="history">
      <summary>History ({entries.length})</summary>
      <ul className="history-list">
        {entries.map((e) => {
          const expired = Date.parse(e.expires_at) < now;
          return (
            <li key={e.id} className="history-row">
              <button type="button" className="link" onClick={() => onOpen(e)} disabled={expired}>
                {e.title}
              </button>
              <span className="muted">
                {e.profile}
                {e.tokens != null ? `, ${e.tokens.toLocaleString()} tokens` : ""}
                {expired ? ", expired on the server" : ""}
              </span>
              {e.preview && <span className="history-preview">{e.preview}</span>}
            </li>
          );
        })}
      </ul>
      <button type="button" className="btn ghost" onClick={onClear}>
        Clear history
      </button>
    </details>
  );
}
