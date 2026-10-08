import { openAsBlob } from "node:fs";
import { basename } from "node:path";
import type { EzmdClient } from "./client.js";
import type { ConvertOptions, CreatedJob, Profile } from "./types.js";

export interface ConvertPathOptions {
  profile?: Profile;
  options?: ConvertOptions;
  mime?: string;
  signal?: AbortSignal;
}

/** Uploads a file from disk. `fs.openAsBlob` streams from disk instead of buffering the whole file. */
export async function convertPath(client: EzmdClient, path: string, opts: ConvertPathOptions = {}): Promise<CreatedJob> {
  const file = await openAsBlob(path, opts.mime ? { type: opts.mime } : undefined);
  return client.convert({ file, filename: basename(path), profile: opts.profile, options: opts.options, signal: opts.signal });
}
