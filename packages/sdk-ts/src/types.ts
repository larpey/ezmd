// Hand-written REST contract types (spec part1 section 7). When docs/api/openapi.json exists,
// `pnpm -F @intomd/sdk generate` writes src/openapi.d.ts; these types are the stable public surface.

export type Profile = "full" | "compact" | "rag" | "agent";
export type ResultFormat = "md" | "json" | "txt" | "zip";

export type JobState =
  | "queued"
  | "fetching"
  | "converting"
  | "rendering"
  | "done"
  | "failed"
  | "needs_user_action"
  | "expired";

export const TERMINAL_STATES: readonly JobState[] = ["done", "failed", "needs_user_action", "expired"];

export type Severity = "info" | "warning" | "error";

/** A conversion warning (part1 section 4 `Warning`). Rendered verbatim by every interface. */
export interface IntomdWarning {
  kind: string;
  /** Some surfaces call the kind `code`; both are accepted. */
  code?: string;
  severity?: Severity;
  message: string;
  block_id?: string | null;
  page?: number | null;
  count?: number | null;
  detail?: Record<string, string | number | boolean>;
}

export interface JobInput {
  kind: "path" | "bytes" | "url" | "residential_fetch" | string;
  display: string;
  mime?: string | null;
  size_bytes?: number | null;
  sha256?: string | null;
}

export interface NeedsAction {
  kind: "upload_file" | "use_extension" | string;
  reason: string;
  accept?: string[];
  alternatives?: string[];
  supply_url?: string;
}

export interface ErrorBody {
  code: ErrorCode | string;
  message: string;
  status: number;
  request_id?: string;
  detail?: Record<string, unknown>;
  docs?: string;
}

export type ErrorCode =
  | "invalid_request"
  | "turnstile_required"
  | "turnstile_failed"
  | "unauthorized"
  | "forbidden"
  | "not_found"
  | "job_not_ready"
  | "input_too_large"
  | "unsupported_media_type"
  | "url_blocked"
  | "platform_disabled"
  | "rate_limited"
  | "conversion_failed"
  | "fetch_failed"
  | "queue_unavailable"
  | "timeout"
  | "network_error";

export interface Job {
  id: string;
  state: JobState;
  progress: number;
  stage_message: string;
  queue?: string;
  converter_id?: string | null;
  created_at: string;
  updated_at?: string;
  expires_at: string;
  input: JobInput;
  profile: Profile | string;
  warnings_count?: number;
  truncated?: boolean;
  needs_action?: NeedsAction | null;
  error?: ErrorBody | null;
}

export interface JobLinks {
  self: string;
  events: string;
  result: string;
}

export interface ConvertResponse {
  job: Job;
  deduplicated: boolean;
  links: JobLinks;
}

/** `Job` as returned by `convert()`, with the creation envelope fields merged in. */
export type CreatedJob = Job & { deduplicated: boolean; links: JobLinks };

/** Overrides accepted in `options` (dotted keys allowed, e.g. `chunks.chunk_tokens`). */
export interface ConvertOptions {
  max_pages?: number;
  ocr?: boolean;
  [key: string]: unknown;
}

interface ConvertCommon {
  profile?: Profile;
  options?: ConvertOptions;
  idempotencyKey?: string;
  signal?: AbortSignal;
}

export type ConvertInput =
  | (ConvertCommon & { file: Blob; filename?: string })
  | (ConvertCommon & { url: string; preferResidential?: boolean })
  | (ConvertCommon & { text: string; sourceHint?: string; filename?: string });

export interface Capabilities {
  version: string;
  converters: Array<{
    id: string;
    family: string;
    mimes: string[];
    experimental?: boolean;
    loaded?: boolean;
    extras?: string[];
    extensions?: string[];
  }>;
  profiles: Profile[];
  formats: ResultFormat[];
  limits: {
    max_upload_bytes?: number;
    max_url_bytes?: number;
    max_audio_seconds?: number;
    max_pages?: number;
    retention_hours?: number;
  };
  fetch_node_online?: boolean;
  residential_platforms?: string[];
  public_mode?: boolean;
  turnstile_site_key?: string | null;
  instance_name?: string | null;
  sponsor?: string | null;
}

/** Payload of `format=json` (the JsonRenderer output). */
export interface JsonResult {
  markdown: string;
  frontmatter: Record<string, unknown>;
  sidecar: Sidecar | null;
  chunks: Array<Record<string, unknown>>;
}

export interface Sidecar {
  schema?: string;
  profile?: string;
  metrics?: Record<string, unknown>;
  warnings?: IntomdWarning[];
  document?: Record<string, unknown>;
  [key: string]: unknown;
}

export type JobEvent =
  | { type: "progress"; progress: number; stage_message?: string }
  | { type: "state"; state: JobState }
  | { type: "warning"; warning: IntomdWarning }
  | { type: "done"; result_url?: string; tokens?: number; warnings_count?: number }
  | { type: "failed"; error: ErrorBody }
  | { type: "needs_user_action"; needs_action: NeedsAction };

export interface EventSourceLike {
  addEventListener(type: string, listener: (ev: MessageEvent) => void): void;
  close(): void;
  onerror: ((ev: Event) => void) | null;
}

export type EventSourceCtor = new (url: string) => EventSourceLike;
