"""Table representation switching (part3.md section 15): pipe, KV records, HTML, sampling, CSV attachments."""

from __future__ import annotations

from render_builders import make_result, prov, span, table

from intomd.ir import Paragraph, Table, TableCell
from intomd.render import render


def _wide() -> Table:
    header = [
        "route",
        "driver",
        "trips",
        "harsh_brake",
        "harsh_accel",
        "speeding_min",
        "idle_min",
        "miles",
        "mpg",
        "incidents",
        "score",
        "trend",
    ]
    rows = [
        [str(14 + i), f"D{i}", str(50 + i), str(i % 9), "", "12", "88", f"{1000 + i:,}", "7.1", "0", "91", "down"]
        for i in range(240)
    ]
    return table([header, *rows], caption="Route-level harsh braking, Q3 2025")


def _long() -> Table:
    rows = [["id", "name", "miles"]] + [[str(i), f"n{i}", str(i * 2)] for i in range(1, 1501)]
    return table(rows, caption="Long")


def _merged() -> Table:
    cells = [
        TableCell(spans=[span("Region")], row=0, col=0, row_span=2, is_header=True),
        TableCell(spans=[span("Q3")], row=0, col=1, col_span=2, is_header=True),
        TableCell(spans=[span("North")], row=0, col=3, row_span=2, is_header=True),
        TableCell(spans=[span("Revenue")], row=1, col=1, is_header=True),
        TableCell(spans=[span("Cost")], row=1, col=2, is_header=True),
        TableCell(spans=[span("East")], row=2, col=0),
        TableCell(spans=[span("10")], row=2, col=1),
        TableCell(spans=[span("4")], row=2, col=2),
        TableCell(spans=[span("x")], row=2, col=3),
    ]
    return Table(cells=cells, n_rows=3, n_cols=4, header_rows=2, provenance=prov())


def test_wide_table_becomes_kv_records_with_csv() -> None:
    out = render(make_result([_wide()]), "full")
    body = out.body
    assert (
        "**Table 1: Route-level harsh braking, Q3 2025** (12 columns, 240 rows; full data: tables/table-01.csv)\n"
        "Columns: route, driver, trips, harsh_brake, harsh_accel, speeding_min, idle_min, miles, mpg, incidents, "
        "score, trend\n\n- route: 14 | driver: D0 | trips: 50 | harsh_brake: 0 | speeding_min: 12"
    ) in body
    assert "harsh_accel:" not in body  # empty cells are omitted from records
    assert [a.path for a in out.attachments] == ["tables/table-01.csv"]
    csv = out.attachments[0].data
    assert csv.startswith(
        b"route,driver,trips,harsh_brake,harsh_accel,speeding_min,idle_min,miles,mpg,incidents,"
        b'score,trend\r\n14,D0,50,0,,12,88,"1,000",7.1,0,91,down\r\n'
    )
    assert out.frontmatter["exports"] == {"tables": ["tables/table-01.csv"]}


def test_long_table_sampled_with_summary_and_warning() -> None:
    out = render(make_result([_long()]), "full")
    body = out.body
    assert (
        "- id: 20 | name: n20 | miles: 40\n<!-- intomd: 1,475 rows omitted; full data in tables/table-01.csv -->\n"
        "- id: 1496 | name: n1496 | miles: 2992" in body
    )
    # the first column is the record label, so only `miles` is summarized
    assert body.endswith("\n\nSummary: 1,500 rows; miles min 2, max 3,000, sum 2,251,500\n")
    assert "table_sampled" in out.frontmatter["warnings"]  # type: ignore[operator]
    assert out.frontmatter["truncated"] is True and out.truncated
    assert out.attachments[0].data.count(b"\r\n") == 1501


def test_compact_sampling_uses_prose_note() -> None:
    rows = [["k", "v"]] + [[f"k{i}", str(i)] for i in range(300)]
    body = render(make_result([table(rows)]), "compact").body
    assert "(275 rows omitted; full data in tables/table-01.csv)" in body
    assert "<!-- intomd" not in body


def test_merged_cells_html_in_full_flattened_elsewhere() -> None:
    res = make_result([_merged()])
    full = render(res, "full")
    assert (
        '<table>\n<thead>\n<tr><th rowspan="2">Region</th><th colspan="2">Q3</th><th rowspan="2">North</th></tr>\n'
        "<tr><th>Revenue</th><th>Cost</th></tr>\n</thead>\n<tbody>\n<tr><td>East</td><td>10</td><td>4</td>"
        "<td>x</td></tr>\n</tbody>\n</table>"
    ) in full.body
    assert "merged_cells_flattened" not in full.frontmatter["warnings"]  # type: ignore[operator]
    compact = render(res, "compact")
    assert "| Region | Q3 / Revenue | Q3 / Cost | North |\n|---|---:|---:|---|\n| East | 10 | 4 | x |" in compact.body
    assert "merged_cells_flattened" in render(res, "agent").frontmatter["warnings"]  # type: ignore[operator]


def test_pipe_table_legend_escaping_and_numeric_alignment() -> None:
    rows = [["a", "b", "c", "d", "e"], ["x|y", "1", "(12.5)", "$1,099.00", "line1\nline2"]]
    body = render(make_result([table(rows)]), "full").body
    assert "**Table 1**\nColumns: a, b, c, d, e\n\n| a | b | c | d | e |\n|---|---:|---:|---:|---|\n" in body
    assert "| x\\|y | 1 | (12.5) | $1,099.00 | line1<br>line2 |" in body


def test_header_inference_and_synthesis() -> None:
    inferred = render(make_result([table([["Name", "Qty"], ["a", "1"], ["b", "2"]], header_rows=0)]), "full").body
    assert "| Name | Qty |\n|---|---:|\n| a | 1 |" in inferred
    synth = render(make_result([table([["1", "2"], ["3", "4"]], header_rows=0)]), "full").body
    assert "**Table 1**\n<!-- intomd: header synthesized -->\n\n| col_1 | col_2 |" in synth


def test_table_caption_from_figure_and_rag_atomic_rows() -> None:
    res = make_result([table([["h", "v"], *[[f"r{i}", str(i)] for i in range(60)]])])
    rag = render(res, "rag").body
    assert "Columns: h, v" in rag and "| h |" not in rag  # 60 rows > 50: KV records in rag


def test_footnote_in_table_cell_defined_after_table() -> None:
    cells = [
        TableCell(spans=[span("h")], row=0, col=0, is_header=True),
        TableCell(spans=[span("v"), span("1", footnote="fn")], row=1, col=0),
    ]
    from intomd.ir import Footnote

    res = make_result(
        [
            Table(cells=cells, n_rows=2, n_cols=1, header_rows=1, provenance=prov()),
            Paragraph(spans=[span("After.")], provenance=prov()),
            Footnote(id="fn", marker="1", spans=[span("Cell note.")], provenance=prov()),
        ]
    )
    body = render(res, "full").body
    assert "| v[^1] |\n\n[^1]: Cell note.\n\nAfter." in body
