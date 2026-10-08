---
title: "input.ts"
source: "input.ts"
source_type: code
converter: code.source_file
converter_version: "0.1.0rc1"
ezmd_version: "0.1.0rc1"
schema_version: 1
profile: full
provenance: block
fetched_at: 2026-01-01T00:00:00Z
converted_at: 2026-01-01T00:00:00Z
word_count: 40
tokens: {o200k_base: 99, cl100k_base: 100, claude_approx: 107}
content_hash: "sha256:c9a47a48942c077bf59152373f221dfb073ecfd3125322515c29d76b869de48b"
source_hash: "sha256:3e7675358fddb7ac50a374120d233f2a140f137edf15ef8d7363470d7a89f1d7"
truncated: false
warnings: []
injection_risk: none
extra: {bytes: 328, encoding: utf-8, language: typescript, lines: 14, tokens: 82}
---
# input.ts {#doc}

File: `input.ts`

```typescript
// greeter.ts: a tiny TypeScript module (ezmd fixture).
import { format } from "./format";

export interface Greeting {
  name: string;
  excited?: boolean;
}

export function greet(g: Greeting): string {
  const base = format(`Hello, ${g.name}`);
  return g.excited ? base + "!" : base;
}

export const DEFAULT_NAME = 'world';
```
