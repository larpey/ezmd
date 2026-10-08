import type { Capabilities, ConvertInput, CreatedJob, EzmdClient, Job, JobEvent, JsonResult, WaitOptions } from "@ezmd/sdk";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { App } from "./App";
import type { KeptResult, KeptResultStore } from "./lib/localstore";
import { HISTORY_KEY } from "./lib/storage";

vi.mock("./lib/input", async (orig) => ({ ...(await orig<typeof import("./lib/input")>()), saveBlob: vi.fn() }));
const { saveBlob } = await import("./lib/input");

const CAPS: Capabilities = {
  version: "0.1.0",
  converters: [{ id: "text.markdown", family: "text", mimes: ["text/markdown"], experimental: false, loaded: true, extras: [] }],
  profiles: ["full", "compact", "rag", "agent"],
  formats: ["md", "json", "txt", "zip"],
  limits: { max_upload_bytes: 1, max_url_bytes: 1, max_audio_seconds: 1, max_pages: 10, retention_hours: 24 },
  fetch_node_online: false,
  residential_platforms: [],
  public_mode: false,
};

function fakeClient() {
  let n = 0;
  const later = new Date(Date.now() + 86_400_000).toISOString();
  const jobOf = (id: string, over: Partial<Job> = {}): Job => ({ id, state: "queued", progress: 0, stage_message: "Queued", input: { kind: "bytes", display: id }, profile: "compact", expires_at: later, ...over });
  const convert = vi.fn(async (input: ConvertInput): Promise<CreatedJob> => {
    n += 1;
    return { ...jobOf(`job_${n}`, { profile: input.profile ?? "compact" }), deduplicated: false, links: { self: "", events: "", result: "" } };
  });
  const waitForJob = vi.fn(async (id: string, wait: WaitOptions = {}): Promise<Job> => {
    const events: JobEvent[] = [
      { type: "state", state: "converting" },
      { type: "progress", progress: 50, stage_message: "Converting" },
      { type: "warning", warning: { kind: "truncated", message: "Cut at 2 MB." } },
    ];
    events.forEach((e) => wait.onEvent?.(e));
    return jobOf(id, { state: "done", progress: 100 });
  });
  const getResult = vi.fn(async (id: string, format = "md", opts: { profile?: string } = {}): Promise<unknown> => {
    const md = `---\ntitle: Doc ${id}\ntokens: 7\n---\n\n# Doc ${id} (${opts.profile ?? "default"})\n`;
    if (format === "json") return { markdown: md, frontmatter: { title: `Doc ${id}`, tokens: { cl100k_base: 8, o200k_base: 7, claude_approx: 9 } }, sidecar: { warnings: [] }, chunks: [] } satisfies JsonResult;
    return md;
  });
  const client = {
    getCapabilities: vi.fn(async () => CAPS),
    warningCodes: vi.fn(async () => []),
    convert,
    waitForJob,
    getResult,
  };
  return client;
}

function memoryStore(): KeptResultStore & { data: Map<string, KeptResult> } {
  const data = new Map<string, KeptResult>();
  return {
    data,
    put: vi.fn(async (r: KeptResult) => (data.set(r.id, r), true)),
    get: vi.fn(async (id: string) => data.get(id) ?? null),
    remove: vi.fn(async (id: string) => data.delete(id)),
    clear: vi.fn(async () => (data.clear(), true)),
  };
}

function setup() {
  const client = fakeClient();
  const store = memoryStore();
  render(<App client={client as unknown as EzmdClient} store={store} />);
  return { client, store, user: userEvent.setup() };
}

