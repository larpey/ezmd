import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { HistoryEntry } from "../lib/storage";
import { History } from "./History";

const future = new Date(Date.now() + 3600_000).toISOString();
const past = new Date(Date.now() - 3600_000).toISOString();
const entry = (over: Partial<HistoryEntry>): HistoryEntry => ({
  id: "job_1",
  title: "Report",
  source_kind: "file",
  created_at: past,
  expires_at: future,
  profile: "compact",
  ...over,
});

function setup(entries: HistoryEntry[]) {
  const handlers = { onOpen: vi.fn(), onOpenLocal: vi.fn(), onToggleKeep: vi.fn(), onClear: vi.fn() };
  render(<History entries={entries} {...handlers} />);
  return handlers;
}

describe("History", () => {
  it("renders nothing when empty", () => {
    const { container } = render(<History entries={[]} onOpen={vi.fn()} onOpenLocal={vi.fn()} onToggleKeep={vi.fn()} onClear={vi.fn()} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("re-opens live rows, toggles keep, and clears", async () => {
    const user = userEvent.setup();
    const h = setup([entry({ preview: "First 200 chars", tokens: 1200 })]);
    await user.click(screen.getByText("History (1)"));
    expect(screen.getByText("First 200 chars")).toBeInTheDocument();
    expect(screen.getByText(/1,200 tokens/)).toBeInTheDocument();
    await user.click(screen.getByTestId("history-open"));
    expect(h.onOpen).toHaveBeenCalledWith(expect.objectContaining({ id: "job_1" }));
    await user.click(screen.getByLabelText("Keep result on this device"));
    expect(h.onToggleKeep).toHaveBeenCalledWith(expect.objectContaining({ id: "job_1" }), true);
    await user.click(screen.getByTestId("history-clear"));
    expect(h.onClear).toHaveBeenCalled();
  });

  it("shows expired rows with the local copy when kept", async () => {
    const user = userEvent.setup();
    const h = setup([entry({ id: "a", expires_at: past, keep: true }), entry({ id: "b", title: "Gone", expires_at: past })]);
    await user.click(screen.getByText("History (2)"));
    expect(screen.getAllByText(/Expired on the server/)).toHaveLength(2);
    expect(screen.queryByTestId("history-open")).toBeNull();
    await user.click(screen.getByTestId("history-open-local"));
    expect(h.onOpenLocal).toHaveBeenCalledWith(expect.objectContaining({ id: "a" }));
    expect(screen.getAllByTestId("history-keep")[1]).toBeDisabled();
  });
});
