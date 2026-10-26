# ezmd 2026-10-25-figtext vs 2026-10-24-whole

## arXiv papers, correct answers per 10k tokens of converted text

- ezmd-main: 1.893 [1.602, 2.184] -> 1.916 [1.623, 2.216]; after - before +0.023 [-0.005, +0.053] (n=30)
  - vs markitdown (1.576): beats, +0.340 [+0.103, +0.582]
  - vs docling (2.112): ties, -0.197 [-0.451, +0.070]
  - vs mineru (1.734): ties, +0.182 [-0.062, +0.426]
  - vs pymupdf4llm (1.843): ties, +0.073 [-0.172, +0.331]
- ezmd-main-compact: 2.173 [1.647, 2.712] -> 2.180 [1.659, 2.738]; after - before +0.008 [-0.106, +0.140] (n=30)
  - vs markitdown (1.576): beats, +0.604 [+0.179, +1.095]
  - vs docling (2.112): ties, +0.068 [-0.394, +0.589]
  - vs mineru (1.734): beats, +0.447 [+0.043, +0.907]
  - vs pymupdf4llm (1.843): ties, +0.338 [-0.088, +0.838]
- ezmd-main-rag: 1.634 [1.381, 1.905] -> 1.680 [1.416, 1.955]; after - before +0.046 [+0.016, +0.081] (n=30)
  - vs markitdown (1.576): ties, +0.104 [-0.123, +0.327]
  - vs docling (2.112): trails, -0.432 [-0.677, -0.171]
  - vs mineru (1.734): ties, -0.053 [-0.282, +0.188]
  - vs pymupdf4llm (1.843): ties, -0.162 [-0.400, +0.095]

## arXiv papers, Claude tokens per page (Anthropic count_tokens; lower is better)

- ezmd-main: 1681.387 [1483.503, 1896.681] -> n/a; after - before n/a
- ezmd-main-compact: 1111.530 [878.550, 1331.770] -> n/a; after - before n/a
- ezmd-main-rag: 1974.960 [1738.399, 2239.920] -> n/a; after - before n/a

## arXiv papers, outline recall (PDF bookmarks found as headings)

- ezmd-main: 0.786 [0.698, 0.863] -> 0.788 [0.701, 0.865]; after - before +0.002 [+0.000, +0.006] (n=24)
  - vs markitdown (0.010): beats, +0.777 [+0.690, +0.853]
  - vs docling (0.844): trails, -0.056 [-0.107, -0.007]
  - vs mineru (0.874): trails, -0.086 [-0.127, -0.047]
  - vs pymupdf4llm (0.843): trails, -0.055 [-0.097, -0.014]
- ezmd-main-compact: 0.571 [0.471, 0.664] -> 0.589 [0.493, 0.677]; after - before +0.018 [+0.002, +0.036] (n=24)
  - vs markitdown (0.010): beats, +0.578 [+0.483, +0.669]
  - vs docling (0.844): trails, -0.255 [-0.350, -0.173]
  - vs mineru (0.874): trails, -0.285 [-0.390, -0.194]
  - vs pymupdf4llm (0.843): trails, -0.254 [-0.364, -0.163]
- ezmd-main-rag: 0.786 [0.698, 0.863] -> 0.788 [0.701, 0.865]; after - before +0.002 [+0.000, +0.006] (n=24)
  - vs markitdown (0.010): beats, +0.777 [+0.690, +0.853]
  - vs docling (0.844): trails, -0.056 [-0.107, -0.007]
  - vs mineru (0.874): trails, -0.086 [-0.127, -0.047]
  - vs pymupdf4llm (0.843): trails, -0.055 [-0.097, -0.014]

## arXiv papers, answer accuracy (local-model QA over the converted text)

- ezmd-main: 0.780 [0.691, 0.862] -> 0.776 [0.690, 0.859]; after - before -0.004 [-0.013, +0.000] (n=30)
  - vs markitdown (0.787): ties, -0.011 [-0.073, +0.047]
  - vs docling (0.758): ties, +0.018 [-0.090, +0.117]
  - vs mineru (0.753): ties, +0.023 [-0.078, +0.126]
  - vs pymupdf4llm (0.677): beats, +0.099 [+0.019, +0.188]
