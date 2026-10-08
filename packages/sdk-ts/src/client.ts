import { IntomdError, errorFromBody, errorFromResponse } from "./errors.js";
import { openStream } from "./sse.js";
import { SDK_VERSION } from "./version.js";
import type {
  Capabilities, ConvertInput, ConvertResponse, CreatedJob, EventSourceCtor, Job, JobEvent, JsonResult,
  Profile, ResultFormat, Sidecar, WarningCodeInfo,
} from "./types.js";
import { TERMINAL_STATES } from "./types.js";

export interface IntomdClientOptions {
  /** API origin; defaults to same-origin ("") in browsers. */
  baseUrl?: string;
  apiKey?: string;
  /** Called before URL submissions when the instance requires Turnstile. */
  turnstileToken?: () => Promise<string | undefined>;
  /** Client identity sent as `X-Intomd-Client` (and `User-Agent` outside browsers), e.g. `intomd-web/0.1.0`. */
  clientName?: string;
  /** Retry once on 429/503 honoring `Retry-After`. */
  retry?: boolean;
  fetch?: typeof fetch;
  EventSource?: EventSourceCtor | null;
}

export interface WaitOptions {
  timeoutMs?: number;
  onEvent?: (ev: JobEvent) => void;
  signal?: AbortSignal;
  /** Initial polling interval when SSE is unavailable; backs off 1.5x up to 10 s. */
  pollIntervalMs?: number;
}

export interface ResultOptions {
  profile?: Profile;
  signal?: AbortSignal;
}

export interface EventsOptions {
  signal?: AbortSignal;
  /** Polling interval used when the event stream is unavailable. */
  pollIntervalMs?: number;
}

const isTerminalEvent = (ev: JobEvent): boolean => ev.type === "done" || ev.type === "failed" || ev.type === "needs_user_action";

const MAX_POLL_MS = 10_000;
const sleep = (ms: number): Promise<void> => new Promise((r) => setTimeout(r, ms));

export class IntomdClient {
  private readonly base: string;
  private readonly opts: IntomdClientOptions;
  private readonly fetchImpl: typeof fetch;

  constructor(opts: IntomdClientOptions = {}) {
    this.opts = opts;
    this.base = (opts.baseUrl ?? "").replace(/\/+$/, "");
    const f = opts.fetch ?? globalThis.fetch;
    this.fetchImpl = (input, init) => f(input, init);
  }

  private headers(extra: Record<string, string> = {}): Record<string, string> {
    const name = this.opts.clientName ?? `intomd-sdk-ts/${SDK_VERSION}`;
    const h: Record<string, string> = { "X-Intomd-Client": name, ...extra };
    if (typeof window === "undefined") h["User-Agent"] = name;
    if (this.opts.apiKey) h["X-API-Key"] = this.opts.apiKey;
    return h;
  }

  private async request(path: string, init: RequestInit = {}, attempt = 0): Promise<Response> {
    let res: Response;
    try {
      res = await this.fetchImpl(this.base + path, { ...init, headers: this.headers(init.headers as Record<string, string>) });
    } catch (err) {
      if ((err as Error)?.name === "AbortError") throw err;
      throw new IntomdError({ code: "network_error", message: "Could not reach the intomd API.", status: 0 });
    }
    if (res.ok) return res;
    const error = await errorFromResponse(res);
    if (this.opts.retry && attempt === 0 && (res.status === 429 || res.status === 503)) {
      await sleep(Math.min(error.retryAfter ?? 1, 30) * 1000);
      return this.request(path, init, 1);
    }
    throw error;
  }

