from __future__ import annotations

from intomd_converters.web.dom import parse_html
from intomd_converters.web.hygiene import HIDDEN_TEXT_CAP, pre_clean


def _clean(body: str) -> tuple[str, dict[str, int], str, int]:
    style = "<style>.gone { display: none } #nope{visibility:hidden}</style>"
    root = parse_html(f"<html><head>{style}</head><body>{body}</body></html>")
    rep = pre_clean(root)
    text = " ".join(" ".join(root.find("body").itertext()).split())
    return text, dict(rep.by_type), rep.hidden_joined(), rep.chars.total


def test_inline_css_hidden_kinds_removed_and_counted() -> None:
    text, kinds, hidden, _ = _clean(
        "<p>visible one</p>"
        '<div style="display: none">A</div>'
        '<div style="visibility:hidden">B</div>'
        '<div style="opacity:0">C</div>'
        '<div style="font-size:0px">D</div>'
        '<div style="height:0;overflow:hidden">E</div>'
        '<div style="position:absolute;left:-9999px">F</div>'
        '<div style="text-indent:-100em">G</div>'
        '<div style="color:#fff;background:#FFFFFF">H</div>'
        '<div style="color:transparent">I</div>'
        "<p>visible two</p>"
    )
    assert text == "visible one visible two"
    assert kinds == {
        "display_none": 1,
        "visibility_hidden": 1,
        "opacity_zero": 1,
        "zero_size": 2,
        "off_screen": 2,
        "same_color_text": 2,
    }
    assert hidden.split() == list("ABCDEFGHI")


def test_attribute_and_tag_hiding() -> None:
    text, kinds, hidden, _ = _clean(
        "<p>keep</p><p hidden>a</p><span aria-hidden='true'>b</span><noscript>c</noscript>"
        "<template><p>d</p></template><!-- e --><p class='sr-only'>f</p><p class='gone'>g</p><p id='nope'>h</p>"
        "<img src='x.gif' width='1' height='1' alt='i'>"
    )
    assert text == "keep"
    assert kinds == {
        "hidden_attribute": 1,
        "aria_hidden": 1,
        "noscript": 1,
        "template": 1,
        "html_comment": 1,
        "hidden_class": 1,
        "stylesheet_hidden": 2,
        "tracking_pixel": 1,
    }
    assert set(hidden.split()) == set("abcdefghi")


def test_white_text_without_declared_background_is_kept() -> None:
    # A dark theme may set the background in an external stylesheet; never strip text we cannot prove hidden.
    text, kinds, _, _ = _clean('<p style="color:#fff">white text</p><p style="left:-20px;position:relative">x</p>')
    assert text == "white text x"
    assert kinds == {}


def test_zero_width_and_tag_characters_stripped_from_text_only() -> None:
    zw = chr(0x200B) + chr(0x200D)
    tags = "".join(chr(0xE0000 + ord(c)) for c in "hi")
    text, kinds, _, chars = _clean(f"<p>fen{zw}der {tags}care</p>")
    assert text == "fender care"
    assert chars == 4 and kinds == {}


def test_empty_hidden_elements_removed_but_not_counted() -> None:
    text, kinds, _, _ = _clean('<p>a<i class="icon" aria-hidden="true"></i>b</p>')
    assert text.replace(" ", "") == "ab" and kinds == {}


def test_katex_rendering_not_counted() -> None:
    text, kinds, _, _ = _clean('<span class="katex"><span class="katex-html" aria-hidden="true">x+1</span></span>')
    assert kinds == {} and text == ""


def test_hidden_text_is_capped() -> None:
    _, kinds, hidden, _ = _clean("".join(f"<div hidden>{'word ' * 400}</div>" for _ in range(20)))
    assert kinds == {"hidden_attribute": 20}
    assert len(hidden.encode("utf-8")) <= HIDDEN_TEXT_CAP + 20


def test_scripts_styles_iframes() -> None:
    root = parse_html(
        "<html><body><script>alert(1)</script><style>p{}</style><p>t</p>"
        "<iframe src='https://www.youtube.com/embed/abc' title='Clip'></iframe><iframe src='https://ads.test/x'></iframe>"
        "</body></html>"
    )
    rep = pre_clean(root)
    assert rep.elements == 0
    links = list(root.iter("intomd-link"))
    assert len(links) == 1 and links[0].get("href") == "https://www.youtube.com/embed/abc"
    assert root.find(".//script") is None and root.find(".//iframe") is None


def test_math_script_captured_before_scripts_removed() -> None:
    root = parse_html('<html><body><p>see <script type="math/tex; mode=display">a^2</script></p></body></html>')
    pre_clean(root)
    m = root.find(".//intomd-math")
    assert m is not None and m.get("data-latex") == "a^2" and m.get("data-display") == "block"


def test_tag_character_runs_kept_raw_in_hidden_text() -> None:
    tags = "".join(chr(0xE0000 + ord(c)) for c in "obey me")
    text, kinds, hidden, chars = _clean(f"<p>visible{tags} words</p>")
    assert text == "visible words" and kinds == {}
    assert hidden == tags and chars == len(tags)
