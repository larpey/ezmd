import type { IntomdWarning } from "@intomd/sdk";
import { suggestedAction, warningKind } from "../lib/warnings";

interface WarningsPanelProps {
  warnings: readonly IntomdWarning[];
  /** Render expanded without the summary toggle (used inside the Warnings tab). */
  expanded?: boolean;
}

function WarningList({ warnings }: { warnings: readonly IntomdWarning[] }) {
  return (
    <ul className="warnings-list">
      {warnings.map((w, i) => (
        <li key={`${warningKind(w)}-${i}`} className={`warning sev-${w.severity ?? "warning"}`}>
          <div className="warning-head">
            <code className="warning-code">{warningKind(w)}</code>
            <span className="warning-sev">{w.severity ?? "warning"}</span>
            {w.page != null && <span className="warning-meta">page {w.page}</span>}
            {w.count != null && <span className="warning-meta">x{w.count}</span>}
          </div>
          <p className="warning-message">{w.message}</p>
          <p className="warning-action">{suggestedAction(w)}</p>
        </li>
      ))}
    </ul>
  );
}

/** Every warning is shown verbatim with a suggested action; nothing is hidden (spec part4 4.0 rule 2). */
export function WarningsPanel({ warnings, expanded = false }: WarningsPanelProps) {
  if (warnings.length === 0) {
    return expanded ? <p className="muted">No warnings. Nothing was dropped.</p> : null;
  }
  const hasError = warnings.some((w) => w.severity === "error");
  const label = `${warnings.length} warning${warnings.length === 1 ? "" : "s"}`;
  if (expanded) return <WarningList warnings={warnings} />;
  return (
    <details className={`warnings-panel${hasError ? " has-error" : ""}`} open={hasError} role={hasError ? "alert" : undefined}>
      <summary>{label}</summary>
      <WarningList warnings={warnings} />
    </details>
  );
}
