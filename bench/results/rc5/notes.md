# rc5 rerun

ezmd built from `fix/rc5` at a71a2aa (detached worktree, wheels 0.1.0rc4 version string), installed in separate
venvs (`ezmd-rc5`, `ezmd-docs-rc5`; same dependency set as the baseline except defusedxml 0.7.1). Same corpora,
samples and seed as 2026-10-13; competitors are not rerun (their 2026-10-13 scores are the comparison). Run
2026-10-13 23:13-23:27 CDT next to the same idle game. `compare.md` is
`python -m tools.bench compare --before 2026-10-13 --after rc5` (paired bootstrap over shared documents).

Text-layer pages still fragmented (more than 30% of paragraphs of 3 characters or fewer): OmniDocBench 42 of 237
(was 158), olmOCR-Bench 28 of 233 (was 119). Outputs with synthesized `col_N` tables: 73 of 300 (was 143) and
63 of 336 (was 141).
