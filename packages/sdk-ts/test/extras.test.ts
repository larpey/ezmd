import { mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { describe, expect, it, vi } from "vitest";
import { EzmdClient } from "../src/index.js";
import type { EventSourceLike, Job, JobEvent } from "../src/index.js";
import { convertPath } from "../src/node.js";

const json = (body: unknown, status = 200): Response =>
  new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

const job = (over: Partial<Job> = {}): Job => ({
  id: "job_abc", state: "queued", progress: 0, stage_message: "Queued", input: { kind: "bytes", display: "a.md" }, profile: "compact", ...over,
});

class FakeES implements EventSourceLike {
  static last: FakeES | undefined;
  listeners = new Map<string, (ev: MessageEvent) => void>();
  onerror: ((ev: Event) => void) | null = null;
  closed = false;
  constructor(public url: string) {
    FakeES.last = this;
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

function recorder(handler: (url: string, init: RequestInit) => Response) {
  const calls: Array<{ url: string; init: RequestInit }> = [];
  const fn = vi.fn(async (url: RequestInfo | URL, init: RequestInit = {}) => {
    calls.push({ url: String(url), init });
    return handler(String(url), init);
  }) as unknown as typeof fetch;
  return { fn, calls };
}

describe("events()", () => {
  it("yields stream events and ends after the terminal event", async () => {
    const { fn } = recorder(() => json(job({ state: "done" })));
    const client = new EzmdClient({ fetch: fn, EventSource: FakeES });
    const seen: JobEvent[] = [];
    const iter = client.events("job_abc");
    const first = iter.next();
    const es = FakeES.last!;
    es.emit("progress", { progress: 30, stage_message: "Converting" });
    es.emit("done", { tokens: 5 });
    seen.push((await first).value as JobEvent);
    for await (const ev of { [Symbol.asyncIterator]: () => iter }) seen.push(ev);
    expect(seen.map((e) => e.type)).toEqual(["progress", "done"]);
    expect(es.closed).toBe(true);
  });

  it("synthesizes a terminal event when it falls back to polling", async () => {
    const { fn } = recorder(() => json(job({ state: "failed", error: { code: "conversion_failed", message: "Bad.", status: 500 } })));
    const client = new EzmdClient({ fetch: fn, EventSource: FakeES });
    const iter = client.events("job_abc", { pollIntervalMs: 1 });
    const firstP = iter.next();
    FakeES.last!.onerror?.(new Event("error"));
    const types = [((await firstP).value as JobEvent).type];
    for await (const ev of { [Symbol.asyncIterator]: () => iter }) types.push(ev.type);
    expect(types).toEqual(["state", "progress", "failed"]);
  });

  it("stops the stream when the consumer breaks early", async () => {
    const { fn } = recorder(() => json(job()));
    const client = new EzmdClient({ fetch: fn, EventSource: FakeES });
    const iter = client.events("job_abc");
    const p = iter.next();
    const es = FakeES.last!;
    es.emit("state", { state: "converting" });
    expect((await p).value).toEqual({ type: "state", state: "converting" });
    await iter.return(undefined);
    expect(es.closed).toBe(true);
  });

  it("rejects with AbortError when the signal is already aborted", async () => {
    const { fn } = recorder(() => json(job()));
    const ctrl = new AbortController();
    ctrl.abort();
    const client = new EzmdClient({ fetch: fn, EventSource: FakeES });
    await expect(client.waitForJob("job_abc", { signal: ctrl.signal })).rejects.toMatchObject({ name: "AbortError" });
  });
});

describe("other endpoints", () => {
  it("lists warning codes", async () => {
    const entry = { code: "truncated", severity: "warning", family: "core", description: "d", suggestion: "s", truncates: true, aliases: [] };
    const { fn, calls } = recorder(() => json({ warnings: [entry] }));
    expect(await new EzmdClient({ fetch: fn }).warningCodes()).toEqual([entry]);
    expect(calls[0]!.url).toBe("/v1/warnings");
  });

  it("deletes a job", async () => {
    const { fn, calls } = recorder(() => new Response(null, { status: 204 }));
    await new EzmdClient({ fetch: fn, baseUrl: "https://x.example" }).deleteJob("job/1");
    expect(calls[0]!.url).toBe("https://x.example/v1/jobs/job%2F1");
    expect(calls[0]!.init.method).toBe("DELETE");
  });

  it("result() takes the spec's options object", async () => {
    const { fn, calls } = recorder(() => new Response("plain"));
    expect(await new EzmdClient({ fetch: fn }).result("job_abc", { profile: "agent", format: "txt" })).toBe("plain");
    expect(calls[0]!.url).toBe("/v1/jobs/job_abc/result?format=txt&profile=agent");
  });
});

describe("@ezmd/sdk/node", () => {
  it("convertPath uploads a file from disk with its basename", async () => {
    const dir = mkdtempSync(join(tmpdir(), "ezmd-sdk-"));
    const path = join(dir, "notes.md");
    writeFileSync(path, "# Notes\n");
    const envelope = { job: job(), deduplicated: false, links: { self: "s", events: "e", result: "r" } };
    const { fn, calls } = recorder(() => json(envelope, 202));
    const created = await convertPath(new EzmdClient({ fetch: fn }), path, { profile: "rag" });
    expect(created.id).toBe("job_abc");
    const file = (calls[0]!.init.body as FormData).get("file") as File;
    expect(file.name).toBe("notes.md");
    expect(await file.text()).toBe("# Notes\n");
  });
});
