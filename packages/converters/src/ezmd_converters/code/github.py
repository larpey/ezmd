"""GitHub repository URL parsing (docs/spec/part2.md 8a, 8c step 1).

`https://github.com/<o>/<r>` and `https://github.com/<o>/<r>/tree/<ref>[/<path>]` map to the codeload tarball
`https://codeload.github.com/<o>/<r>/tar.gz/<ref>` (ref `HEAD` when absent). The converter never fetches: it raises
`FetchRequired` and the pipeline fetches through netguard, then converts the downloaded tarball.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import unquote, urlsplit

__all__ = ["RepoUrl", "is_codeload_url", "parse_repo_url"]

_NAME = r"[A-Za-z0-9](?:[A-Za-z0-9._-]{0,99})"
_RESERVED_OWNERS = frozenset(
    {"orgs", "settings", "marketplace", "topics", "explore", "features", "login", "sponsors", "about", "apps"}
)
_REPO_PATH = re.compile(rf"^/(?P<o>{_NAME})/(?P<r>{_NAME})(?:/tree/(?P<rest>.+?))?/?$")
_CODELOAD_PATH = re.compile(rf"^/(?P<o>{_NAME})/(?P<r>{_NAME})/(?:tar\.gz|legacy\.tar\.gz|zip)/(?P<ref>.+)$")
_SAFE_REF = re.compile(r"^[A-Za-z0-9._/-]{1,200}$")


@dataclass(frozen=True, slots=True)
class RepoUrl:
    owner: str
    repo: str
    ref: str | None
    subpath: str | None

    @property
    def tarball_url(self) -> str:
        return f"https://codeload.github.com/{self.owner}/{self.repo}/tar.gz/{self.ref or 'HEAD'}"

    @property
    def display(self) -> str:
        return f"{self.owner}/{self.repo}"


def parse_repo_url(url: str | None) -> RepoUrl | None:
    """A github.com repository or tree URL, or None. Blob, pull, and issue URLs are not repositories."""
    if not url:
        return None
    try:
        parts = urlsplit(url.strip())
    except ValueError:
        return None
    if parts.scheme not in ("https", "http") or (parts.hostname or "").lower() not in ("github.com", "www.github.com"):
        return None
    m = _REPO_PATH.match(unquote(parts.path))
    if m is None or m.group("o").lower() in _RESERVED_OWNERS:
        return None
    rest = m.group("rest")
    ref: str | None = None
    subpath: str | None = None
    if rest:
        ref, _, sub = rest.partition("/")
        subpath = sub.strip("/") or None
        if not _SAFE_REF.match(ref) or ".." in ref.split("/"):
            return None
        if subpath is not None and ".." in subpath.split("/"):
            return None
    repo = m.group("r").removesuffix(".git")
    if not repo:
        return None
    return RepoUrl(owner=m.group("o"), repo=repo, ref=ref, subpath=subpath)


def is_codeload_url(url: str | None) -> RepoUrl | None:
    """The repository behind a `codeload.github.com` archive URL (the body the pipeline fetched), or None."""
    if not url:
        return None
    try:
        parts = urlsplit(url.strip())
    except ValueError:
        return None
    if (parts.hostname or "").lower() != "codeload.github.com":
        return None
    m = _CODELOAD_PATH.match(unquote(parts.path))
    if m is None:
        return None
    return RepoUrl(owner=m.group("o"), repo=m.group("r"), ref=m.group("ref"), subpath=None)
