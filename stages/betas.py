"""Discover beta firmware from ipsw.dev.

Apple publishes no API for beta IPSWs. ipsw.dev serves a server-rendered
listing per device, including the real Apple CDN download URL, so we scrape it
with html.parser (no regex). Device models and the current *stable* version
come from the existing stable source (ipsw.me, via stages.discover).

A firmware is treated as a beta when it is a pre-release build (its ipsw.dev
label carries a beta/RC/seed marker) whose version is strictly *ahead of* the
latest stable version of its family. That captures both:

  * next-major betas      e.g. 27.0 beta while stable is 26.5
  * same-major next-minor  e.g. 26.6 beta while stable is 26.5

Betas keep their plain numeric version (e.g. "27.0") and the iOS/mac group, so
the frontend lists and diffs them like any other build; they are tagged
``beta: True`` downstream so pruning can prefer the stable build of the same
version once it ships. ipsw.dev exposes no md5/sha1/sha256, which betas lack.
"""

import json
import time
import urllib.request
from html.parser import HTMLParser
from pathlib import Path

from stages.discover import (
    fetch_with_cache,
    fetch_ios_firmwares,
    fetch_mac_firmwares,
)

IPSW_DEV = "https://ipsw.dev"
USER_AGENT = "Mozilla/5.0 (entdb-indexer)"

# Tokens that mark a version label as pre-release rather than a shipped build.
PRERELEASE_MARKERS = ("beta", "rc", "seed", "gm")


def _fetch_cached(url: str, cache_dir: Path, cache_name: str) -> str:
    """Fetch ``url`` with a 24h on-disk cache, returning decoded text.

    ipsw.dev requires a browser-like User-Agent, so this does not reuse
    stages.discover.fetch_with_cache (which targets the ipsw.me JSON API).
    """
    cache_dir.mkdir(parents=True, exist_ok=True)
    local = cache_dir / cache_name
    if local.exists() and local.is_file():
        if local.stat().st_mtime + 86400 > time.time():
            return local.read_bytes().decode("utf-8", "replace")

    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    buf = urllib.request.urlopen(req).read()
    local.write_bytes(buf)
    return buf.decode("utf-8", "replace")


class _FirmwareRowParser(HTMLParser):
    """Collect the text of each cell of every ``<tr class="firmware">`` row."""

    def __init__(self) -> None:
        super().__init__()
        self.rows: list[list[str]] = []
        self._in_row = False
        self._in_cell = False
        self._cells: list[str] = []
        self._buf: list[str] = []

    def handle_starttag(self, tag, attrs):
        d = dict(attrs)
        if tag == "tr" and "firmware" in (d.get("class") or "").split():
            self._in_row = True
            self._cells = []
        elif tag == "td" and self._in_row:
            self._in_cell = True
            self._buf = []

    def handle_data(self, data):
        if self._in_cell:
            text = data.strip()
            if text:
                self._buf.append(text)

    def handle_endtag(self, tag):
        if tag == "td" and self._in_cell:
            self._in_cell = False
            self._cells.append(" ".join(self._buf))
        elif tag == "tr" and self._in_row:
            self._in_row = False
            if self._cells:
                self.rows.append(self._cells)


class _DownloadLinkParser(HTMLParser):
    """Capture the first ``.ipsw`` URL from any tag attribute on a page."""

    def __init__(self) -> None:
        super().__init__()
        self.url: str | None = None

    def handle_starttag(self, tag, attrs):
        if self.url:
            return
        for _, value in attrs:
            if value and value.startswith("http") and value.endswith(".ipsw"):
                self.url = value
                return


def _version_tuple(version: str) -> tuple[int, ...]:
    return tuple(int(p) for p in version.split(".") if p.isdigit())


def _minor_key(version: str) -> str:
    return ".".join(version.split(".")[:2])


