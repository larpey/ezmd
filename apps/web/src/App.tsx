import type { Capabilities, CreatedJob, Profile, ResultFormat } from "@intomd/sdk";
import { useCallback, useEffect, useRef, useState } from "react";
import { History } from "./components/History";
import { InputPanel, type SubmitPayload } from "./components/InputPanel";
import { JobCard, type JobSummary } from "./components/JobCard";
import { SupportedInputs } from "./components/SupportedInputs";
import { ThemeToggle } from "./components/ThemeToggle";
import { Turnstile, type TurnstileHandle } from "./components/Turnstile";
import { createClient, errorMessage } from "./lib/api";
import { HISTORY_KEY, loadHistory, removeKey, upsertHistory, writeJson, type HistoryEntry } from "./lib/storage";

const DEFAULT_PROFILES: Profile[] = ["full", "compact", "rag", "agent"];
const DEFAULT_FORMATS: ResultFormat[] = ["md", "txt", "json"];
const DOWNLOADABLE: ResultFormat[] = ["md", "txt", "json", "zip"];

// Plain holder (not a React ref): the SDK reads it lazily when a URL is submitted.
const turnstile: { current: TurnstileHandle | null } = { current: null };
const client = createClient(async () => turnstile.current?.take());

export function App() {
  const fileInput = useRef<HTMLInputElement>(null);
  const [caps, setCaps] = useState<Capabilities | null>(null);
  const [capsError, setCapsError] = useState<string | null>(null);
  const [jobs, setJobs] = useState<JobSummary[]>([]);
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [history, setHistory] = useState<HistoryEntry[]>(() => loadHistory());

  useEffect(() => {
    const ctrl = new AbortController();
    client.getCapabilities(ctrl.signal).then(setCaps, (err: unknown) => {
      if ((err as Error).name !== "AbortError") setCapsError(errorMessage(err));
    });
    return () => ctrl.abort();
  }, []);

  useEffect(() => writeJson(HISTORY_KEY, history), [history]);

  const profiles = caps?.profiles?.length ? caps.profiles : DEFAULT_PROFILES;
  const formats = (caps?.formats?.length ? caps.formats : DEFAULT_FORMATS).filter((f) => DOWNLOADABLE.includes(f));

  const track = (created: CreatedJob, title: string, kind: HistoryEntry["source_kind"]): void => {
    setJobs((list) => [{ id: created.id, title, profile: (created.profile as Profile) ?? "compact" }, ...list.filter((j) => j.id !== created.id)]);
    setHistory((h) => upsertHistory(h, { id: created.id, title, source_kind: kind, created_at: created.created_at, expires_at: created.expires_at, profile: String(created.profile) }));
  };

  const onSubmit = async ({ files, text, profile, options }: SubmitPayload): Promise<void> => {
    setSubmitting(true);
    setSubmitError(null);
    const errors: string[] = [];
    // One job per source.
    for (const file of files) {
      try {
        track(await client.convert({ file, filename: file.name, profile, options }), file.name, "file");
      } catch (err) {
        errors.push(`${file.name}: ${errorMessage(err)}`);
      }
    }
    try {
      if (text.kind === "url") track(await client.convert({ url: text.url, profile, options }), text.url, "url");
      if (text.kind === "text") track(await client.convert({ text: text.text, profile, options }), `Pasted text (${text.words} words)`, "text");
    } catch (err) {
      errors.push(errorMessage(err));
    }
    setSubmitError(errors.length ? errors.join(" ") : null);
    setSubmitting(false);
  };

  const onResult = useCallback((id: string, info: { tokens?: number; preview: string; title?: string }) => {
    setHistory((h) => {
      const prev = h.find((e) => e.id === id);
      return prev ? upsertHistory(h, { ...prev, tokens: info.tokens, preview: info.preview, title: info.title ?? prev.title }) : h;
    });
  }, []);

  const onRemove = useCallback((id: string) => setJobs((list) => list.filter((j) => j.id !== id)), []);
  const onUploadInstead = useCallback(() => fileInput.current?.click(), []);

  const reopen = (e: HistoryEntry): void => {
    setJobs((list) => [{ id: e.id, title: e.title, profile: e.profile as Profile }, ...list.filter((j) => j.id !== e.id)]);
  };

  const clearHistory = (): void => {
    removeKey(HISTORY_KEY);
    setHistory([]);
  };

  const retention = caps?.limits.retention_hours ?? 24;

  return (
    <div className="app">
      <header className="top">
        <h1 className="brand">intomd</h1>
        <nav className="top-links" aria-label="Site">
          <a href="/docs/self-host">Self-host</a>
          <ThemeToggle />
        </nav>
      </header>
      <main id="main">
        <p className="explainer">Paste a link, drop a file, or paste text. Get clean Markdown with nothing silently dropped.</p>
        {capsError && (
          <p className="error" role="alert">
            Could not load instance capabilities: {capsError}
          </p>
        )}
        <InputPanel profiles={profiles} maxPagesLimit={caps?.limits.max_pages} submitting={submitting} fileInputRef={fileInput} onSubmit={(p) => void onSubmit(p)} />
        {caps?.turnstile_site_key && <Turnstile siteKey={caps.turnstile_site_key} handleRef={turnstile} />}
        {submitError && (
          <p className="error" role="alert">
            {submitError}
          </p>
        )}
        <History entries={history} onOpen={reopen} onClear={clearHistory} />
        <section className="jobs" aria-label="Jobs">
          {jobs.map((j) => (
            <JobCard key={j.id} client={client} job={j} profiles={profiles} formats={formats} onResult={onResult} onRemove={onRemove} onUploadInstead={onUploadInstead} />
          ))}
        </section>
        <SupportedInputs capabilities={caps} />
      </main>
      <footer className="footer">
        <p>
          {caps?.instance_name ? `${caps.instance_name}. ` : ""}
          {caps?.sponsor ? `Hosting by ${caps.sponsor}. ` : ""}
          Results are deleted after {retention} hours.
        </p>
        <nav aria-label="Legal and project">
          <a href="/legal/terms">Terms</a>
          <a href="/legal/privacy">Privacy</a>
          <a href="/legal/dmca">DMCA</a>
          <a href="/source">Source</a>
          <a href="/support">Support</a>
        </nav>
      </footer>
    </div>
  );
}
