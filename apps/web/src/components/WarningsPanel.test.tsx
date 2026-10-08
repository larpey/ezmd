import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { SUGGESTED_ACTIONS, mergeWarnings } from "../lib/warnings";
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
    expect(screen.getByText("2 warnings")).toBeInTheDocument();
    expect(screen.getByText("Output exceeded 2 MB and was cut.")).toBeInTheDocument();
    expect(screen.getByText("Exact text from the server.")).toBeInTheDocument();
    expect(screen.getByText(SUGGESTED_ACTIONS.truncated!)).toBeInTheDocument();
    expect(screen.getByText("Check the result against the original.")).toBeInTheDocument();
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("expands and announces when any warning is an error", () => {
    const { container } = render(<WarningsPanel warnings={[{ kind: "pages_without_text", severity: "error", message: "3 pages unreadable.", page: 4 }]} />);
    expect(screen.getByRole("alert")).toBeInTheDocument();
    expect(container.querySelector("details")).toHaveAttribute("open");
    expect(screen.getByText("page 4")).toBeInTheDocument();
  });

  it("accepts `code` in place of `kind`", () => {
    render(<WarningsPanel expanded warnings={[{ kind: undefined as unknown as string, code: "injection_flagged", message: "m" }]} />);
    expect(screen.getByText("injection_flagged")).toBeInTheDocument();
    expect(screen.getByText(SUGGESTED_ACTIONS.injection_flagged!)).toBeInTheDocument();
  });

  it("covers the warning kinds required by the spec", () => {
    for (const kind of ["fetch_blocked_by_platform", "pages_without_text", "duration_cap_exceeded", "injection_flagged", "truncated"]) {
      expect(SUGGESTED_ACTIONS[kind]).toBeTruthy();
    }
  });

  it("dedupes warnings merged from SSE and the sidecar", () => {
    const w = { kind: "truncated", message: "cut" };
    expect(mergeWarnings([w], [{ ...w }, { kind: "other", message: "x" }])).toHaveLength(2);
  });
});
