import type { Capabilities, CreatedJob, IntomdClient, Profile, ResultFormat } from "@intomd/sdk";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { History } from "./components/History";
import { InputPanel, type SubmitPayload } from "./components/InputPanel";
import { JobCard, type JobSummary, type ResultInfo } from "./components/JobCard";
import { SupportedInputs } from "./components/SupportedInputs";
import { ThemeToggle } from "./components/ThemeToggle";
import { Turnstile, type TurnstileHandle } from "./components/Turnstile";
import { createClient, errorMessage } from "./lib/api";
import { saveBlob } from "./lib/input";
import { keptResults, type KeptResultStore } from "./lib/localstore";
import { HISTORY_KEY, isExpired, loadHistory, removeKey, upsertHistory, writeJson, type HistoryEntry } from "./lib/storage";
import { WarningRegistryContext } from "./lib/warning-context";
import { BUNDLED_REGISTRY, registryFrom, type WarningRegistry } from "./lib/warnings";
import { zipResults } from "./lib/zip";

const DEFAULT_PROFILES: Profile[] = ["full", "compact", "rag", "agent"];
const DEFAULT_FORMATS: ResultFormat[] = ["md", "txt", "json"];
// docx answers 501 on this API and .srt needs transcript segments (Phase 2), so neither is offered yet.
const DOWNLOADABLE: ResultFormat[] = ["md", "txt", "json", "zip"];

// Plain holder (not a React ref): the SDK reads it lazily when a URL is submitted.
const turnstile: { current: TurnstileHandle | null } = { current: null };
const defaultClient = createClient(async () => turnstile.current?.take());

interface FinishedResult {
  title: string;
  markdown: string;
}

export interface AppProps {
  client?: IntomdClient;
  store?: KeptResultStore;
}

