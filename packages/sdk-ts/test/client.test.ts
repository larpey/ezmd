import { describe, expect, it, vi } from "vitest";
import { IntomdClient, IntomdError } from "../src/index.js";
import type { EventSourceLike, Job, JobEvent } from "../src/index.js";
import { readSse, toJobEvent } from "../src/sse.js";

type Call = { url: string; init: RequestInit };

function json(body: unknown, status = 200, headers: Record<string, string> = {}): Response {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json", ...headers } });
}

function mockFetch(...responses: Array<Response | ((call: Call) => Response)>) {
  const calls: Call[] = [];
  const fn = vi.fn(async (url: RequestInfo | URL, init: RequestInit = {}) => {
    const call = { url: String(url), init };
    calls.push(call);
    const next = responses.length > 1 ? responses.shift()! : responses[0]!;
    return typeof next === "function" ? next(call) : next.clone();
  });
  return { fn: fn as unknown as typeof fetch, calls };
}

const job = (over: Partial<Job> = {}): Job => ({
  id: "job_abc",
  state: "queued",
  progress: 0,
  stage_message: "Queued",
  created_at: "2026-10-08T00:00:00Z",
  expires_at: "2026-10-09T00:00:00Z",
  input: { kind: "bytes", display: "a.md" },
  profile: "compact",
  ...over,
});

const envelope = { job: job(), deduplicated: false, links: { self: "/v1/jobs/job_abc", events: "/v1/jobs/job_abc/events", result: "/v1/jobs/job_abc/result" } };

class FakeEventSource implements EventSourceLike {
  static last: FakeEventSource | undefined;
  listeners = new Map<string, (ev: MessageEvent) => void>();
  onerror: ((ev: Event) => void) | null = null;
  closed = false;
  constructor(public url: string) {
    FakeEventSource.last = this;
  }
  addEventListener(type: string, fn: (ev: MessageEvent) => void): void {
    this.listeners.set(type, fn);
  }
  close(): void {
    this.closed = true;
  }
  emit(type: string, data: unknown): void {
    this.listeners.get(type)?.({ data: JSON.stringify(data) } as MessageEvent);
  }
}

describe("convert", () => {
  it("uploads files as multipart with options and client header", async () => {
    const { fn, calls } = mockFetch(json(envelope, 202));
    const client = new IntomdClient({ baseUrl: "http://api/", fetch: fn, clientName: "intomd-web/0.1.0" });
    const created = await client.convert({ file: new Blob(["# hi"], { type: "text/markdown" }), filename: "a.md", profile: "compact", options: { ocr: true } });
    expect(created.id).toBe("job_abc");
    expect(created.links.events).toContain("/events");
    expect(calls[0]!.url).toBe("http://api/v1/convert");
    const headers = calls[0]!.init.headers as Record<string, string>;
    expect(headers["X-Intomd-Client"]).toBe("intomd-web/0.1.0");
    expect(headers["User-Agent"]).toBe("intomd-web/0.1.0");
    const form = calls[0]!.init.body as FormData;
    expect((form.get("file") as File).name).toBe("a.md");
    expect(JSON.parse(form.get("options") as string)).toEqual({ profile: "compact", ocr: true });
  });

  it("sends URLs as JSON with a Turnstile token and API key", async () => {
    const { fn, calls } = mockFetch(json(envelope, 202));
    const client = new IntomdClient({ fetch: fn, apiKey: "ak_test_x", turnstileToken: async () => "tok" });
    await client.convert({ url: "https://example.com/a.pdf", profile: "rag", options: { max_pages: 5 }, idempotencyKey: "k1" });
    const headers = calls[0]!.init.headers as Record<string, string>;
    expect(headers["Content-Type"]).toBe("application/json");
    expect(headers["X-API-Key"]).toBe("ak_test_x");
    expect(headers["Idempotency-Key"]).toBe("k1");
    expect(JSON.parse(calls[0]!.init.body as string)).toEqual({ url: "https://example.com/a.pdf", profile: "rag", options: { max_pages: 5 }, turnstile_token: "tok" });
  });

  it("sends pasted text as a file part", async () => {
    const { fn, calls } = mockFetch(json(envelope, 202));
    await new IntomdClient({ fetch: fn }).convert({ text: "hello", sourceHint: "text/markdown" });
    const file = (calls[0]!.init.body as FormData).get("file") as File;
    expect(file.name).toBe("pasted.md");
    expect(await file.text()).toBe("hello");
  });
});

describe("errors", () => {
  it("throws IntomdError from the error schema", async () => {
    const body = { error: { code: "input_too_large", message: "Too big.", status: 413, request_id: "req_1", detail: { limit_bytes: 1 } } };
    const { fn } = mockFetch(json(body, 413));
    const err = await new IntomdClient({ fetch: fn }).getCapabilities().catch((e: unknown) => e);
    expect(err).toBeInstanceOf(IntomdError);
    expect(err).toMatchObject({ code: "input_too_large", status: 413, requestId: "req_1", message: "Too big.", detail: { limit_bytes: 1 } });
  });

  it("maps non-JSON errors by status and parses Retry-After", async () => {
    const { fn } = mockFetch(new Response("nope", { status: 503, headers: { "Retry-After": "7" } }));
    const err = (await new IntomdClient({ fetch: fn }).getCapabilities().catch((e: unknown) => e)) as IntomdError;
    expect(err.code).toBe("queue_unavailable");
    expect(err.retryAfter).toBe(7);
  });

  it("retries once on 429 when retry is enabled", async () => {
    const { fn, calls } = mockFetch(new Response("", { status: 429, headers: { "Retry-After": "0" } }), json({ version: "0.1.0" }));
    const caps = await new IntomdClient({ fetch: fn, retry: true }).getCapabilities();
    expect(caps.version).toBe("0.1.0");
    expect(calls).toHaveLength(2);
  });

  it("wraps network failures", async () => {
    const fn = (async () => {
      throw new TypeError("fetch failed");
    }) as unknown as typeof fetch;
    await expect(new IntomdClient({ fetch: fn }).getJob("job_x")).rejects.toMatchObject({ code: "network_error" });
  });
});

