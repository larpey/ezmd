# ezmd 2026-10-24-fix2 vs 2026-10-24

## arXiv papers, correct answers per 10k tokens of converted text

- ezmd-main: 2.049 [1.578, 2.527] -> 2.121 [1.619, 2.622]; after - before +0.072 [-0.070, +0.259] (n=30)
  - vs docling (2.525): trails, -0.404 [-0.719, -0.084]
  - vs mineru (2.128): ties, -0.007 [-0.292, +0.277]
  - vs pymupdf4llm (2.272): ties, -0.151 [-0.413, +0.109]
- ezmd-main-compact: 3.048 [2.599, 3.499] -> 3.056 [2.618, 3.505]; after - before +0.008 [-0.152, +0.183] (n=30)
  - vs docling (2.525): ties, +0.531 [-0.035, +1.165]
  - vs mineru (2.128): beats, +0.928 [+0.400, +1.516]
  - vs pymupdf4llm (2.272): beats, +0.783 [+0.256, +1.395]
- ezmd-main-rag: 1.891 [1.469, 2.314] -> 1.810 [1.357, 2.266]; after - before -0.081 [-0.227, +0.054] (n=30)
  - vs docling (2.525): trails, -0.714 [-1.040, -0.397]
  - vs mineru (2.128): trails, -0.318 [-0.579, -0.059]
  - vs pymupdf4llm (2.272): trails, -0.462 [-0.728, -0.213]

## arXiv papers, Claude tokens per page (Anthropic count_tokens; lower is better)

- ezmd-main: 1710.360 [1509.323, 1932.926] -> 1681.387 [1483.503, 1896.681]; after - before -28.973 [-37.321, -20.916] (n=30)
  - vs docling (1425.253): trails, +256.133 [+174.948, +345.100]
  - vs mineru (1819.350): beats, -137.963 [-284.059, -13.940]
  - vs pymupdf4llm (1590.480): ties, +90.907 [-7.607, +188.143]
- ezmd-main-compact: 1096.877 [861.671, 1328.859] -> 1111.530 [878.550, 1331.770]; after - before +14.653 [-11.643, +48.748] (n=30)
  - vs docling (1425.253): beats, -313.723 [-495.811, -147.611]
  - vs mineru (1819.350): beats, -707.820 [-999.387, -477.131]
  - vs pymupdf4llm (1590.480): beats, -478.950 [-701.366, -282.577]
- ezmd-main-rag: 2067.327 [1819.438, 2347.938] -> 2030.980 [1788.906, 2302.359]; after - before -36.347 [-51.137, -22.742] (n=30)
  - vs docling (1425.253): trails, +605.727 [+484.045, +742.926]
  - vs mineru (1819.350): trails, +211.630 [+63.490, +361.378]
  - vs pymupdf4llm (1590.480): trails, +440.500 [+312.434, +585.760]

## arXiv papers, outline recall (PDF bookmarks found as headings)

- ezmd-main: 0.786 [0.698, 0.863] -> 0.786 [0.698, 0.863]; after - before +0.000 [+0.000, +0.000] (n=24)
  - vs docling (0.844): trails, -0.058 [-0.110, -0.008]
  - vs mineru (0.874): trails, -0.088 [-0.130, -0.048]
  - vs pymupdf4llm (0.843): trails, -0.057 [-0.101, -0.015]
- ezmd-main-compact: 0.567 [0.467, 0.659] -> 0.571 [0.471, 0.664]; after - before +0.004 [+0.000, +0.009] (n=24)
  - vs docling (0.844): trails, -0.273 [-0.375, -0.190]
  - vs mineru (0.874): trails, -0.303 [-0.410, -0.211]
  - vs pymupdf4llm (0.843): trails, -0.272 [-0.384, -0.178]
- ezmd-main-rag: 0.786 [0.698, 0.863] -> 0.786 [0.698, 0.863]; after - before +0.000 [+0.000, +0.000] (n=24)
  - vs docling (0.844): trails, -0.058 [-0.110, -0.008]
  - vs mineru (0.874): trails, -0.088 [-0.130, -0.048]
  - vs pymupdf4llm (0.843): trails, -0.057 [-0.101, -0.015]

## arXiv papers, answer accuracy (local-model QA over the converted text)

- ezmd-main: 0.762 [0.673, 0.847] -> 0.762 [0.678, 0.838]; after - before +0.000 [-0.040, +0.040] (n=30)
  - vs docling (0.800): ties, -0.038 [-0.133, +0.060]
  - vs mineru (0.816): ties, -0.053 [-0.147, +0.033]
  - vs pymupdf4llm (0.776): ties, -0.013 [-0.107, +0.080]
- ezmd-main-compact: 0.729 [0.636, 0.813] -> 0.742 [0.656, 0.822]; after - before +0.013 [-0.020, +0.053] (n=30)
  - vs docling (0.800): ties, -0.058 [-0.147, +0.040]
  - vs mineru (0.816): ties, -0.073 [-0.167, +0.013]
  - vs pymupdf4llm (0.776): ties, -0.033 [-0.120, +0.073]
