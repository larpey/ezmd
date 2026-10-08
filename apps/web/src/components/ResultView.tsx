import type { IntomdWarning, Profile, ResultFormat, Sidecar } from "@intomd/sdk";
import { useMemo, useState } from "react";
import { renderMarkdown } from "../lib/markdown";
import { Tabs } from "./Tabs";
import { WarningsPanel } from "./WarningsPanel";

export interface ResultViewProps {
  markdown: string;
  sidecar: Sidecar | null;
  warnings: readonly IntomdWarning[];
  tokens?: number;
  /** Tokenizer behind `tokens` (e.g. o200k_base); shown as the badge tooltip. */
  tokenizer?: string;
  profile: Profile;
  profiles: readonly Profile[];
  formats: readonly ResultFormat[];
  busy?: boolean;
  onProfileChange: (p: Profile) => void;
  onDownload: (format: ResultFormat) => void;
}

// Scrollable <pre> blocks must be reachable by keyboard (axe scrollable-region-focusable): a named,
// focusable region lets keyboard users scroll a long or unwrapped line with the arrow keys.
const SCROLL_REGION = { tabIndex: 0, role: "region" } as const;

const DOWNLOAD_LABELS: Record<ResultFormat, string> = { md: ".md", txt: ".txt", json: ".json", zip: ".zip" };

async function copyText(text: string): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    return false;
  }
}

export function ResultView(props: ResultViewProps) {
  const { markdown, sidecar, warnings, tokens, tokenizer, profile, profiles, formats, busy, onProfileChange, onDownload } = props;
  const [tab, setTab] = useState("rendered");
  const [copied, setCopied] = useState<"idle" | "ok" | "fail">("idle");
  const [wrap, setWrap] = useState(true);
  const html = useMemo(() => renderMarkdown(markdown), [markdown]);

  const onCopy = async (): Promise<void> => {
    // Copies the raw Markdown, frontmatter included.
    setCopied((await copyText(markdown)) ? "ok" : "fail");
    setTimeout(() => setCopied("idle"), 1500);
  };

  const tabs = [
    // Sanitized by DOMPurify in renderMarkdown; raw HTML in the source is escaped, never rendered.
    { id: "rendered", label: "Rendered", content: <div className="markdown-body" data-testid="result-rendered" dangerouslySetInnerHTML={{ __html: html }} /> },
    {
      id: "raw",
      label: "Raw",
      content: (
        <>
          <label className="inline-check">
            <input type="checkbox" data-testid="result-wrap" checked={wrap} onChange={(e) => setWrap(e.target.checked)} /> Soft wrap
          </label>
          <pre className={wrap ? "raw wrap" : "raw"} data-testid="result-raw" {...SCROLL_REGION} aria-label="Raw Markdown">
            {markdown}
          </pre>
        </>
      ),
    },
    {
      id: "sidecar",
      label: "Sidecar JSON",
      content: sidecar ? (
          <pre className="raw wrap" {...SCROLL_REGION} aria-label="Sidecar JSON">
            {JSON.stringify(sidecar, null, 2)}
          </pre>
        ) : <p className="muted">No sidecar for this profile.</p>,
    },
    { id: "warnings", label: `Warnings (${warnings.length})`, content: <WarningsPanel warnings={warnings} expanded /> },
  ];

  return (
    <section className="result" aria-label="Result" data-testid="result" aria-busy={busy || undefined}>
      <WarningsPanel warnings={warnings} />
      <div className="result-actions">
        <button type="button" className="btn" onClick={() => void onCopy()} data-testid="result-copy">
          {copied === "ok" ? "Copied" : copied === "fail" ? "Copy failed" : "Copy Markdown"}
        </button>
        <label className="field-inline">
          <span>Profile</span>
          <select data-testid="result-profile" value={profile} onChange={(e) => onProfileChange(e.target.value as Profile)} disabled={busy}>
            {profiles.map((p) => (
              <option key={p} value={p}>
                {p}
              </option>
            ))}
          </select>
        </label>
        <span className="download-group" role="group" aria-label="Download">
          {formats.map((f) => (
            <button key={f} type="button" className="btn secondary" onClick={() => onDownload(f)} aria-label={`Download ${DOWNLOAD_LABELS[f]}`} data-testid={`download-${f}`}>
              {DOWNLOAD_LABELS[f]}
            </button>
          ))}
        </span>
        {tokens != null && (
          <span className="badge" title={tokenizer ? `${tokenizer} count` : "Token count"} data-testid="result-tokens">
            {tokens.toLocaleString()} tokens
          </span>
        )}
      </div>
      <Tabs tabs={tabs} active={tab} onChange={setTab} label="Result views" />
    </section>
  );
}