describe("waitForJob", () => {
  it("follows SSE events and resolves with the final job", async () => {
    const { fn } = mockFetch(json(job({ state: "done", progress: 100 })));
    const client = new IntomdClient({ fetch: fn, EventSource: FakeEventSource });
    const events: JobEvent[] = [];
    const pending = client.waitForJob("job_abc", { onEvent: (e) => events.push(e) });
    const es = FakeEventSource.last!;
    expect(es.url).toBe("/v1/jobs/job_abc/events");
    es.emit("state", { state: "converting" });
    es.emit("progress", { progress: 42, stage_message: "Converting" });
    es.emit("warning", { kind: "truncated", message: "Output was truncated." });
    es.emit("done", { result_url: "/r", tokens: 10 });
    const final = await pending;
    expect(final.state).toBe("done");
    expect(es.closed).toBe(true);
    expect(events.map((e) => e.type)).toEqual(["state", "progress", "warning", "done"]);
    expect(events[2]).toEqual({ type: "warning", warning: { kind: "truncated", message: "Output was truncated." } });
  });

  it("falls back to polling when the stream errors", async () => {
    const { fn, calls } = mockFetch(json(job({ state: "converting", progress: 50 })), json(job({ state: "done", progress: 100 })));
    const client = new IntomdClient({ fetch: fn, EventSource: FakeEventSource });
    const events: JobEvent[] = [];
    const pending = client.waitForJob("job_abc", { onEvent: (e) => events.push(e), pollIntervalMs: 1 });
    FakeEventSource.last!.onerror?.(new Event("error"));
    const final = await pending;
    expect(final.state).toBe("done");
    expect(calls.length).toBe(2);
    expect(events).toContainEqual({ type: "progress", progress: 50, stage_message: "Queued" });
  });

  it("uses a fetch stream when an API key must be sent", async () => {
    const sse = "event: progress\nid: 1\ndata: {\"progress\":10,\"stage_message\":\"x\"}\n\n: keepalive\n\nevent: done\ndata: {}\n\n";
    const { fn, calls } = mockFetch((c) => (c.url.endsWith("/events") ? new Response(sse) : json(job({ state: "done" }))));
    const client = new IntomdClient({ fetch: fn, apiKey: "ak_x", EventSource: FakeEventSource });
    const events: JobEvent[] = [];
    const final = await client.waitForJob("job_abc", { onEvent: (e) => events.push(e) });
    expect(final.state).toBe("done");
    expect((calls[0]!.init.headers as Record<string, string>)["X-API-Key"]).toBe("ak_x");
    expect(events.map((e) => e.type)).toEqual(["progress", "done"]);
  });

  it("times out", async () => {
    const { fn } = mockFetch(json(job()));
    const client = new IntomdClient({ fetch: fn, EventSource: FakeEventSource });
    await expect(client.waitForJob("job_abc", { timeoutMs: 5 })).rejects.toMatchObject({ code: "timeout" });
  });
});

describe("results and capabilities", () => {
  it("returns markdown text with profile and format params", async () => {
    const { fn, calls } = mockFetch(new Response("# Title\n"));
    const md = await new IntomdClient({ fetch: fn }).getResult("job_abc", "md", { profile: "rag" });
    expect(md).toBe("# Title\n");
    expect(calls[0]!.url).toBe("/v1/jobs/job_abc/result?format=md&profile=rag");
  });

  it("parses the json payload and exposes the sidecar", async () => {
    const payload = { markdown: "# T", frontmatter: { title: "T" }, sidecar: { schema: "intomd.sidecar/1", warnings: [] }, chunks: [] };
    const { fn } = mockFetch(json(payload));
    const client = new IntomdClient({ fetch: fn });
    expect((await client.getResult("job_abc", "json")).frontmatter).toEqual({ title: "T" });
    expect((await client.sidecar("job_abc"))?.schema).toBe("intomd.sidecar/1");
  });

  it("fetches capabilities", async () => {
    const { fn } = mockFetch(json({ version: "0.1.0", converters: [], profiles: ["compact"], formats: ["md"], limits: {} }));
    expect((await new IntomdClient({ fetch: fn }).capabilities()).profiles).toEqual(["compact"]);
  });

  it("assertDone throws the job error", () => {
    expect(() => IntomdClient.assertDone(job({ state: "failed", error: { code: "conversion_failed", message: "Bad file.", status: 500 } }))).toThrow("Bad file.");
  });
});

describe("sse parsing", () => {
  it("parses multi-line data and ignores comments", async () => {
    const frames: Array<[string, string]> = [];
    const body = new Response("event: warning\r\ndata: {\"kind\":\"a\",\r\ndata: \"message\":\"m\"}\r\n\r\n").body!;
    await readSse(body, (n, d) => frames.push([n, d]));
    expect(frames).toEqual([["warning", '{"kind":"a",\n"message":"m"}']]);
  });

  it("ignores unknown events and bad JSON", () => {
    expect(toJobEvent("other", "{}")).toBeNull();
    expect(toJobEvent("progress", "not json")).toBeNull();
  });
});