  /** POST /v1/convert. Files and text go multipart; URLs go JSON. One job per call. */
  async convert(input: ConvertInput): Promise<CreatedJob> {
    const options = { ...(input.profile ? { profile: input.profile } : {}), ...input.options };
    const headers: Record<string, string> = input.idempotencyKey ? { "Idempotency-Key": input.idempotencyKey } : {};
    let body: BodyInit;
    if ("url" in input) {
      const token = this.opts.turnstileToken ? await this.opts.turnstileToken() : undefined;
      headers["Content-Type"] = "application/json";
      body = JSON.stringify({
        url: input.url, profile: input.profile, options: input.options ?? {},
        ...(token ? { turnstile_token: token } : {}),
        ...(input.preferResidential ? { prefer_residential: true } : {}),
      });
    } else {
      const form = new FormData();
      if ("file" in input) {
        form.append("file", input.file, input.filename ?? (input.file as File).name ?? "upload.bin");
      } else {
        const type = input.sourceHint ?? "text/plain";
        form.append("file", new Blob([input.text], { type }), input.filename ?? (type === "text/markdown" ? "pasted.md" : type === "text/html" ? "pasted.html" : "pasted.txt"));
      }
      form.append("options", JSON.stringify(options));
      body = form;
    }
    const res = await this.request("/v1/convert", { method: "POST", body, headers, signal: input.signal });
    const env = (await res.json()) as ConvertResponse;
    return { ...env.job, deduplicated: env.deduplicated, links: env.links };
  }

  async getJob(id: string, signal?: AbortSignal): Promise<Job> {
    return (await this.request(`/v1/jobs/${encodeURIComponent(id)}`, { signal })).json() as Promise<Job>;
  }

  /** Resolves with the job once it reaches a terminal state, streaming events to `onEvent`. */
  waitForJob(id: string, wait: WaitOptions = {}): Promise<Job> {
    const ES = this.opts.EventSource === undefined ? (globalThis as { EventSource?: EventSourceCtor }).EventSource : this.opts.EventSource ?? undefined;
    return new Promise<Job>((resolve, reject) => {
      let settled = false;
      let stop = (): void => {};
      const timer = wait.timeoutMs ? setTimeout(() => finish(new IntomdError({ code: "timeout", message: `Job ${id} did not finish within ${wait.timeoutMs} ms.`, status: 504 })), wait.timeoutMs) : undefined;
      const onAbort = (): void => finish(new DOMException("Aborted", "AbortError"));
      wait.signal?.addEventListener("abort", onAbort);
      const finish = (outcome: Job | Error): void => {
        if (settled) return;
        settled = true;
        stop();
        if (timer) clearTimeout(timer);
        wait.signal?.removeEventListener("abort", onAbort);
        if (outcome instanceof Error) reject(outcome);
        else resolve(outcome);
      };
      if (wait.signal?.aborted) {
        onAbort();
        return;
      }
      const settleFromServer = (): void => {
        this.getJob(id, wait.signal).then(finish, finish);
      };
      const poll = async (): Promise<void> => {
        let delay = wait.pollIntervalMs ?? 2000;
        let last = "";
        while (!settled) {
          try {
            const job = await this.getJob(id, wait.signal);
            const key = `${job.state}:${job.progress}:${job.stage_message}`;
            if (key !== last) {
              last = key;
              wait.onEvent?.({ type: "state", state: job.state });
              wait.onEvent?.({ type: "progress", progress: job.progress, stage_message: job.stage_message });
            }
            if (TERMINAL_STATES.includes(job.state)) return finish(job);
          } catch (err) {
            if (!(err instanceof IntomdError) || err.code !== "network_error") return finish(err as Error);
          }
          await sleep(delay);
          delay = Math.min(delay * 1.5, MAX_POLL_MS);
        }
      };
      stop = openStream(
        `${this.base}/v1/jobs/${encodeURIComponent(id)}/events`,
        {
          onEvent: (ev) => {
            wait.onEvent?.(ev);
            if (ev.type === "done" || ev.type === "failed" || ev.type === "needs_user_action") {
              stop(); // the server closes the stream next; do not treat that as an error
              settleFromServer();
            }
          },
          onError: () => void poll(),
        },
        { EventSource: ES, fetch: this.fetchImpl, headers: this.headers(), preferFetch: Boolean(this.opts.apiKey) || !ES },
      );
    });
  }

