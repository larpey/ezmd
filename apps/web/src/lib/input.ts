const URL_RE = /^https?:\/\/[^\s<>"']+$/i;

export type TextKind = { kind: "url"; url: string } | { kind: "text"; text: string; words: number } | { kind: "empty" };

/** Classifies the text box: a lone URL, free text, or nothing. */
export function classifyText(value: string): TextKind {
  const trimmed = value.trim();
  if (!trimmed) return { kind: "empty" };
  if (URL_RE.test(trimmed)) {
    try {
      return { kind: "url", url: new URL(trimmed).toString() };
    } catch {
      // fall through to text
    }
  }
  return { kind: "text", text: value, words: trimmed.split(/\s+/).length };
}

export function formatBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / (1024 * 1024)).toFixed(1)} MB`;
}

/** File name from frontmatter title, slugified and capped at 80 chars, falling back to the job id. */
export function downloadName(title: unknown, jobId: string, ext: string): string {
  const slug = typeof title === "string" ? title.toLowerCase().normalize("NFKD").replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "").slice(0, 80) : "";
  return `${slug || jobId}.${ext}`;
}

export function saveBlob(blob: Blob, name: string): void {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
