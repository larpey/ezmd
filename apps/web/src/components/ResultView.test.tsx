import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { ResultView, type ResultViewProps } from "./ResultView";

const MD = "---\ntitle: Kitchen Sink\ntokens: 42\n---\n\n# Kitchen Sink\n\nSome **bold** text.\n\n<script>alert(1)</script>\n\n![logo](https://cdn.example.com/x.png)\n";

function setup(over: Partial<ResultViewProps> = {}) {
  const props: ResultViewProps = {
    markdown: MD,
    sidecar: { schema: "ezmd.sidecar/1", warnings: [] },
    warnings: [{ kind: "truncated", message: "Cut at the cap." }],
    tokens: 42,
    tokenizer: "o200k_base",
    profile: "compact",
    profiles: ["full", "compact", "rag", "agent"],
    formats: ["md", "txt", "json"],
    onProfileChange: vi.fn(),
    onDownload: vi.fn(),
    ...over,
  };
  render(<ResultView {...props} />);
  return props;
}

describe("ResultView", () => {
  it("renders sanitized markdown without frontmatter, raw HTML or remote images", () => {
    setup();
    const heading = screen.getByRole("heading", { name: "Kitchen Sink" });
    expect(heading).toBeInTheDocument();
    const panel = heading.closest("[role=tabpanel]")!;
    expect(panel.querySelector("script")).toBeNull();
    expect(panel.querySelector("img")).toBeNull();
    expect(panel.textContent).toContain("<script>alert(1)</script>");
    expect(panel.textContent).not.toContain("tokens: 42");
    expect(screen.getByText("42 tokens")).toHaveAttribute("title", "o200k_base count");
  });

  it("switches tabs with arrow keys following the WAI-ARIA tabs pattern", async () => {
    setup();
    const user = userEvent.setup();
    const rendered = screen.getByRole("tab", { name: "Rendered" });
    expect(rendered).toHaveAttribute("aria-selected", "true");
    rendered.focus();
    await user.keyboard("{ArrowRight}");
    const raw = screen.getByRole("tab", { name: "Raw" });
    expect(raw).toHaveAttribute("aria-selected", "true");
    expect(raw).toHaveFocus();
    expect(screen.getByRole("tabpanel").querySelector("pre")?.textContent).toBe(MD);
    await user.keyboard("{End}");
    expect(screen.getByRole("tab", { name: "Warnings (1)" })).toHaveAttribute("aria-selected", "true");
    expect(screen.getAllByText("Cut at the cap.").length).toBeGreaterThan(0);
    await user.keyboard("{ArrowRight}");
    expect(rendered).toHaveAttribute("aria-selected", "true");
  });

  it("makes the scrollable raw and sidecar blocks keyboard-focusable named regions", async () => {
    setup();
    const user = userEvent.setup();
    await user.click(screen.getByRole("tab", { name: "Raw" }));
    const raw = screen.getByRole("region", { name: "Raw Markdown" });
    expect(raw).toBe(screen.getByTestId("result-raw"));
    expect(raw).toHaveAttribute("tabindex", "0");
    screen.getByTestId("result-wrap").focus();
    await user.tab();
    expect(raw).toHaveFocus();
    await user.click(screen.getByRole("tab", { name: "Sidecar JSON" }));
    expect(screen.getByRole("region", { name: "Sidecar JSON" })).toHaveAttribute("tabindex", "0");
  });

  it("shows the sidecar JSON tab", async () => {
    setup();
    await userEvent.setup().click(screen.getByRole("tab", { name: "Sidecar JSON" }));
    expect(screen.getByRole("tabpanel").textContent).toContain('"schema": "ezmd.sidecar/1"');
  });

  it("copies raw markdown and triggers downloads and profile changes", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, "clipboard", { value: { writeText }, configurable: true });
    const props = setup();
    fireEvent.click(screen.getByRole("button", { name: "Copy Markdown" }));
    expect(await screen.findByRole("button", { name: "Copied" })).toBeInTheDocument();
    expect(writeText).toHaveBeenCalledWith(MD);
    fireEvent.click(screen.getByRole("button", { name: "Download .json" }));
    expect(props.onDownload).toHaveBeenCalledWith("json");
    fireEvent.change(screen.getByLabelText("Profile"), { target: { value: "rag" } });
    expect(props.onProfileChange).toHaveBeenCalledWith("rag");
  });
});
