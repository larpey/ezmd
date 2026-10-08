import { act, fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createRef } from "react";
import { describe, expect, it, vi } from "vitest";
import { InputPanel, type SubmitPayload } from "./InputPanel";

function setup() {
  const onSubmit = vi.fn<(p: SubmitPayload) => void>();
  render(<InputPanel profiles={["full", "compact", "rag", "agent"]} submitting={false} fileInputRef={createRef<HTMLInputElement>()} onSubmit={onSubmit} />);
  return { onSubmit, user: userEvent.setup() };
}

describe("InputPanel", () => {
  it("labels every control and starts with Convert disabled", () => {
    setup();
    expect(screen.getByLabelText("Link or text")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Choose files/ })).toBeInTheDocument();
    expect(screen.getByLabelText("Files to convert")).toBeInTheDocument();
    expect(screen.getByRole("group", { name: "Profile" })).toBeInTheDocument();
    expect(screen.getByTestId("convert-button")).toBeDisabled();
    expect(screen.getByTestId("input-chip")).toHaveTextContent("Nothing selected");
  });

  it("detects a URL and submits it on Enter with the chosen profile", async () => {
    const { onSubmit, user } = setup();
    await user.type(screen.getByTestId("input-text"), "https://example.com/a.pdf");
    expect(screen.getByTestId("input-chip")).toHaveTextContent("URL");
    await user.click(screen.getByLabelText("rag"));
    screen.getByTestId("input-text").focus();
    await user.keyboard("{Enter}");
    expect(onSubmit).toHaveBeenCalledTimes(1);
    expect(onSubmit.mock.calls[0]![0]).toMatchObject({ text: { kind: "url", url: "https://example.com/a.pdf" }, profile: "rag", files: [] });
    expect(screen.getByTestId("input-text")).toHaveValue("");
  });

  it("treats other text as text: Enter adds a newline, Ctrl+Enter submits", async () => {
    const { onSubmit, user } = setup();
    const box = screen.getByTestId("input-text");
    await user.type(box, "hello world");
    expect(screen.getByTestId("input-chip")).toHaveTextContent("Text, 2 words");
    await user.keyboard("{Enter}");
    expect(onSubmit).not.toHaveBeenCalled();
    await user.keyboard("{Control>}{Enter}{/Control}");
    expect(onSubmit.mock.calls[0]![0].text).toMatchObject({ kind: "text", words: 2 });
  });

  it("collects picked files and options", async () => {
    const { onSubmit, user } = setup();
    const files = [new File(["a"], "a.md", { type: "text/markdown" }), new File(["bb"], "b.csv", { type: "text/csv" })];
    await user.upload(screen.getByTestId("input-file"), files);
    expect(screen.getByTestId("input-chip")).toHaveTextContent("2 files, 3 B");
    await user.click(screen.getByText("Options"));
    await user.type(screen.getByLabelText("Max pages"), "5");
    await user.selectOptions(screen.getByLabelText("OCR"), "off");
    await user.click(screen.getByTestId("convert-button"));
    expect(onSubmit.mock.calls[0]![0]).toMatchObject({ options: { max_pages: 5, ocr: false } });
    expect(onSubmit.mock.calls[0]![0].files.map((f) => f.name)).toEqual(["a.md", "b.csv"]);
  });

  it("accepts dropped files and clipboard images", () => {
    setup();
    const dropped = new File(["x"], "x.pdf", { type: "application/pdf" });
    fireEvent.drop(screen.getByTestId("dropzone"), { dataTransfer: { files: [dropped] } });
    expect(screen.getByTestId("input-chip")).toHaveTextContent("1 file");
    fireEvent.click(screen.getByTestId("input-clear-files"));
    const img = new File(["png"], "image.png", { type: "image/png" });
    fireEvent.paste(screen.getByTestId("input-text"), { clipboardData: { files: [img], getData: () => "" } });
    expect(screen.getByTestId("input-chip")).toHaveTextContent("Image from clipboard");
  });

  it("keeps files chosen while another update is pending, although the input's FileList is reset", () => {
    setup();
    const input = screen.getByTestId("input-file") as HTMLInputElement;
    const picked = [new File(["a"], "a.md", { type: "text/markdown" }), new File(["bb"], "b.csv", { type: "text/csv" })];
    // A live FileList: resetting the input's value empties it, as browsers do.
    const live: File[] = [...picked];
    Object.defineProperty(input, "files", { configurable: true, get: () => live });
    Object.defineProperty(input, "value", { configurable: true, get: () => "", set: () => live.splice(0) });
    act(() => {
      // The profile click leaves an update queued, so React runs the setFiles updater lazily.
      fireEvent.click(screen.getByTestId("profile-rag"));
      fireEvent.change(input);
    });
    expect(screen.getByTestId("input-chip")).toHaveTextContent("2 files, 3 B");
  });
});
