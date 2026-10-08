---
title: "input.go"
source: "input.go"
source_type: code
converter: code.source_file
converter_version: "0.1.0rc1"
ezmd_version: "0.1.0rc1"
schema_version: 1
profile: full
provenance: block
fetched_at: 2026-01-01T00:00:00Z
converted_at: 2026-01-01T00:00:00Z
word_count: 39
tokens: {o200k_base: 79, cl100k_base: 81, claude_approx: 85}
content_hash: "sha256:4467f0b55d8ac0055620946bfcb3432452debcf51b524f3d162f70ea0e10951e"
source_hash: "sha256:88bf7f791df925de04960074a47738b1824790f4cbeaf45baf1d65267e7de5a5"
truncated: false
warnings: []
injection_risk: none
extra: {bytes: 246, encoding: utf-8, language: go, lines: 14, tokens: 63}
---
# input.go {#doc}

File: `input.go`

```go
// Package shapes computes areas.
package shapes

import "math"

// Circle is a round shape.
type Circle struct {
	Radius float64
}

// Area returns the area of the circle.
func (c Circle) Area() float64 {
	return math.Pi * c.Radius * c.Radius
}
```
