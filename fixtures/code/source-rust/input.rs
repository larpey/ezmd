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