- ezmd-main-rag: 0.802 [0.722, 0.876] -> 0.756 [0.662, 0.847]; after - before -0.047 [-0.113, +0.007] (n=30)
  - vs docling (0.800): ties, -0.044 [-0.151, +0.056]
  - vs mineru (0.816): ties, -0.060 [-0.167, +0.040]
  - vs pymupdf4llm (0.776): ties, -0.020 [-0.120, +0.093]

## arXiv papers, silent loss (over 5% of words lost with no warning raised; lower is better)

- ezmd-main: 0.000 [0.000, 0.000] -> 0.000 [0.000, 0.000]; after - before +0.000 [+0.000, +0.000] (n=30)
  - vs docling (0.100): ties, -0.100 [-0.200, +0.000]
  - vs mineru (0.133): beats, -0.133 [-0.267, -0.033]
  - vs pymupdf4llm (0.167): beats, -0.167 [-0.300, -0.067]
- ezmd-main-compact: 0.000 [0.000, 0.000] -> 0.000 [0.000, 0.000]; after - before +0.000 [+0.000, +0.000] (n=30)
  - vs docling (0.100): ties, -0.100 [-0.200, +0.000]
  - vs mineru (0.133): beats, -0.133 [-0.267, -0.033]
  - vs pymupdf4llm (0.167): beats, -0.167 [-0.300, -0.067]
- ezmd-main-rag: 0.000 [0.000, 0.000] -> 0.000 [0.000, 0.000]; after - before +0.000 [+0.000, +0.000] (n=30)
  - vs docling (0.100): ties, -0.100 [-0.200, +0.000]
  - vs mineru (0.133): beats, -0.133 [-0.267, -0.033]
  - vs pymupdf4llm (0.167): beats, -0.167 [-0.300, -0.067]

## arXiv papers, source recall (share of the LaTeX source's words kept; independent witness)

- ezmd-main: 0.947 [0.915, 0.974] -> 0.947 [0.915, 0.974]; after - before -0.000 [-0.000, +0.000] (n=27)
  - vs docling (0.943): beats, +0.004 [+0.002, +0.006]
  - vs mineru (0.944): ties, +0.003 [-0.001, +0.007]
  - vs pymupdf4llm (0.935): beats, +0.011 [+0.004, +0.019]
- ezmd-main-compact: 0.707 [0.618, 0.795] -> 0.714 [0.626, 0.801]; after - before +0.007 [+0.002, +0.015] (n=27)
  - vs docling (0.943): trails, -0.228 [-0.321, -0.139]
  - vs mineru (0.944): trails, -0.229 [-0.323, -0.140]
  - vs pymupdf4llm (0.935): trails, -0.221 [-0.311, -0.135]
- ezmd-main-rag: 0.946 [0.915, 0.973] -> 0.946 [0.915, 0.973]; after - before -0.000 [-0.000, +0.000] (n=27)
  - vs docling (0.943): beats, +0.003 [+0.002, +0.005]
  - vs mineru (0.944): ties, +0.002 [-0.002, +0.007]
  - vs pymupdf4llm (0.935): beats, +0.011 [+0.004, +0.018]

## arXiv papers, text recall (share of the PDF text layer's words kept)

- ezmd-main: 0.992 [0.989, 0.995] -> 0.992 [0.989, 0.995]; after - before -0.000 [-0.000, -0.000] (n=30)
  - vs docling (0.978): beats, +0.014 [+0.008, +0.020]
  - vs mineru (0.969): beats, +0.023 [+0.017, +0.029]
  - vs pymupdf4llm (0.973): beats, +0.019 [+0.009, +0.032]
- ezmd-main-compact: 0.707 [0.599, 0.805] -> 0.723 [0.615, 0.820]; after - before +0.016 [+0.002, +0.034] (n=30)
  - vs docling (0.978): trails, -0.254 [-0.360, -0.159]
  - vs mineru (0.969): trails, -0.245 [-0.352, -0.149]
  - vs pymupdf4llm (0.973): trails, -0.249 [-0.354, -0.157]
- ezmd-main-rag: 0.992 [0.989, 0.995] -> 0.992 [0.989, 0.995]; after - before -0.000 [-0.000, +0.000] (n=30)
  - vs docling (0.978): beats, +0.014 [+0.008, +0.020]
  - vs mineru (0.969): beats, +0.023 [+0.017, +0.029]
  - vs pymupdf4llm (0.973): beats, +0.019 [+0.009, +0.032]

## arXiv papers, o200k tokens per page (lower is better)

