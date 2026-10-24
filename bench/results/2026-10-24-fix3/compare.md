# ezmd 2026-10-24-fix3 vs 2026-10-24

## arXiv papers, correct answers per 10k tokens of converted text

- ezmd-main-rag: 1.891 [1.469, 2.314] -> 1.835 [1.391, 2.266]; after - before -0.056 [-0.202, +0.081] (n=30)
  - vs docling (2.525): trails, -0.689 [-0.979, -0.384]
  - vs mineru (2.128): trails, -0.293 [-0.518, -0.074]
  - vs pymupdf4llm (2.272): trails, -0.437 [-0.682, -0.187]

## arXiv papers, Claude tokens per page (Anthropic count_tokens; lower is better)

- ezmd-main-rag: 2067.327 [1819.438, 2347.938] -> 1974.960 [1738.399, 2239.920]; after - before -92.367 [-111.767, -75.592] (n=30)
  - vs docling (1425.253): trails, +549.707 [+433.125, +680.082]
  - vs mineru (1819.350): trails, +155.610 [+10.144, +300.392]
  - vs pymupdf4llm (1590.480): trails, +384.480 [+262.470, +522.073]

## arXiv papers, outline recall (PDF bookmarks found as headings)

- ezmd-main-rag: 0.786 [0.698, 0.863] -> 0.786 [0.698, 0.863]; after - before +0.000 [+0.000, +0.000] (n=24)
  - vs docling (0.844): trails, -0.058 [-0.110, -0.008]
  - vs mineru (0.874): trails, -0.088 [-0.130, -0.048]
  - vs pymupdf4llm (0.843): trails, -0.057 [-0.101, -0.015]

## arXiv papers, answer accuracy (local-model QA over the converted text)

- ezmd-main-rag: 0.802 [0.722, 0.876] -> 0.742 [0.640, 0.831]; after - before -0.060 [-0.127, +0.007] (n=30)
  - vs docling (0.800): ties, -0.058 [-0.171, +0.049]
  - vs mineru (0.816): ties, -0.073 [-0.180, +0.020]
  - vs pymupdf4llm (0.776): ties, -0.033 [-0.140, +0.080]

## arXiv papers, silent loss (over 5% of words lost with no warning raised; lower is better)

- ezmd-main-rag: 0.000 [0.000, 0.000] -> 0.000 [0.000, 0.000]; after - before +0.000 [+0.000, +0.000] (n=30)
  - vs docling (0.100): ties, -0.100 [-0.200, +0.000]
  - vs mineru (0.133): beats, -0.133 [-0.267, -0.033]
  - vs pymupdf4llm (0.167): beats, -0.167 [-0.300, -0.067]

## arXiv papers, source recall (share of the LaTeX source's words kept; independent witness)

- ezmd-main-rag: 0.946 [0.915, 0.973] -> 0.946 [0.915, 0.973]; after - before -0.000 [-0.000, +0.000] (n=27)
  - vs docling (0.943): beats, +0.003 [+0.002, +0.005]
  - vs mineru (0.944): ties, +0.002 [-0.002, +0.007]
  - vs pymupdf4llm (0.935): beats, +0.011 [+0.004, +0.018]

## arXiv papers, text recall (share of the PDF text layer's words kept)

- ezmd-main-rag: 0.992 [0.989, 0.995] -> 0.992 [0.989, 0.995]; after - before -0.000 [-0.000, +0.000] (n=30)
  - vs docling (0.978): beats, +0.014 [+0.008, +0.020]
  - vs mineru (0.969): beats, +0.023 [+0.017, +0.029]
  - vs pymupdf4llm (0.973): beats, +0.019 [+0.009, +0.032]

## arXiv papers, o200k tokens per page (lower is better)

- ezmd-main-rag: 1363.163 [1191.607, 1562.218] -> 1294.623 [1133.562, 1479.412]; after - before -68.540 [-81.707, -57.253] (n=30)
  - vs docling (930.107): trails, +364.517 [+286.596, +452.913]
  - vs mineru (1226.150): ties, +68.473 [-36.344, +170.605]
  - vs pymupdf4llm (1054.953): trails, +239.670 [+155.683, +333.662]
