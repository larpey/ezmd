import type { ConvertOptions, Profile } from "@ezmd/sdk";
import { useId, useState, type ClipboardEvent, type DragEvent, type FormEvent, type KeyboardEvent, type RefObject } from "react";
import { classifyText, formatBytes } from "../lib/input";

export interface SubmitPayload {
  files: File[];
  text: ReturnType<typeof classifyText>;
  profile: Profile;
  options: ConvertOptions;
}

interface InputPanelProps {
  profiles: readonly Profile[];
  maxPagesLimit?: number;
  submitting: boolean;
  fileInputRef: RefObject<HTMLInputElement>;
  onSubmit: (payload: SubmitPayload) => void;
}

// Files that arrived through a paste event, so the chip can say "Image from clipboard".
const pasted = new WeakSet<File>();

export function describeInput(files: readonly File[], text: ReturnType<typeof classifyText>): string {
  const parts: string[] = [];
  const fromClipboard = files.length > 0 && files.every((f) => pasted.has(f) && f.type.startsWith("image/"));
  if (fromClipboard) parts.push(files.length === 1 ? "Image from clipboard" : `${files.length} images from clipboard`);
  else if (files.length) parts.push(`${files.length} file${files.length > 1 ? "s" : ""}, ${formatBytes(files.reduce((n, f) => n + f.size, 0))}`);
  if (text.kind === "url") parts.push("URL");
  if (text.kind === "text") parts.push(`Text, ${text.words.toLocaleString()} words`);
  return parts.join(" + ");
}

export function InputPanel({ profiles, maxPagesLimit, submitting, fileInputRef, onSubmit }: InputPanelProps) {
  const ids = useId();
  const [value, setValue] = useState("");
  const [files, setFiles] = useState<File[]>([]);
  const [dragging, setDragging] = useState(false);
  const [profile, setProfile] = useState<Profile>("compact");
  const [maxPages, setMaxPages] = useState("");
  const [ocr, setOcr] = useState<"default" | "on" | "off">("default");

  const text = classifyText(value);
  const chip = describeInput(files, text);
  const canSubmit = !submitting && (files.length > 0 || text.kind !== "empty");

  const addFiles = (list: FileList | File[] | null): void => {
    if (!list || !list.length) return;
    // Copy now: a live FileList empties when the input is reset, and the updater may run later.
    const picked = Array.from(list);
    setFiles((prev) => [...prev, ...picked]);
  };

  const submit = (e?: FormEvent): void => {
    e?.preventDefault();
    if (!canSubmit) return;
    const options: ConvertOptions = {};
    const pages = Number.parseInt(maxPages, 10);
    if (Number.isFinite(pages) && pages > 0) options.max_pages = pages;
    if (ocr !== "default") options.ocr = ocr === "on";
    onSubmit({ files, text, profile, options });
    setFiles([]);
    setValue("");
  };

  const onKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>): void => {
    if (e.key !== "Enter") return;
    if (e.ctrlKey || e.metaKey || (text.kind === "url" && !e.shiftKey)) {
      e.preventDefault();
      submit();
    }
  };

  const onPaste = (e: ClipboardEvent<HTMLTextAreaElement>): void => {
    if (e.clipboardData.files.length) {
      e.preventDefault();
      const list = Array.from(e.clipboardData.files);
      list.forEach((f) => pasted.add(f));
      addFiles(list);
    }
  };

  const onDrop = (e: DragEvent<HTMLElement>): void => {
    e.preventDefault();
    setDragging(false);
    addFiles(e.dataTransfer.files);
  };

  return (
    <form className="input-panel" onSubmit={submit} aria-label="Convert" data-testid="input-form">
      <div
        className={`dropzone${dragging ? " dragging" : ""}`}
        data-testid="dropzone"
        onDragOver={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
      >
        <label htmlFor={`${ids}-text`} className="field-label">
          Link or text
        </label>
        <textarea
          id={`${ids}-text`}
          data-testid="input-text"
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={onKeyDown}
          onPaste={onPaste}
          rows={4}
          placeholder="Paste a link or text, or drop files here"
          aria-describedby={`${ids}-chip`}
        />
        <div className="dropzone-row">
          <button type="button" className="btn secondary" onClick={() => fileInputRef.current?.click()} data-testid="input-choose-files" aria-label="Choose files, or drop them on this box">
            Choose files
          </button>
          <input
            ref={fileInputRef}
            id={`${ids}-file`}
            data-testid="input-file"
            type="file"
            multiple
            className="visually-hidden"
            tabIndex={-1}
            aria-label="Files to convert"
            onChange={(e) => {
              addFiles(e.target.files);
              e.target.value = "";
            }}
          />
          <span id={`${ids}-chip`} className="chip" aria-live="polite" data-testid="input-chip">
            {chip || "Nothing selected"}
          </span>
          {files.length > 0 && (
            <button type="button" className="btn ghost" onClick={() => setFiles([])} data-testid="input-clear-files">
              Clear files
            </button>
          )}
        </div>
      </div>

      <fieldset className="profiles">
        <legend>Profile</legend>
        {profiles.map((p) => (
          <label key={p} className={`segment${p === profile ? " selected" : ""}`}>
            <input type="radio" data-testid={`profile-${p}`} name={`${ids}-profile`} value={p} checked={p === profile} onChange={() => setProfile(p)} />
            {p}
          </label>
        ))}
      </fieldset>

      <details className="options">
        <summary>Options</summary>
        <div className="options-grid">
          <label className="field">
            <span>Max pages</span>
            <input type="number" inputMode="numeric" min={1} max={maxPagesLimit} value={maxPages} placeholder={maxPagesLimit ? `up to ${maxPagesLimit}` : "default"} onChange={(e) => setMaxPages(e.target.value)} />
          </label>
          <label className="field">
            <span>OCR</span>
            <select value={ocr} onChange={(e) => setOcr(e.target.value as typeof ocr)}>
              <option value="default">Instance default</option>
              <option value="on">On</option>
              <option value="off">Off</option>
            </select>
          </label>
        </div>
      </details>

      <button type="submit" className="btn primary convert" disabled={!canSubmit} data-testid="convert-button">
        {submitting ? "Converting..." : "Convert"}
      </button>
    </form>
  );
}
