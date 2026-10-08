import { EzmdError } from "@ezmd/sdk";
import type { EzmdClient, EzmdWarning, JobEvent, JobState, JsonResult, NeedsAction, Profile, ResultFormat } from "@ezmd/sdk";
import { useCallback, useEffect, useState } from "react";
import { errorMessage } from "../lib/api";
import { downloadName, saveBlob } from "../lib/input";
import { stripFrontmatter } from "../lib/markdown";
import { PREVIEW_CHARS } from "../lib/storage";
import { tokenBadge } from "../lib/tokens";
import { mergeWarnings } from "../lib/warnings";
import { Progress } from "./Progress";
import { ResultView } from "./ResultView";
import { WarningsPanel } from "./WarningsPanel";

export interface JobSummary {
  id: string;
  title: string;
  profile: Profile;
  /** Set when re-opened from a kept local copy after the server TTL; no requests are made. */
  local?: { markdown: string };
}

export interface ResultInfo {
  tokens?: number;
  preview: string;
  title?: string;
  markdown: string;
}

interface JobCardProps {
  client: EzmdClient;
  job: JobSummary;
  profiles: readonly Profile[];
  formats: readonly ResultFormat[];
  onResult: (id: string, info: ResultInfo) => void;
  onRemove: (id: string) => void;
  onUploadInstead: () => void;
}

interface LiveState {
  state: JobState | string;
  progress: number;
  message?: string;
  converter?: string | null;
}

const LOCAL_FORMATS: readonly ResultFormat[] = ["md", "txt"];

/** Progress events carry 0..100 from this API; tolerate a 0..1 fraction too (spec part4 4.1.2 step 5). */
export function toPercent(p: number): number {
  return p > 0 && p < 1 ? p * 100 : p;
}

function LocalJobCard({ job, onRemove }: Pick<JobCardProps, "job" | "onRemove">) {
  const markdown = job.local?.markdown ?? "";
  const download = (format: ResultFormat): void => {
    const body = format === "txt" ? stripFrontmatter(markdown) : markdown;
    saveBlob(new Blob([body], { type: format === "txt" ? "text/plain" : "text/markdown" }), downloadName(job.title, job.id, format));
  };
  return (
    <article className="job-card" aria-label={`Job ${job.title}`} data-testid="job-card" data-job-id={job.id} data-state="local">
      <header className="job-head">
        <h3 className="job-title">{job.title}</h3>
        <button type="button" className="btn ghost" onClick={() => onRemove(job.id)} aria-label={`Close ${job.title}`} data-testid="job-close">
          Close
        </button>
      </header>
      <p className="notice">Expired on the server. Showing the copy kept on this device.</p>
      <ResultView markdown={markdown} sidecar={null} warnings={[]} profile={job.profile} profiles={[job.profile]} formats={LOCAL_FORMATS} onProfileChange={() => {}} onDownload={download} />
    </article>
  );
}

