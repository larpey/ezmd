import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { WarningRegistryContext } from "../lib/warning-context";
import { mergeWarnings, registryFrom, suggestedAction } from "../lib/warnings";
import { WarningsPanel } from "./WarningsPanel";

describe("WarningsPanel", () => {
  it("renders nothing collapsed when there are no warnings", () => {
    const { container } = render(<WarningsPanel warnings={[]} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("shows every warning verbatim with a count summary and suggested action", () => {
    render(
      <WarningsPanel
        warnings={[
          { kind: "truncated", severity: "warning", message: "Output exceeded 2 MB and was cut." },
          { kind: "something_new", severity: "info", message: "Exact text from the server." },
        ]}
      />,
    );
    expect(screen.getByTestId("warnings-summary")).toHaveTextContent("2 warnings");
    expect(screen.getByText("Output exceeded 2 MB and was cut.")).toBeInTheDocument();
    expect(screen.getByText("Exact text from the server.")).toBeInTheDocument();
    expect(screen.getByText(suggestedAction({ kind: "truncated", message: "" }))).toBeInTheDocument();
    expect(screen.getByText("Check the result against the original.")).toBeInTheDocument();
    expect(screen.queryByRole("alert")).toBeNull();
    expect(screen.getByTestId("warnings-panel")).not.toHaveAttribute("open");
  });

  it("expands and announces when any warning is an error", () => {
    render(<WarningsPanel warnings={[{ kind: "pages_without_text", severity: "error", message: "3 pages unreadable.", page: 4 }]} />);
    expect(screen.getByRole("alert")).toBeInTheDocument();
    expect(screen.getByTestId("warnings-panel")).toHaveAttribute("open");
    expect(screen.getByText("page 4")).toBeInTheDocument();
  });

  it("accepts `code` in place of `kind` and normalizes aliases", () => {
    render(<WarningsPanel expanded warnings={[{ kind: undefined as unknown as string, code: "injection_flagged", message: "m" }]} />);
    expect(screen.getByText("injection_flagged")).toBeInTheDocument();
    expect(screen.getByTestId("warning-item")).toHaveAttribute("data-code", "injection_suspected");
    expect(screen.getByTestId("warning-action")).toHaveTextContent("instructions aimed at an AI");
  });

  it("links the extension docs for platform blocks", () => {
    render(<WarningsPanel expanded warnings={[{ kind: "fetch_blocked_by_platform", message: "403" }]} />);
    expect(screen.getByRole("link", { name: "About the browser extension" })).toHaveAttribute("href", "/docs/extension");
  });

  it("uses the server registry from context for severity", () => {
    const reg = registryFrom([{ code: "x_new", severity: "error", family: "f", description: "d", suggestion: "Fix it.", truncates: false, aliases: [] }]);
    render(
      <WarningRegistryContext.Provider value={reg}>
        <WarningsPanel warnings={[{ kind: "x_new", message: "bad" }]} />
      </WarningRegistryContext.Provider>,
    );
    expect(screen.getByRole("alert")).toHaveTextContent("Fix it.");
  });

  it("dedupes warnings merged from SSE and the sidecar", () => {
    const w = { kind: "truncated", message: "cut" };
    expect(mergeWarnings([w], [{ ...w }, { kind: "other", message: "x" }])).toHaveLength(2);
  });
});