  /** GET /v1/jobs/{id}/result. `md`/`txt` resolve to a string, `json` to the JsonRenderer payload, `zip` to a Blob. */
  getResult(id: string, format?: "md" | "txt", opts?: ResultOptions): Promise<string>;
  getResult(id: string, format: "json", opts?: ResultOptions): Promise<JsonResult>;
  getResult(id: string, format: "zip", opts?: ResultOptions): Promise<Blob>;
  async getResult(id: string, format: ResultFormat = "md", opts: ResultOptions = {}): Promise<string | JsonResult | Blob> {
    const q = new URLSearchParams({ format });
    if (opts.profile) q.set("profile", opts.profile);
    const res = await this.request(`/v1/jobs/${encodeURIComponent(id)}/result?${q}`, { signal: opts.signal });
    if (format === "json") return (await res.json()) as JsonResult;
    if (format === "zip") return res.blob();
    return res.text();
  }

  async sidecar(id: string, opts: ResultOptions = {}): Promise<Sidecar | null> {
    return (await this.getResult(id, "json", opts)).sidecar;
  }

  /** Async iterator over the job's events (spec part4 4.5.1); ends after the terminal event or on abort. */
  async *events(id: string, opts: EventsOptions = {}): AsyncGenerator<JobEvent, void, undefined> {
    const queue: JobEvent[] = [];
    let wake: (() => void) | undefined;
    let ended = false;
    let failure: unknown;
    const push = (ev: JobEvent): void => {
      queue.push(ev);
      wake?.();
    };
    const end = (err?: unknown): void => {
      ended = true;
      failure ??= err;
      wake?.();
    };
    // An internal controller stops the stream when the consumer breaks out of the loop early.
    const ctrl = new AbortController();
    const onAbort = (): void => ctrl.abort();
    if (opts.signal?.aborted) ctrl.abort();
    opts.signal?.addEventListener("abort", onAbort);
    this.waitForJob(id, { onEvent: push, signal: ctrl.signal, pollIntervalMs: opts.pollIntervalMs }).then(
      (job) => {
        // Polling fallback reports state changes only; close the sequence with a terminal event.
        if (!queue.some(isTerminalEvent)) {
          if (job.state === "done") push({ type: "done", warnings_count: job.warnings_count });
          else if (job.state === "failed" && job.error) push({ type: "failed", error: job.error });
          else if (job.state === "needs_user_action" && job.needs_action) push({ type: "needs_user_action", needs_action: job.needs_action });
        }
        end();
      },
      end,
    );
    try {
      for (;;) {
        const next = queue.shift();
        if (next) {
          yield next;
          if (isTerminalEvent(next)) return;
          continue;
        }
        if (ended) {
          if (failure) throw failure;
          return;
        }
        await new Promise<void>((r) => (wake = r));
        wake = undefined;
      }
    } finally {
      opts.signal?.removeEventListener("abort", onAbort);
      ctrl.abort();
    }
  }

  /** GET /v1/warnings: every canonical warning code with severity, suggestion, and aliases. */
  async warningCodes(signal?: AbortSignal): Promise<WarningCodeInfo[]> {
    const body = (await (await this.request("/v1/warnings", { signal })).json()) as { warnings?: WarningCodeInfo[] };
    return body.warnings ?? [];
  }

  /** DELETE /v1/jobs/{id}: removes the job and its stored blobs. */
  async deleteJob(id: string, signal?: AbortSignal): Promise<void> {
    await this.request(`/v1/jobs/${encodeURIComponent(id)}`, { method: "DELETE", signal });
  }

  async getCapabilities(signal?: AbortSignal): Promise<Capabilities> {
    return (await this.request("/v1/capabilities", { signal })).json() as Promise<Capabilities>;
  }

  /** Throws the job's error when a waited job failed; returns it otherwise. */
  static assertDone(job: Job): Job {
    if (job.state === "failed") throw errorFromBody(job.error, `Job ${job.id} failed.`);
    return job;
  }

  /** Spec part4 4.5.1 form: `result(id, { profile, format })`. */
  result(id: string, opts: ResultOptions & { format?: "md" | "txt" } = {}): Promise<string> {
    return this.getResult(id, opts.format ?? "md", opts);
  }

  // Aliases matching spec part4 4.5.1 naming.
  waitFor = this.waitForJob.bind(this);
  capabilities = this.getCapabilities.bind(this);
}