def _parse_prerelease_rows(html_text: str) -> list[dict]:
    """Return pre-release firmware rows parsed from one ipsw.dev device page.

    A row's first cell reads like ``"27.0 beta 24A5355q"`` / ``"26.5 RC 2 23F77"``
    / ``"26.5 23F66"`` — version first, build last, markers in between. Only rows
    whose markers identify a pre-release build are returned.
    """
    parser = _FirmwareRowParser()
    parser.feed(html_text)

    out = []
    for cells in parser.rows:
        tokens = cells[0].split()
        if len(tokens) < 2:
            continue
        version, build = tokens[0], tokens[-1]
        if not version.split(".")[0].isdigit():
            continue
        markers = {t.lower() for t in tokens[1:-1]}
        if not markers & set(PRERELEASE_MARKERS):
            continue
        out.append(
            {
                "version": version,
                "build": build,
                "releasedate": cells[2].strip() if len(cells) > 2 else "",
            }
        )
    return out


def _download_url(model: str, build: str, cache_dir: Path) -> str | None:
    html_text = _fetch_cached(
        f"{IPSW_DEV}/download/{model}/{build}",
        cache_dir,
        f"ipswdev-dl-{model}-{build}.html",
    )
    parser = _DownloadLinkParser()
    parser.feed(html_text)
    return parser.url


def _discover(
    models: list[str], latest_stable: tuple[int, ...], cache_dir: Path
) -> list[dict]:
    # Collect pre-release rows ahead of the latest stable, across all devices,
    # deduped by build id. A build may appear on many devices; keep the first
    # device that lists it so we fetch only one download page per build.
    by_build: dict[str, dict] = {}
    for model in models:
        try:
            html_text = _fetch_cached(
                f"{IPSW_DEV}/{model}", cache_dir, f"ipswdev-{model}.html"
            )
        except Exception:
            continue
        for row in _parse_prerelease_rows(html_text):
            if _version_tuple(row["version"]) <= latest_stable:
                continue
            if row["build"] not in by_build:
                by_build[row["build"]] = {**row, "model": model}

    # Keep only the latest seed of each minor (e.g. one 27.0 and one 27.1).
    # Seeds within a beta line share a build train, so the largest build id is
    # the newest seed.
    winners: dict[str, dict] = {}
    for rec in by_build.values():
        key = _minor_key(rec["version"])
        cur = winners.get(key)
        if cur is None or rec["build"] > cur["build"]:
            winners[key] = rec

    result = []
    for rec in winners.values():
        url = _download_url(rec["model"], rec["build"], cache_dir)
        if not url:
            continue
        result.append(
            {
                "url": url,
                "model": rec["model"],
                "version": rec["version"],
                "build": rec["build"],
                "releasedate": rec["releasedate"],
                "beta": True,
            }
        )

    result.sort(key=lambda fw: _version_tuple(fw["version"]), reverse=True)
    return result


def _latest_stable_version(stable: list[dict]) -> tuple[int, ...] | None:
    best = None
    for fw in stable:
        version = fw.get("version")
        if not version:
            continue
        t = _version_tuple(version)
        if best is None or t > best:
            best = t
    return best


def _devices(cache_dir: Path) -> list[dict]:
    return json.loads(
        fetch_with_cache("https://api.ipsw.me/v4/devices", cache_dir, "devices.json")
    )


def fetch_ios_betas(cache_dir: Path) -> list[dict]:
    latest_stable = _latest_stable_version(fetch_ios_firmwares(cache_dir))
    if latest_stable is None:
        return []
    models = [d["identifier"] for d in _devices(cache_dir) if d["identifier"].startswith("iPhone")]
    return _discover(models, latest_stable, cache_dir)


def fetch_mac_betas(cache_dir: Path) -> list[dict]:
    latest_stable = _latest_stable_version(fetch_mac_firmwares(cache_dir))
    if latest_stable is None:
        return []
    models = [d["identifier"] for d in _devices(cache_dir) if d["identifier"].startswith("Mac")]
    return _discover(models, latest_stable, cache_dir)