function RemoteJobCard({ client, job, profiles, formats, onResult, onRemove, onUploadInstead }: JobCardProps) {
  const [live, setLive] = useState<LiveState>({ state: "queued", progress: 0 });
  const [liveWarnings, setLiveWarnings] = useState<EzmdWarning[]>([]);
  const [result, setResult] = useState<JsonResult | null>(null);
  const [profile, setProfile] = useState<Profile>(job.profile);
  const [error, setError] = useState<string | null>(null);
  const [needs, setNeeds] = useState<NeedsAction | null>(null);
  const [busy, setBusy] = useState(false);

  const loadResult = useCallback(
    async (p: Profile, signal?: AbortSignal) => {
      setBusy(true);
      try {
        // Re-renders from the server's cached IR; never creates a new job (spec part4 4.1.3).
        const res = await client.getResult(job.id, "json", { profile: p, signal });
        setResult(res);
        setError(null);
        onResult(job.id, {
          tokens: tokenBadge(res.frontmatter?.tokens)?.count,
          preview: stripFrontmatter(res.markdown).trimStart().slice(0, PREVIEW_CHARS),
          title: typeof res.frontmatter?.title === "string" ? res.frontmatter.title : undefined,
          markdown: res.markdown,
        });
      } catch (err) {
        if ((err as Error).name !== "AbortError") setError(errorMessage(err));
      } finally {
        setBusy(false);
      }
    },
    [client, job.id, onResult],
  );

  useEffect(() => {
    const ctrl = new AbortController();
    const onEvent = (ev: JobEvent): void => {
      if (ev.type === "progress") setLive((s) => ({ ...s, progress: toPercent(ev.progress), message: ev.stage_message ?? s.message }));
      else if (ev.type === "state") setLive((s) => ({ ...s, state: ev.state }));
      else if (ev.type === "warning") setLiveWarnings((ws) => [...ws, ev.warning]);
    };
    client
      .waitForJob(job.id, { onEvent, signal: ctrl.signal })
      .then((final) => {
        setLive({ state: final.state, progress: toPercent(final.progress), message: final.stage_message, converter: final.converter_id });
        if (final.state === "done") return loadResult(job.profile, ctrl.signal);
        if (final.state === "needs_user_action") setNeeds(final.needs_action ?? null);
        else if (final.state === "failed") setError(final.error?.message ?? "Conversion failed.");
        else if (final.state === "expired") setError("Expired on the server.");
        return undefined;
      })
      .catch((err: unknown) => {
        if ((err as Error).name === "AbortError") return;
        if (err instanceof EzmdError && err.code === "not_found") {
          setLive((s) => ({ ...s, state: "expired" }));
          setError("Expired on the server.");
        } else setError(errorMessage(err));
      });
    return () => ctrl.abort();
  }, [client, job.id, job.profile, loadResult]);

  const changeProfile = (p: Profile): void => {
    setProfile(p);
    void loadResult(p);
  };

  const download = async (format: ResultFormat): Promise<void> => {
    if (!result) return;
    const title = result.frontmatter?.title;
    try {
      if (format === "md") saveBlob(new Blob([result.markdown], { type: "text/markdown" }), downloadName(title, job.id, "md"));
      else if (format === "json") saveBlob(new Blob([JSON.stringify(result.sidecar ?? result, null, 2)], { type: "application/json" }), downloadName(title, job.id, "json"));
      else if (format === "txt") saveBlob(new Blob([await client.getResult(job.id, "txt", { profile })], { type: "text/plain" }), downloadName(title, job.id, "txt"));
      else saveBlob(await client.getResult(job.id, "zip", { profile }), downloadName(title, job.id, "zip"));
    } catch (err) {
      setError(errorMessage(err));
    }
  };

  const warnings = mergeWarnings(liveWarnings, result?.sidecar?.warnings);
  const badge = tokenBadge(result?.frontmatter?.tokens);
  const finished = live.state === "done" || live.state === "failed" || live.state === "expired" || live.state === "needs_user_action";

  return (
    <article className="job-card" aria-label={`Job ${job.title}`} data-testid="job-card" data-job-id={job.id} data-state={result ? "done" : live.state}>
      <header className="job-head">
        <h3 className="job-title">{job.title}</h3>
        <button type="button" className="btn ghost" onClick={() => onRemove(job.id)} aria-label={`Close ${job.title}`} data-testid="job-close">
          Close
        </button>
      </header>
      {!result && <Progress state={live.state} progress={finished ? 100 : live.progress} message={live.message} converter={live.converter} />}
      {needs && (
        <div className="notice" role="alert" data-testid="job-needs-action">
          <p>{needs.reason}</p>
          {needs.kind === "upload_file" && (
            <button type="button" className="btn" onClick={onUploadInstead}>
              Upload the file instead
            </button>
          )}
        </div>
      )}
      {error && (
        <p className="error" role="alert" data-testid="job-error">
          {error}
        </p>
      )}
      {!result && warnings.length > 0 && <WarningsPanel warnings={warnings} />}
      {result && (
        <ResultView
          markdown={result.markdown}
          sidecar={result.sidecar}
          warnings={warnings}
          tokens={badge?.count}
          tokenizer={badge?.tokenizer ?? undefined}
          profile={profile}
          profiles={profiles}
          formats={formats}
          busy={busy}
          onProfileChange={changeProfile}
          onDownload={(f) => void download(f)}
        />
      )}
    </article>
  );
}

export function JobCard(props: JobCardProps) {
  return props.job.local ? <LocalJobCard job={props.job} onRemove={props.onRemove} /> : <RemoteJobCard {...props} />;
}
