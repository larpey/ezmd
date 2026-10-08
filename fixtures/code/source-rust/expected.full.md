---
title: "input.rs"
source: "input.rs"
source_type: code
converter: code.source_file
converter_version: "0.1.0rc1"
ezmd_version: "0.1.0rc1"
schema_version: 1
profile: full
provenance: block
fetched_at: 2026-01-01T00:00:00Z
converted_at: 2026-01-01T00:00:00Z
word_count: 104
tokens: {o200k_base: 350, cl100k_base: 350, claude_approx: 378}
content_hash: "sha256:b6f4edfc210a5c3421d64564ef40d5a7ddf984daea429fa72402dba49f94dd05"
source_hash: "sha256:eca22c320bc92c9e91a0ca9d1966dc31b04431e9b2f8ec78f33e9648dfcd91c7"
truncated: false
warnings: []
injection_risk: none
extra: {bytes: 1134, encoding: utf-8, language: rust, lines: 45, tokens: 332}
---
# input.rs {#doc}

File: `input.rs`

```rust
//! ledger.rs: a fixed-point ledger (ezmd fixture).
use std::collections::BTreeMap;
use std::fmt;

/// Amounts are stored in cents to avoid floating-point drift.
#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord)]
pub struct Cents(pub i64);

impl fmt::Display for Cents {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "{}.{:02}", self.0 / 100, (self.0 % 100).abs())
    }
}

pub trait Account {
    fn balance(&self) -> Cents;
}

#[derive(Default)]
pub struct Ledger<'a> {
    entries: BTreeMap<&'a str, Vec<Cents>>,
}

impl<'a> Ledger<'a> {
    pub fn post(&mut self, account: &'a str, amount: Cents) {
        self.entries.entry(account).or_default().push(amount);
    }

    pub fn total(&self, account: &str) -> Option<Cents> {
        self.entries.get(account).map(|v| Cents(v.iter().map(|c| c.0).sum()))
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn totals_in_cents() {
        let mut l = Ledger::default();
        l.post("cash", Cents(1050));
        l.post("cash", Cents(-25));
        assert_eq!(l.total("cash").unwrap().to_string(), "10.25");
    }
}
```