- ezmd-main: 1158.093 [1011.962, 1321.367] -> 1140.087 [996.002, 1300.699]; after - before -18.007 [-23.150, -13.003] (n=30)
  - vs docling (930.107): trails, +209.980 [+144.815, +280.285]
  - vs mineru (1226.150): ties, -86.063 [-190.188, +3.011]
  - vs pymupdf4llm (1054.953): trails, +85.133 [+12.035, +162.029]
- ezmd-main-compact: 727.100 [569.176, 884.279] -> 736.193 [580.389, 887.116]; after - before +9.093 [-7.411, +30.023] (n=30)
  - vs docling (930.107): beats, -193.913 [-320.060, -74.038]
  - vs mineru (1226.150): beats, -489.957 [-699.722, -325.167]
  - vs pymupdf4llm (1054.953): beats, -318.760 [-476.882, -182.384]
- ezmd-main-rag: 1363.163 [1191.607, 1562.218] -> 1339.730 [1173.366, 1530.752]; after - before -23.433 [-32.314, -15.159] (n=30)
  - vs docling (930.107): trails, +409.623 [+327.098, +503.861]
  - vs mineru (1226.150): trails, +113.580 [+8.786, +218.853]
  - vs pymupdf4llm (1054.953): trails, +284.777 [+195.604, +384.644]

## Damaged arXiv papers, pages named by the pages_without_text warning (Jaccard; ezmd only)

- ezmd-main: 1.000 [1.000, 1.000] -> 1.000 [1.000, 1.000]; after - before +0.000 [+0.000, +0.000] (n=20)

## Damaged arXiv papers, a block of image-only pages: silent loss (lower is better)

- ezmd-main: 0.000 [0.000, 0.000] -> 0.000 [0.000, 0.000]; after - before +0.000 [+0.000, +0.000] (n=10)
  - vs docling (0.300): ties, -0.300 [-0.600, +0.000]
  - vs mineru (0.100): ties, -0.100 [-0.300, +0.000]
  - vs pymupdf4llm (1.000): beats, -1.000 [-1.000, -1.000]

## Damaged arXiv papers, a block of image-only pages: text recall of the intact paper

- ezmd-main: 0.767 [0.737, 0.795] -> 0.767 [0.737, 0.795]; after - before +0.000 [+0.000, +0.000] (n=10)
  - vs docling (0.962): trails, -0.195 [-0.230, -0.162]
  - vs mineru (0.967): trails, -0.200 [-0.229, -0.171]
  - vs pymupdf4llm (0.752): beats, +0.015 [+0.005, +0.022]

## Damaged arXiv papers, scanned (every page an image): silent loss (lower is better)

- ezmd-main: 0.000 [0.000, 0.000] -> 0.000 [0.000, 0.000]; after - before +0.000 [+0.000, +0.000] (n=10)
  - vs docling (0.800): beats, -0.800 [-1.000, -0.500]
  - vs mineru (0.100): ties, -0.100 [-0.300, +0.000]
  - vs pymupdf4llm (1.000): beats, -1.000 [-1.000, -1.000]

## Damaged arXiv papers, scanned: text recall of the intact paper (OCR recovers it)

- ezmd-main: 0.004 [0.003, 0.005] -> 0.004 [0.003, 0.005]; after - before +0.000 [+0.000, +0.000] (n=10)
  - vs docling (0.917): trails, -0.913 [-0.936, -0.889]
  - vs mineru (0.970): trails, -0.966 [-0.974, -0.958]
  - vs pymupdf4llm (0.000): beats, +0.004 [+0.003, +0.005]

## Damaged arXiv papers, silent loss, all kinds (lost over 5%, no warning; lower is better)

- ezmd-main: 0.033 [0.000, 0.100] -> 0.000 [0.000, 0.000]; after - before -0.033 [-0.100, +0.000] (n=30)
  - vs docling (0.400): beats, -0.400 [-0.567, -0.233]
  - vs mineru (0.067): ties, -0.067 [-0.167, +0.000]
  - vs pymupdf4llm (0.667): beats, -0.667 [-0.833, -0.500]

## Damaged arXiv papers, file truncated at 80%: silent loss (lower is better)

- ezmd-main: 0.100 [0.000, 0.300] -> 0.000 [0.000, 0.000]; after - before -0.100 [-0.300, +0.000] (n=10)
  - vs docling (0.100): ties, -0.100 [-0.300, +0.000]
  - vs mineru (0.000): ties, +0.000 [+0.000, +0.000]
  - vs pymupdf4llm (0.000): ties, +0.000 [+0.000, +0.000]

## Damaged arXiv papers, file truncated at 80%: text recall of the intact paper

- ezmd-main: 0.486 [0.195, 0.783] -> 0.486 [0.195, 0.783]; after - before +0.000 [-0.000, +0.000] (n=10)
  - vs docling (0.480): beats, +0.007 [+0.001, +0.012]
  - vs mineru (0.096): beats, +0.391 [+0.093, +0.692]
  - vs pymupdf4llm (0.585): ties, -0.098 [-0.301, +0.013]
