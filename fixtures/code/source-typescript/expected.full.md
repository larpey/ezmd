---
title: "input.ts"
source: "input.ts"
source_type: code
converter: code.source_file
converter_version: "0.0.1"
intomd_version: "0.0.1"
schema_version: 1
profile: full
provenance: block
fetched_at: 2026-01-01T00:00:00Z
converted_at: 2026-01-01T00:00:00Z
word_count: 40
tokens: {o200k_base: 100, cl100k_base: 101, claude_approx: 108}
content_hash: "sha256:d88a0a2c8fac9f3a647d98279235ed3eb4b26e81b6e56ed9d03cf33e78c73e22"
source_hash: "sha256:519601b26f9c6fe8b0b4c525af803f1dfa27b6e47b8cefebb9cf15e74c3b477a"
truncated: false
warnings: []
injection_risk: none
extra: {bytes: 330, encoding: utf-8, language: typescript, lines: 14, tokens: 83}
---
# input.ts {#doc}

File: `input.ts`

```typescript
// greeter.ts: a tiny TypeScript module (intomd fixture).
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
