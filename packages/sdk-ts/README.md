# @ezmd/sdk

Dependency-free TypeScript client for the [ezmd](https://github.com/larpey/ezmd) REST API: convert files,
URLs, and text to LLM-ready Markdown on an ezmd instance you run or have access to. Works in browsers and
Node 20+ (ESM and CommonJS), about 3.5 kB gzipped.

```sh
npm install @ezmd/sdk
```

## Usage

```ts
import { EzmdClient } from "@ezmd/sdk";

const ezmd = new EzmdClient({ baseUrl: "http://localhost:8080", apiKey: process.env.EZMD_API_KEY });

const job = await ezmd.convert({ url: "https://example.com/article", profile: "rag" });
await ezmd.waitForJob(job.id, { onEvent: (ev) => console.log(ev.type) });
const markdown = await ezmd.getResult(job.id); // "md" (default), "txt", "json" or "zip"
```

Convert a local file from Node:

```ts
import { EzmdClient } from "@ezmd/sdk";
import { convertPath } from "@ezmd/sdk/node";

const ezmd = new EzmdClient({ baseUrl: "http://localhost:8080" });
const job = await convertPath(ezmd, "./report.pdf", { profile: "compact" });
```

Other calls: `events(id)` (an async iterator over progress events, falling back to polling),
`getJob(id)`, `sidecar(id)` (block provenance), `getCapabilities()`, `warningCodes()`, and `deleteJob(id)`.
Errors are thrown as `EzmdError`, carrying the API's error `code`, the HTTP `status`, the `requestId`, and
`retryAfter` on 429/503.

## Links

- Self-hosting an instance: <https://larpey.github.io/ezmd/selfhost/>
- API reference: <https://larpey.github.io/ezmd/api/>
- Source and issues: <https://github.com/larpey/ezmd>

Apache-2.0.