describe("App", () => {
  beforeEach(() => {
    localStorage.clear();
    vi.mocked(saveBlob).mockClear();
  });

  it("converts pasted text, shows progress warnings and the result, and records history", async () => {
    const { client, user } = setup();
    await user.type(screen.getByTestId("input-text"), "some pasted words");
    await user.click(screen.getByTestId("convert-button"));
    expect(client.convert).toHaveBeenCalledWith(expect.objectContaining({ text: "some pasted words", profile: "compact" }));
    const card = await screen.findByTestId("job-card");
    await within(card).findByTestId("result");
    expect(within(card).getByRole("heading", { name: /Doc job_1/ })).toBeInTheDocument();
    expect(within(card).getByTestId("result-tokens")).toHaveTextContent("7 tokens");
    expect(within(card).getAllByText("Cut at 2 MB.").length).toBeGreaterThan(0);
    const stored = JSON.parse(localStorage.getItem(HISTORY_KEY)!) as Array<{ id: string; title: string; preview: string }>;
    // Pasted text keeps its submit-time title; the server only knows it as "pasted".
    expect(stored[0]).toMatchObject({ id: "job_1", title: "Pasted text (3 words)" });
    expect(stored[0]!.preview.startsWith("# Doc job_1")).toBe(true);
    expect(stored[0]).toMatchObject({ tokens: 7 });
    expect(JSON.stringify(stored)).not.toContain("tokens: 7");
  });

  it("creates one job per file and offers download-all as zip", async () => {
    const { client, user } = setup();
    const files = ["a.md", "b.md", "c.md", "d.csv", "e.html"].map((n) => new File([n], n));
    await user.upload(screen.getByTestId("input-file"), files);
    await user.click(screen.getByTestId("convert-button"));
    await waitFor(() => expect(screen.getAllByTestId("result")).toHaveLength(5));
    expect(client.convert).toHaveBeenCalledTimes(5);
    await user.click(screen.getByTestId("download-all-zip"));
    await waitFor(() => expect(saveBlob).toHaveBeenCalledWith(expect.any(Blob), "ezmd-results.zip"));
  });

  it("switches profile by re-requesting the result, never creating a new job", async () => {
    const { client, user } = setup();
    await user.type(screen.getByTestId("input-text"), "https://example.com/x");
    await user.click(screen.getByTestId("convert-button"));
    await screen.findByTestId("result");
    await user.selectOptions(screen.getByTestId("result-profile"), "rag");
    await screen.findByRole("heading", { name: /\(rag\)/ });
    expect(client.convert).toHaveBeenCalledTimes(1);
    expect(client.getResult).toHaveBeenLastCalledWith("job_1", "json", expect.objectContaining({ profile: "rag" }));
    // A URL entry is retitled after the document.
    const stored = JSON.parse(localStorage.getItem(HISTORY_KEY)!) as Array<{ title: string }>;
    expect(stored[0]!.title).toBe("Doc job_1");
  });

  it("keeps a result on the device and clears both stores", async () => {
    const { store, user } = setup();
    await user.type(screen.getByTestId("input-text"), "keep me");
    await user.click(screen.getByTestId("convert-button"));
    await screen.findByTestId("result");
    await user.click(screen.getByText("History (1)"));
    await user.click(screen.getByTestId("history-keep"));
    await waitFor(() => expect(store.data.get("job_1")?.markdown).toContain("# Doc job_1"));
    await user.click(screen.getByTestId("history-clear"));
    expect(store.clear).toHaveBeenCalled();
    expect(localStorage.getItem(HISTORY_KEY)).toBe("[]");
  });

  it("opens the kept copy of an expired history row without contacting the server", async () => {
    localStorage.setItem(
      HISTORY_KEY,
      JSON.stringify([{ id: "old", title: "Old doc", source_kind: "url", created_at: "", expires_at: "2000-01-01T00:00:00Z", profile: "rag", keep: true }]),
    );
    const { client, store, user } = setup();
    store.data.set("old", { id: "old", title: "Old doc", markdown: "# Kept body\n", saved_at: "" });
    await user.click(screen.getByText("History (1)"));
    await user.click(screen.getByTestId("history-open-local"));
    const card = await screen.findByTestId("job-card");
    expect(card).toHaveAttribute("data-state", "local");
    expect(within(card).getByRole("heading", { name: "Kept body" })).toBeInTheDocument();
    expect(client.waitForJob).not.toHaveBeenCalled();
  });

  it("renders without localStorage", async () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    setup();
    expect(await screen.findByText(/Results are deleted after 24 hours/)).toBeInTheDocument();
    vi.restoreAllMocks();
  });
});
