import { downloadName } from "./input";

export interface ZipEntry {
  id: string;
  title: string;
  markdown: string;
}

/** Unique file names inside the archive: slugified title, falling back to the job id, deduplicated. */
export function zipEntryNames(entries: readonly ZipEntry[]): string[] {
  const used = new Map<string, number>();
  return entries.map((e) => {
    const base = downloadName(e.title, e.id, "md").replace(/\.md$/, "");
    const n = used.get(base) ?? 0;
    used.set(base, n + 1);
    return n === 0 ? `${base}.md` : `${base}-${n + 1}.md`;
  });
}

/** Builds a client-side zip of finished results (spec part4 4.1.3). fflate is loaded lazily, off the main chunk. */
export async function zipResults(entries: readonly ZipEntry[]): Promise<Blob> {
  const { zipSync, strToU8 } = await import("fflate");
  const names = zipEntryNames(entries);
  const files = Object.fromEntries(entries.map((e, i) => [names[i]!, strToU8(e.markdown)]));
  const bytes = zipSync(files, { level: 6 });
  return new Blob([bytes as BlobPart], { type: "application/zip" });
}
