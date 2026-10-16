# ezmd rc5 vs 2026-10-13

## ezmd fixtures (self-graded, supporting evidence only): archives

- ezmd: 0.859 [0.577, 1.000] -> 0.859 [0.577, 1.000]; after - before +0.000 [+0.000, +0.000] (n=6)
- ezmd-docs: 0.859 [0.577, 1.000] -> 0.859 [0.577, 1.000]; after - before +0.000 [+0.000, +0.000] (n=6)

## ezmd fixtures (self-graded, supporting evidence only): code

- ezmd: 0.729 [0.539, 0.911] -> 0.729 [0.539, 0.911]; after - before +0.000 [+0.000, +0.000] (n=11)
- ezmd-docs: 0.729 [0.539, 0.911] -> 0.729 [0.539, 0.911]; after - before +0.000 [+0.000, +0.000] (n=11)

## ezmd fixtures (self-graded, supporting evidence only): comms

- ezmd: 1.000 [1.000, 1.000] -> 1.000 [1.000, 1.000]; after - before +0.000 [+0.000, +0.000] (n=9)
- ezmd-docs: 1.000 [0.999, 1.000] -> 1.000 [0.999, 1.000]; after - before +0.000 [+0.000, +0.000] (n=9)

## ezmd fixtures (self-graded, supporting evidence only): data

- ezmd: 0.941 [0.827, 1.000] -> 0.941 [0.827, 1.000]; after - before +0.000 [+0.000, +0.000] (n=18)
- ezmd-docs: 0.941 [0.827, 1.000] -> 0.941 [0.827, 1.000]; after - before +0.000 [+0.000, +0.000] (n=18)

## ezmd fixtures (self-graded, supporting evidence only): ebooks

- ezmd: 1.000 [1.000, 1.000] -> 1.000 [1.000, 1.000]; after - before +0.000 [+0.000, +0.000] (n=5)
- ezmd-docs: 1.000 [1.000, 1.000] -> 1.000 [1.000, 1.000]; after - before +0.000 [+0.000, +0.000] (n=5)

## ezmd fixtures (self-graded, supporting evidence only): edgar

- ezmd: 0.749 [0.273, 1.000] -> 0.749 [0.273, 1.000]; after - before n/a
- ezmd-docs: 0.749 [0.273, 1.000] -> 0.749 [0.273, 1.000]; after - before n/a

## ezmd fixtures (self-graded, supporting evidence only): office

- ezmd: 1.000 [1.000, 1.000] -> 1.000 [1.000, 1.000]; after - before +0.000 [+0.000, +0.000] (n=12)
- ezmd-docs: 1.000 [1.000, 1.000] -> 1.000 [1.000, 1.000]; after - before +0.000 [+0.000, +0.000] (n=12)

## ezmd fixtures (self-graded, supporting evidence only): pdf

- ezmd: 1.000 [1.000, 1.000] -> 1.000 [1.000, 1.000]; after - before +0.000 [+0.000, +0.000] (n=10)
- ezmd-docs: 0.928 [0.804, 1.000] -> 0.928 [0.804, 1.000]; after - before +0.000 [+0.000, +0.000] (n=10)

## ezmd fixtures (self-graded, supporting evidence only): text

- ezmd: 1.000 [1.000, 1.000] -> 1.000 [1.000, 1.000]; after - before +0.000 [+0.000, +0.000] (n=6)
- ezmd-docs: 1.000 [1.000, 1.000] -> 1.000 [1.000, 1.000]; after - before +0.000 [+0.000, +0.000] (n=6)

## ezmd fixtures (self-graded, supporting evidence only): web

- ezmd: 0.987 [0.969, 1.000] -> 0.987 [0.969, 1.000]; after - before +0.000 [+0.000, +0.000] (n=14)
- ezmd-docs: 0.987 [0.969, 1.000] -> 0.987 [0.969, 1.000]; after - before +0.000 [+0.000, +0.000] (n=14)

## PDF, OmniDocBench display formulas (1 - edit distance; CDM off)

- ezmd: 0.093 [0.046, 0.161] -> 0.104 [0.062, 0.159]; after - before +0.011 [-0.011, +0.036] (n=17)
  - vs pymupdf4llm (0.029): beats, +0.075 [+0.039, +0.115]
  - vs unstructured (0.116): ties, -0.012 [-0.055, +0.031]
- ezmd-docs: 0.047 [0.028, 0.068] -> 0.047 [0.028, 0.068]; after - before +0.000 [+0.000, +0.000] (n=17)
  - vs pymupdf4llm (0.029): ties, +0.017 [-0.014, +0.048]
  - vs unstructured (0.116): trails, -0.069 [-0.143, -0.003]

## PDF, OmniDocBench reading order (1 - edit distance)

- ezmd: 0.426 [0.383, 0.467] -> 0.537 [0.492, 0.579]; after - before +0.111 [+0.076, +0.146] (n=295)
  - vs pymupdf4llm (0.553): ties, -0.016 [-0.048, +0.017]
  - vs unstructured (0.613): trails, -0.076 [-0.111, -0.042]
- ezmd-docs: 0.621 [0.579, 0.660] -> 0.622 [0.581, 0.661]; after - before +0.001 [-0.003, +0.005] (n=295)
  - vs pymupdf4llm (0.553): beats, +0.069 [+0.038, +0.102]
  - vs unstructured (0.613): ties, +0.009 [-0.025, +0.042]

## PDF, OmniDocBench tables (TEDS)

- ezmd: 0.150 [0.100, 0.203] -> 0.179 [0.129, 0.233]; after - before +0.029 [+0.010, +0.051] (n=129)
  - vs pymupdf4llm (0.433): trails, -0.254 [-0.321, -0.189]
  - vs unstructured (0.002): beats, +0.177 [+0.127, +0.226]
- ezmd-docs: 0.421 [0.347, 0.495] -> 0.421 [0.347, 0.495]; after - before +0.000 [+0.000, +0.000] (n=129)
  - vs pymupdf4llm (0.433): ties, -0.012 [-0.068, +0.039]
  - vs unstructured (0.002): beats, +0.419 [+0.344, +0.497]

## PDF, OmniDocBench text (1 - edit distance)

- ezmd: 0.286 [0.245, 0.328] -> 0.498 [0.455, 0.543]; after - before +0.213 [+0.175, +0.252] (n=278)
  - vs pymupdf4llm (0.620): trails, -0.122 [-0.150, -0.093]
  - vs unstructured (0.676): trails, -0.177 [-0.211, -0.146]
- ezmd-docs: 0.666 [0.618, 0.712] -> 0.666 [0.618, 0.712]; after - before -0.000 [-0.002, +0.002] (n=278)
  - vs pymupdf4llm (0.620): beats, +0.046 [+0.016, +0.076]
  - vs unstructured (0.676): ties, -0.010 [-0.036, +0.016]

## PDF, olmOCR-Bench (unit-test pass rate)

- ezmd: 0.277 [0.262, 0.292] -> 0.335 [0.318, 0.352]; after - before +0.061 [+0.030, +0.092] (n=336)
  - vs pymupdf4llm (0.333): ties, +0.005 [-0.022, +0.031]
  - vs unstructured (0.313): ties, +0.023 [-0.006, +0.050]
- ezmd-docs: 0.480 [0.464, 0.494] -> 0.480 [0.464, 0.494]; after - before +0.000 [+0.000, +0.000] (n=336)
  - vs pymupdf4llm (0.333): beats, +0.141 [+0.113, +0.168]
  - vs unstructured (0.313): beats, +0.159 [+0.122, +0.196]
