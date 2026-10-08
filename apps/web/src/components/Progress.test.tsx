import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { toPercent } from "./JobCard";
import { Progress, stateLabel } from "./Progress";

describe("Progress", () => {
  it("is a polite live region with a determinate bar when progress is known", () => {
    render(<Progress state="converting" progress={42} converter="documents.pdfium_text" />);
    const status = screen.getByRole("status");
    expect(status).toHaveAttribute("aria-live", "polite");
    expect(status).toHaveTextContent("Converting (documents.pdfium_text)");
    expect(screen.getByRole("progressbar")).toHaveAttribute("value", "42");
  });

  it("is indeterminate without progress", () => {
    render(<Progress state="queued" progress={0} message="Queued" />);
    expect(screen.getByRole("progressbar")).not.toHaveAttribute("value");
    expect(screen.getByRole("status")).toHaveTextContent("Waiting in queue");
  });

  it("maps stage names to labels and accepts fractional progress", () => {
    expect(stateLabel("fetching")).toBe("Fetching");
    expect(stateLabel("ocr")).toBe("Reading images");
    expect(stateLabel("postprocessing")).toBe("Formatting");
    expect(stateLabel("mystery")).toBe("mystery");
    expect(toPercent(0.5)).toBe(50);
    expect(toPercent(15)).toBe(15);
  });
});
