import type { ErrorBody, EzmdWarning } from "./types.js";

const CODE_BY_STATUS: Record<number, string> = {
  400: "invalid_request",
  401: "unauthorized",
  403: "forbidden",
  404: "not_found",
  409: "job_not_ready",
  413: "input_too_large",
  415: "unsupported_media_type",
  422: "url_blocked",
  429: "rate_limited",
  500: "conversion_failed",
  502: "fetch_failed",
  503: "queue_unavailable",
  504: "timeout",
};

/** Error thrown by every SDK call; mirrors the API error schema (part1 7.5). */
export class EzmdError extends Error {
  readonly code: string;
  readonly status: number;
  readonly requestId: string | undefined;
  readonly detail: Record<string, unknown>;
  readonly docs: string | undefined;
  /** Seconds, from `Retry-After` on 429/503. */
  readonly retryAfter: number | undefined;
  readonly warnings: EzmdWarning[];

  constructor(body: ErrorBody, retryAfter?: number, warnings: EzmdWarning[] = []) {
    super(body.message);
    this.name = "EzmdError";
    this.code = body.code;
    this.status = body.status;
    this.requestId = body.request_id;
    this.detail = body.detail ?? {};
    this.docs = body.docs;
    this.retryAfter = retryAfter;
    this.warnings = warnings;
  }
}

function parseRetryAfter(value: string | null): number | undefined {
  if (!value) return undefined;
  const secs = Number(value);
  if (Number.isFinite(secs)) return Math.max(0, secs);
  const at = Date.parse(value);
  return Number.isNaN(at) ? undefined : Math.max(0, Math.ceil((at - Date.now()) / 1000));
}

function isErrorBody(value: unknown): value is ErrorBody {
  if (typeof value !== "object" || value === null) return false;
  const v = value as Record<string, unknown>;
  return typeof v.code === "string" && typeof v.message === "string";
}

/** Builds an EzmdError from a non-2xx response, tolerating non-JSON bodies. */
export async function errorFromResponse(res: Response): Promise<EzmdError> {
  const retryAfter = parseRetryAfter(res.headers.get("Retry-After"));
  const requestId = res.headers.get("X-Request-Id") ?? undefined;
  let parsed: unknown;
  try {
    parsed = await res.json();
  } catch {
    parsed = undefined;
  }
  const inner = (parsed as { error?: unknown } | undefined)?.error;
  if (isErrorBody(inner)) {
    return new EzmdError({ ...inner, status: inner.status ?? res.status, request_id: inner.request_id ?? requestId }, retryAfter);
  }
  return new EzmdError(
    {
      code: CODE_BY_STATUS[res.status] ?? "invalid_request",
      message: `Request failed with HTTP ${res.status}.`,
      status: res.status,
      request_id: requestId,
    },
    retryAfter,
  );
}

export function errorFromBody(body: unknown, fallbackMessage: string): EzmdError {
  const inner = (body as { error?: unknown } | undefined)?.error ?? body;
  if (isErrorBody(inner)) return new EzmdError({ ...inner, status: inner.status ?? 500 });
  return new EzmdError({ code: "conversion_failed", message: fallbackMessage, status: 500 });
}