export function App({ client = defaultClient, store = keptResults }: AppProps) {
  const fileInput = useRef<HTMLInputElement>(null);
  const [caps, setCaps] = useState<Capabilities | null>(null);
  const [capsError, setCapsError] = useState<string | null>(null);
  const [registry, setRegistry] = useState<WarningRegistry>(BUNDLED_REGISTRY);
  const [jobs, setJobs] = useState<JobSummary[]>([]);
  const [finished, setFinished] = useState<Readonly<Record<string, FinishedResult>>>({});
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [history, setHistory] = useState<HistoryEntry[]>(() => loadHistory());
  // Latest history for async callbacks without re-creating them on every change.
  const historyRef = useRef(history);
  useEffect(() => {
    historyRef.current = history;
  }, [history]);

  useEffect(() => {
    const ctrl = new AbortController();
    client.getCapabilities(ctrl.signal).then(setCaps, (err: unknown) => {
      if ((err as Error).name !== "AbortError") setCapsError(errorMessage(err));
    });
    // Warning registry from the server; the bundled copy stays in use if this fails.
    client.warningCodes(ctrl.signal).then(
      (list) => setRegistry(registryFrom(list)),
      () => undefined,
    );
    return () => ctrl.abort();
  }, [client]);

  useEffect(() => writeJson(HISTORY_KEY, history), [history]);

  const profiles = caps?.profiles?.length ? (caps.profiles as Profile[]) : DEFAULT_PROFILES;
  const formats = (caps?.formats?.length ? (caps.formats as ResultFormat[]) : DEFAULT_FORMATS).filter((f) => DOWNLOADABLE.includes(f));
  const needsTurnstile = caps?.challenge === "turnstile" && Boolean(caps.turnstile_site_key);

  const track = (created: CreatedJob, title: string, kind: HistoryEntry["source_kind"]): void => {
    const profile = (created.profile as Profile) ?? "compact";
    setJobs((list) => [{ id: created.id, title, profile }, ...list.filter((j) => j.id !== created.id)]);
    setHistory((h) =>
      upsertHistory(h, {
        id: created.id,
        title,
        source_kind: kind,
        created_at: created.created_at ?? new Date().toISOString(),
        expires_at: created.expires_at ?? "",
        profile: String(created.profile),
      }),
    );
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

  const onResult = useCallback(
    (id: string, info: ResultInfo) => {
      const prev = historyRef.current.find((e) => e.id === id);
      // Pasted text has no name of its own: the server titles it after the SDK's placeholder file
      // ("pasted"), so the title chosen at submit time stays. Files and URLs take the document title.
      const title = (prev?.source_kind === "text" ? prev.title : info.title) ?? prev?.title ?? id;
      setFinished((m) => ({ ...m, [id]: { title, markdown: info.markdown } }));
      setHistory((h) => {
        const entry = h.find((e) => e.id === id);
        return entry ? upsertHistory(h, { ...entry, tokens: info.tokens, preview: info.preview, title }) : h;
      });
      if (prev?.keep) void store.put({ id, title, markdown: info.markdown, saved_at: new Date().toISOString() });
    },
    [store],
  );

  const onRemove = useCallback((id: string) => setJobs((list) => list.filter((j) => j.id !== id)), []);
  const onUploadInstead = useCallback(() => fileInput.current?.click(), []);

  const reopen = (e: HistoryEntry): void => {
    setJobs((list) => [{ id: e.id, title: e.title, profile: e.profile as Profile }, ...list.filter((j) => j.id !== e.id)]);
  };

  const openLocal = async (e: HistoryEntry): Promise<void> => {
    const kept = await store.get(e.id);
    if (!kept) {
      setNotice("No copy of this result is stored on this device.");
      return;
    }
    setJobs((list) => [{ id: e.id, title: e.title, profile: e.profile as Profile, local: { markdown: kept.markdown } }, ...list.filter((j) => j.id !== e.id)]);
  };

  const toggleKeep = async (e: HistoryEntry, keep: boolean): Promise<void> => {
    setHistory((h) => upsertHistory(h, { ...e, keep }, { moveToTop: false }));
    if (!keep) {
      void store.remove(e.id);
      return;
    }
    let markdown = finished[e.id]?.markdown;
    if (markdown == null && !isExpired(e)) {
      try {
        markdown = await client.getResult(e.id, "md");
      } catch (err) {
        setNotice(`Could not fetch the result to keep it: ${errorMessage(err)}`);
      }
    }
    if (markdown == null) return;
    const ok = await store.put({ id: e.id, title: e.title, markdown, saved_at: new Date().toISOString() });
    if (!ok) setNotice("This browser does not allow storing results on this device.");
  };

  const clearHistory = (): void => {
    removeKey(HISTORY_KEY);
    void store.clear();
    setHistory([]);
  };

  const zippable = useMemo(() => jobs.filter((j) => finished[j.id]).map((j) => ({ id: j.id, ...finished[j.id]! })), [jobs, finished]);

  const downloadAll = async (): Promise<void> => {
    try {
      saveBlob(await zipResults(zippable), "intomd-results.zip");
    } catch (err) {
      setNotice(`Could not build the zip: ${errorMessage(err)}`);
    }
  };

  const retention = caps?.limits.retention_hours ?? 24;

  return (
    <WarningRegistryContext.Provider value={registry}>
      <div className="app">
        <header className="top">
          <h1 className="brand">intomd</h1>
          <nav className="top-links" aria-label="Site">
            <a href="/docs/self-host" data-testid="link-self-host">
              Self-host
            </a>
            <ThemeToggle />
          </nav>
        </header>
        <main id="main">
          <p className="explainer">Paste a link, drop a file, or paste text. Get clean Markdown with nothing silently dropped.</p>
          {capsError && (
            <p className="error" role="alert" data-testid="caps-error">
              Could not load instance capabilities: {capsError}
            </p>
          )}
          <InputPanel profiles={profiles} maxPagesLimit={caps?.limits.max_pages} submitting={submitting} fileInputRef={fileInput} onSubmit={(p) => void onSubmit(p)} />
          {needsTurnstile && caps?.turnstile_site_key && <Turnstile siteKey={caps.turnstile_site_key} handleRef={turnstile} />}
          {submitError && (
            <p className="error" role="alert" data-testid="submit-error">
              {submitError}
            </p>
          )}
          {notice && (
            <p className="notice" role="status" data-testid="app-notice">
              {notice}
            </p>
          )}
          <History entries={history} onOpen={reopen} onOpenLocal={(e) => void openLocal(e)} onToggleKeep={(e, k) => void toggleKeep(e, k)} onClear={clearHistory} />
          {zippable.length > 1 && (
            <button type="button" className="btn secondary" onClick={() => void downloadAll()} data-testid="download-all-zip">
              Download all as zip ({zippable.length})
            </button>
          )}
          <section className="jobs" aria-label="Jobs" data-testid="jobs">
            {jobs.map((j) => (
              <JobCard key={j.id} client={client} job={j} profiles={profiles} formats={formats} onResult={onResult} onRemove={onRemove} onUploadInstead={onUploadInstead} />
            ))}
          </section>
          <SupportedInputs capabilities={caps} />
        </main>
        <footer className="footer" data-testid="footer">
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
    </WarningRegistryContext.Provider>
  );
}
