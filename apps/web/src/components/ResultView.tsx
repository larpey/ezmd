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
  profile: Profile;
  profiles: readonly Profile[];
  formats: readonly ResultFormat[];
  busy?: boolean;
  onProfileChange: (p: Profile) => void;
  onDownload: (format: ResultFormat) => void;
}

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
  const { markdown, sidecar, warnings, tokens, profile, profiles, formats, busy, onProfileChange, onDownload } = props;
  const [tab, setTab] = useState("rendered");
  const [copied, setCopied] = useState<"idle" | "ok" | "fail">("idle");
  const [wrap, setWrap] = useState(true);
  const html = useMemo(() => renderMarkdown(markdown), [markdown]);

  const onCopy = async (): Promise<void> => {
    setCopied((await copyText(markdown)) ? "ok" : "fail");
    setTimeout(() => setCopied("idle"), 1500);
  };

  const tabs = [
    // Sanitized by DOMPurify in renderMarkdown; raw HTML in the source is escaped, never rendered.
    { id: "rendered", label: "Rendered", content: <div className="markdown-body" dangerouslySetInnerHTML={{ __html: html }} /> },
    {
      id: "raw",
      label: "Raw",
      content: (
        <>
          <label className="inline-check">
            <input type="checkbox" checked={wrap} onChange={(e) => setWrap(e.target.checked)} /> Soft wrap
          </label>
          <pre className={wrap ? "raw wrap" : "raw"}>{markdown}</pre>
        </>
      ),
    },
    {
      id: "sidecar",
      label: "Sidecar JSON",
      content: sidecar ? <pre className="raw wrap">{JSON.stringify(sidecar, null, 2)}</pre> : <p className="muted">No sidecar for this profile.</p>,
    },
    { id: "warnings", label: `Warnings (${warnings.length})`, content: <WarningsPanel warnings={warnings} expanded /> },
  ];

  return (
    <section className="result" aria-label="Result" aria-busy={busy || undefined}>
      <WarningsPanel warnings={warnings} />
      <div className="result-actions">
        <button type="button" className="btn" onClick={() => void onCopy()}>
          {copied === "ok" ? "Copied" : copied === "fail" ? "Copy failed" : "Copy Markdown"}
        </button>
        <label className="field-inline">
          <span>Profile</span>
          <select value={profile} onChange={(e) => onProfileChange(e.target.value as Profile)} disabled={busy}>
            {profiles.map((p) => (
              <option key={p} value={p}>
                {p}
              </option>
            ))}
          </select>
        </label>
        <span className="download-group" role="group" aria-label="Download">
          {formats.map((f) => (
            <button key={f} type="button" className="btn secondary" onClick={() => onDownload(f)} aria-label={`Download ${DOWNLOAD_LABELS[f]}`}>
              {DOWNLOAD_LABELS[f]}
            </button>
          ))}
        </span>
        {tokens != null && (
          <span className="badge" title="cl100k estimate">
            {tokens.toLocaleString()} tokens
          </span>
        )}
      </div>
      <Tabs tabs={tabs} active={tab} onChange={setTab} label="Result views" />
    </section>
  );
}
