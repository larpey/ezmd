import type { EventSourceCtor, JobEvent } from "./types.js";

export const EVENT_NAMES = ["progress", "state", "warning", "done", "failed", "needs_user_action"] as const;

/** Maps one SSE frame (event name + JSON data) to a typed JobEvent; unknown events yield null. */
export function toJobEvent(name: string, data: string): JobEvent | null {
  let payload: Record<string, unknown>;
  try {
    payload = JSON.parse(data) as Record<string, unknown>;
  } catch {
    return null;
  }
  switch (name) {
    case "progress":
      return { type: "progress", progress: Number(payload.progress ?? 0), stage_message: payload.stage_message as string | undefined };
    case "state":
      return { type: "state", state: payload.state as never };
    case "warning":
      return { type: "warning", warning: payload as never };
    case "done":
      return { type: "done", ...payload };
    case "failed":
      return { type: "failed", error: (payload.error ?? payload) as never };
    case "needs_user_action":
      return { type: "needs_user_action", needs_action: (payload.needs_action ?? payload) as never };
    default:
      return null;
  }
}

export interface StreamHandlers {
  onEvent: (ev: JobEvent) => void;
  /** Called once if the stream fails before a terminal event. */
  onError: () => void;
}

/** Parses a text/event-stream body, invoking `emit` per dispatched frame. */
export async function readSse(body: ReadableStream<Uint8Array>, emit: (name: string, data: string) => void): Promise<void> {
  const reader = body.getReader();
  const decoder = new TextDecoder();
  let buf = "";
  let name = "message";
  let data: string[] = [];
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buf += decoder.decode(value, { stream: true });
    let nl: number;
    while ((nl = buf.indexOf("\n")) >= 0) {
      const line = buf.slice(0, nl).replace(/\r$/, "");
      buf = buf.slice(nl + 1);
      if (line === "") {
        if (data.length) emit(name, data.join("\n"));
        name = "message";
        data = [];
      } else if (line.startsWith("event:")) name = line.slice(6).trim();
      else if (line.startsWith("data:")) data.push(line.slice(5).replace(/^ /, ""));
    }
  }
}

/** Opens the job's event stream with EventSource when possible, else a fetch stream (needed to send headers). */
export function openStream(
  url: string,
  handlers: StreamHandlers,
  opts: { EventSource?: EventSourceCtor; fetch: typeof fetch; headers: Record<string, string>; preferFetch: boolean },
): () => void {
  let closed = false;
  const emit = (name: string, data: string): void => {
    const ev = toJobEvent(name, data);
    if (ev && !closed) handlers.onEvent(ev);
  };
  const fail = (): void => {
    if (!closed) {
      closed = true;
      handlers.onError();
    }
  };
  if (opts.EventSource && !opts.preferFetch) {
    const es = new opts.EventSource(url);
    for (const n of EVENT_NAMES) es.addEventListener(n, (m) => emit(n, String(m.data)));
    es.onerror = () => {
      es.close();
      fail();
    };
    return () => {
      closed = true;
      es.close();
    };
  }
  const ctrl = new AbortController();
  opts
    .fetch(url, { headers: { ...opts.headers, Accept: "text/event-stream" }, signal: ctrl.signal })
    .then(async (res) => {
      if (!res.ok || !res.body) return fail();
      await readSse(res.body, emit);
      fail();
    })
    .catch(fail);
  return () => {
    closed = true;
    ctrl.abort();
  };
}