- ezmd-main-compact: 0.564 [0.425, 0.695] -> 0.577 [0.434, 0.709]; after - before +0.013 [+0.000, +0.035] (n=30)
  - vs markitdown (0.787): trails, -0.209 [-0.312, -0.117]
  - vs docling (0.758): trails, -0.181 [-0.298, -0.073]
  - vs mineru (0.753): trails, -0.176 [-0.286, -0.071]
  - vs pymupdf4llm (0.677): trails, -0.099 [-0.191, -0.014]
- ezmd-main-rag: 0.761 [0.668, 0.844] -> 0.769 [0.677, 0.848]; after - before +0.007 [-0.005, +0.023] (n=30)
  - vs markitdown (0.787): ties, -0.018 [-0.078, +0.047]
  - vs docling (0.758): ties, +0.011 [-0.105, +0.116]
  - vs mineru (0.753): ties, +0.016 [-0.087, +0.116]
  - vs pymupdf4llm (0.677): beats, +0.092 [+0.012, +0.181]

## arXiv papers, answer accuracy on questions whose evidence is in the paper's second half

- ezmd-main: 0.716 [0.603, 0.815] -> 0.710 [0.599, 0.805]; after - before -0.006 [-0.017, +0.000] (n=29)
  - vs markitdown (0.753): ties, -0.043 [-0.118, +0.032]
  - vs docling (0.707): ties, +0.003 [-0.121, +0.126]
  - vs mineru (0.684): ties, +0.026 [-0.103, +0.149]
  - vs pymupdf4llm (0.582): beats, +0.125 [+0.026, +0.228]
- ezmd-main-compact: 0.453 [0.306, 0.608] -> 0.470 [0.319, 0.625]; after - before +0.017 [+0.000, +0.052] (n=29)
  - vs markitdown (0.753): trails, -0.283 [-0.444, -0.128]
  - vs docling (0.707): trails, -0.237 [-0.392, -0.086]
  - vs mineru (0.684): trails, -0.214 [-0.365, -0.078]
  - vs pymupdf4llm (0.582): ties, -0.115 [-0.241, +0.000]
- ezmd-main-rag: 0.706 [0.603, 0.800] -> 0.701 [0.595, 0.797]; after - before -0.004 [-0.030, +0.022] (n=29)
  - vs markitdown (0.753): ties, -0.052 [-0.138, +0.043]
  - vs docling (0.707): ties, -0.006 [-0.132, +0.121]
  - vs mineru (0.684): ties, +0.017 [-0.095, +0.129]
  - vs pymupdf4llm (0.582): beats, +0.116 [+0.013, +0.226]

## arXiv papers, silent loss (over 5% of words lost with no warning raised; lower is better)

- ezmd-main: 0.000 [0.000, 0.000] -> 0.000 [0.000, 0.000]; after - before +0.000 [+0.000, +0.000] (n=30)
  - vs markitdown (0.900): beats, -0.900 [-1.000, -0.800]
  - vs docling (0.100): ties, -0.100 [-0.200, +0.000]
  - vs mineru (0.133): beats, -0.133 [-0.267, -0.033]
  - vs pymupdf4llm (0.167): beats, -0.167 [-0.300, -0.067]
- ezmd-main-compact: 0.000 [0.000, 0.000] -> 0.000 [0.000, 0.000]; after - before +0.000 [+0.000, +0.000] (n=30)
  - vs markitdown (0.900): beats, -0.900 [-1.000, -0.800]
  - vs docling (0.100): ties, -0.100 [-0.200, +0.000]
  - vs mineru (0.133): beats, -0.133 [-0.267, -0.033]
  - vs pymupdf4llm (0.167): beats, -0.167 [-0.300, -0.067]
- ezmd-main-rag: 0.000 [0.000, 0.000] -> 0.000 [0.000, 0.000]; after - before +0.000 [+0.000, +0.000] (n=30)
  - vs markitdown (0.900): beats, -0.900 [-1.000, -0.800]
  - vs docling (0.100): ties, -0.100 [-0.200, +0.000]
  - vs mineru (0.133): beats, -0.133 [-0.267, -0.033]
  - vs pymupdf4llm (0.167): beats, -0.167 [-0.300, -0.067]

## arXiv papers, source recall (share of the LaTeX source's words kept; independent witness)

- ezmd-main: 0.947 [0.915, 0.974] -> 0.947 [0.915, 0.974]; after - before +0.000 [-0.000, +0.000] (n=27)
  - vs markitdown (0.616): beats, +0.330 [+0.234, +0.437]
  - vs docling (0.943): beats, +0.004 [+0.002, +0.006]
  - vs mineru (0.944): ties, +0.003 [-0.001, +0.007]
  - vs pymupdf4llm (0.935): beats, +0.011 [+0.004, +0.019]
