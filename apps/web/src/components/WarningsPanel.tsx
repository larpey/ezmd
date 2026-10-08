import type { EzmdWarning } from "@ezmd/sdk";
import { useWarningRegistry } from "../lib/warning-context";
import { EXTENSION_DOCS_URL, canonicalCode, suggestedAction, warningKind, warningSeverity, type WarningRegistry } from "../lib/warnings";

interface WarningsPanelProps {
  warnings: readonly EzmdWarning[];
  /** Render expanded without the summary toggle (used inside the Warnings tab). */
  expanded?: boolean;
}

function WarningItem({ w, reg }: { w: EzmdWarning; reg: WarningRegistry }) {
  const severity = warningSeverity(w, reg);
  const code = canonicalCode(w, reg);
  return (
    <li className={`warning sev-${severity}`} data-testid="warning-item" data-code={code}>
      <div className="warning-head">
        <code className="warning-code">{warningKind(w)}</code>
        <span className="warning-sev">{severity}</span>
        {w.page != null && <span className="warning-meta">page {w.page}</span>}
        {w.count != null && <span className="warning-meta">x{w.count}</span>}
      </div>
      <p className="warning-message">{w.message}</p>
      <p className="warning-action" data-testid="warning-action">
        {suggestedAction(w, reg)}
        {code === "fetch_blocked_by_platform" && (
          <>
            {" "}
            <a href={EXTENSION_DOCS_URL}>About the browser extension</a>
          </>
        )}
      </p>
    </li>
  );
}

function WarningList({ warnings, reg }: { warnings: readonly EzmdWarning[]; reg: WarningRegistry }) {
  return (
    <ul className="warnings-list">
      {warnings.map((w, i) => (
        <WarningItem key={`${warningKind(w)}-${i}`} w={w} reg={reg} />
      ))}
    </ul>
  );
}

/** Every warning is shown verbatim with a suggested action; nothing is hidden (spec part4 4.0 rule 2). */
export function WarningsPanel({ warnings, expanded = false }: WarningsPanelProps) {
  const reg = useWarningRegistry();
  if (warnings.length === 0) {
    return expanded ? <p className="muted">No warnings. Nothing was dropped.</p> : null;
  }
  const hasError = warnings.some((w) => warningSeverity(w, reg) === "error");
  const label = `${warnings.length} warning${warnings.length === 1 ? "" : "s"}`;
  if (expanded) return <WarningList warnings={warnings} reg={reg} />;
  return (
    <details className={`warnings-panel${hasError ? " has-error" : ""}`} open={hasError} role={hasError ? "alert" : undefined} data-testid="warnings-panel">
      <summary data-testid="warnings-summary">{label}</summary>
      <WarningList warnings={warnings} reg={reg} />
    </details>
  );
}
