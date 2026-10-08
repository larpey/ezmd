import { useState } from "react";
import { isExpired, type HistoryEntry } from "../lib/storage";

interface HistoryProps {
  entries: readonly HistoryEntry[];
  onOpen: (entry: HistoryEntry) => void;
  onOpenLocal: (entry: HistoryEntry) => void;
  onToggleKeep: (entry: HistoryEntry, keep: boolean) => void;
  onClear: () => void;
}

/** Last 50 jobs from localStorage; rows re-open live results or show the kept local copy once expired. */
export function History({ entries, onOpen, onOpenLocal, onToggleKeep, onClear }: HistoryProps) {
  const [now] = useState(() => Date.now());
  if (entries.length === 0) return null;
  return (
    <details className="history" data-testid="history">
      <summary>History ({entries.length})</summary>
      <ul className="history-list">
        {entries.map((e) => {
          const expired = isExpired(e, now);
          return (
            <li key={e.id} className="history-row" data-testid="history-row" data-job-id={e.id}>
              <div className="history-main">
                {expired ? (
                  <span className="history-title">{e.title}</span>
                ) : (
                  <button type="button" className="link" onClick={() => onOpen(e)} data-testid="history-open">
                    {e.title}
                  </button>
                )}
                <span className="muted">
                  {e.profile}
                  {e.tokens != null ? `, ${e.tokens.toLocaleString()} tokens` : ""}
                </span>
                {expired && <span className="muted"> Expired on the server.</span>}
                {expired && e.keep && (
                  <button type="button" className="btn ghost" onClick={() => onOpenLocal(e)} data-testid="history-open-local">
                    Open local copy
                  </button>
                )}
              </div>
              {e.preview && <span className="history-preview">{e.preview}</span>}
              <label className="inline-check">
                <input
                  type="checkbox"
                  checked={Boolean(e.keep)}
                  disabled={expired && !e.keep}
                  onChange={(ev) => onToggleKeep(e, ev.target.checked)}
                  data-testid="history-keep"
                />{" "}
                Keep result on this device
              </label>
            </li>
          );
        })}
      </ul>
      <button type="button" className="btn ghost" onClick={onClear} data-testid="history-clear">
        Clear history
      </button>
    </details>
  );
}
