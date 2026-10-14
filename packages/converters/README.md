# ezmd-converters

The built-in converter families for [ezmd](https://pypi.org/project/ezmd/): PDF, Office documents, web
pages, data files, code, email, ebooks, archives, SEC EDGAR filings, plain text and Markdown.

You normally don't install this package directly; `pip install ezmd` pulls it in. Optional engines are
extras here, and `ezmd` forwards them under the same names:

- `docs`: Docling layout analysis for PDFs (large; pulls torch).
- `data`: Parquet files (pyarrow).
- `7z`: 7z archives (py7zr).
- `nonfree`: Outlook `.msg` via extract-msg (GPL-3.0). Never part of `all`.

Third-party converters plug in through the `ezmd.converters` entry point group; see
[writing a converter plugin](https://github.com/larpey/ezmd/blob/main/docs/plugins.md).

The converter matrix, with engines, extras and fixture thresholds, is at
<https://github.com/larpey/ezmd/blob/main/docs/converters/README.md>.