- ezmd-main-compact: 0.714 [0.626, 0.801] -> 0.720 [0.632, 0.805]; after - before +0.005 [+0.001, +0.011] (n=27)
  - vs markitdown (0.616): ties, +0.103 [-0.032, +0.243]
  - vs docling (0.943): trails, -0.223 [-0.317, -0.133]
  - vs mineru (0.944): trails, -0.224 [-0.318, -0.136]
  - vs pymupdf4llm (0.935): trails, -0.215 [-0.307, -0.130]
- ezmd-main-rag: 0.946 [0.915, 0.973] -> 0.946 [0.915, 0.973]; after - before +0.000 [-0.000, +0.000] (n=27)
  - vs markitdown (0.616): beats, +0.329 [+0.231, +0.436]
  - vs docling (0.943): beats, +0.003 [+0.002, +0.005]
  - vs mineru (0.944): ties, +0.002 [-0.002, +0.007]
  - vs pymupdf4llm (0.935): beats, +0.011 [+0.004, +0.018]

## arXiv papers, text recall (share of the PDF text layer's words kept)

- ezmd-main: 0.992 [0.989, 0.995] -> 0.992 [0.989, 0.995]; after - before +0.000 [-0.000, +0.000] (n=30)
  - vs markitdown (0.677): beats, +0.315 [+0.229, +0.415]
  - vs docling (0.978): beats, +0.014 [+0.008, +0.020]
  - vs mineru (0.969): beats, +0.023 [+0.017, +0.029]
  - vs pymupdf4llm (0.973): beats, +0.019 [+0.009, +0.032]
- ezmd-main-compact: 0.723 [0.615, 0.820] -> 0.733 [0.630, 0.828]; after - before +0.010 [+0.001, +0.025] (n=30)
  - vs markitdown (0.677): ties, +0.057 [-0.083, +0.193]
  - vs docling (0.978): trails, -0.244 [-0.348, -0.152]
  - vs mineru (0.969): trails, -0.235 [-0.339, -0.142]
  - vs pymupdf4llm (0.973): trails, -0.239 [-0.342, -0.149]
- ezmd-main-rag: 0.992 [0.989, 0.995] -> 0.992 [0.989, 0.995]; after - before +0.000 [-0.000, +0.000] (n=30)
  - vs markitdown (0.677): beats, +0.315 [+0.229, +0.415]
  - vs docling (0.978): beats, +0.014 [+0.008, +0.020]
  - vs mineru (0.969): beats, +0.023 [+0.017, +0.029]
  - vs pymupdf4llm (0.973): beats, +0.019 [+0.009, +0.032]

## arXiv papers, o200k tokens per page (lower is better)

- ezmd-main: 1140.087 [996.002, 1300.699] -> 1121.293 [977.732, 1283.986]; after - before -18.793 [-32.831, -7.246] (n=30)
  - vs markitdown (1440.580): beats, -319.287 [-448.417, -201.308]
  - vs docling (930.100): trails, +191.193 [+131.654, +260.261]
  - vs mineru (1226.143): beats, -104.850 [-205.331, -19.618]
  - vs pymupdf4llm (1054.953): ties, +66.340 [-3.372, +142.421]
- ezmd-main-compact: 736.193 [580.389, 887.116] -> 758.673 [592.839, 922.379]; after - before +22.480 [-11.955, +75.744] (n=30)
  - vs markitdown (1440.580): beats, -681.907 [-898.803, -502.453]
  - vs docling (930.100): beats, -171.427 [-309.599, -45.665]
  - vs mineru (1226.143): beats, -467.470 [-684.575, -301.399]
  - vs pymupdf4llm (1054.953): beats, -296.280 [-469.961, -150.886]
- ezmd-main-rag: 1294.623 [1133.562, 1479.412] -> 1272.693 [1114.646, 1460.384]; after - before -21.930 [-38.551, -8.273] (n=30)
  - vs markitdown (1440.580): beats, -167.887 [-297.310, -45.071]
  - vs docling (930.100): trails, +342.593 [+267.595, +428.148]
  - vs mineru (1226.143): ties, +46.550 [-52.201, +144.645]
  - vs pymupdf4llm (1054.953): trails, +217.740 [+137.303, +311.406]
