import json
import logging
import re
import threading
import time
from html.parser import HTMLParser
from urllib.parse import urlparse
from urllib.request import Request, urlopen

POINTS_BY_DIFFICULTY = {
    "EASY": 1,
    "MEDIUM": 2,
    "HARD": 4,
}

LEETCODE_GRAPHQL_API = "https://leetcode.com/graphql"
LEETCODE_QUERY = """
query questionData($titleSlug: String!) {
  question(titleSlug: $titleSlug) {
    title
    titleSlug
    difficulty
  }
}
"""

USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36"
METADATA_CACHE_TTL_SECONDS = 6 * 60 * 60
_METADATA_CACHE = {}
_CACHE_LOCK = threading.Lock()
_SLUG_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def _normalise_metadata(title, difficulty):
    title = " ".join(str(title or "").split())
    difficulty = str(difficulty or "").strip().upper()
    if not title or difficulty not in POINTS_BY_DIFFICULTY:
        return None
    return {
        "title": title,
        "difficulty": difficulty,
        "points": POINTS_BY_DIFFICULTY[difficulty],
    }


def _cache_get(key):
    now = time.monotonic()
    with _CACHE_LOCK:
        cached = _METADATA_CACHE.get(key)
        if not cached:
            return None
        expires_at, metadata = cached
        if expires_at <= now:
            _METADATA_CACHE.pop(key, None)
            return None
        return metadata.copy()


def _cache_set(key, metadata):
    with _CACHE_LOCK:
        _METADATA_CACHE[key] = (
            time.monotonic() + METADATA_CACHE_TTL_SECONDS,
            metadata.copy(),
        )


def lookup_leetcode_metadata(problem_slug):
    slug = str(problem_slug or "").strip().lower()
    if not _SLUG_PATTERN.fullmatch(slug):
        return None

    cache_key = ("leetcode", slug)
    cached = _cache_get(cache_key)
    if cached:
        return cached

    payload = json.dumps({
        "query": LEETCODE_QUERY,
        "variables": {"titleSlug": slug},
    }).encode("utf-8")
    request = Request(
        LEETCODE_GRAPHQL_API,
        data=payload,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Origin": "https://leetcode.com",
            "Referer": f"https://leetcode.com/problems/{slug}/",
            "User-Agent": USER_AGENT,
        },
    )

    try:
        with urlopen(request, timeout=12) as response:
            body = json.loads(response.read().decode("utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        logging.exception("Failed to fetch LeetCode metadata for %s", slug)
        return None

    if not isinstance(body, dict):
        logging.warning("LeetCode returned an unexpected response for %s", slug)
        return None

    if body.get("errors"):
        logging.warning("LeetCode returned GraphQL errors for %s: %s", slug, body["errors"])
        return None

    question = (body.get("data") or {}).get("question") or {}
    if not isinstance(question, dict):
        return None
    returned_slug = str(question.get("titleSlug") or "").strip().lower()
    if returned_slug != slug:
        logging.warning(
            "LeetCode slug validation failed: requested=%s returned=%s",
            slug,
            returned_slug,
        )
        return None

    metadata = _normalise_metadata(question.get("title"), question.get("difficulty"))
    if not metadata:
        logging.warning("LeetCode returned incomplete metadata for %s", slug)
        return None

    _cache_set(cache_key, metadata)
    return metadata.copy()


class _NeetCodePageParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.canonical_url = None
        self.difficulty_pills = []
        self.problem_titles = []
        self._active_capture = None

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        classes = (attributes.get("class") or "").split()

        if tag == "link" and "canonical" in (attributes.get("rel") or "").lower().split():
            self.canonical_url = attributes.get("href") or self.canonical_url

        if self._active_capture is not None:
            self._active_capture["depth"] += 1
            return

        if tag == "span" and "difficulty-pill" in classes:
            self._active_capture = {
                "kind": "difficulty",
                "tag": tag,
                "depth": 1,
                "classes": classes,
                "parts": [],
            }
        elif tag == "h1" and "problem-title" in classes:
            self._active_capture = {
                "kind": "title",
                "tag": tag,
                "depth": 1,
                "classes": classes,
                "parts": [],
            }

    def handle_data(self, data):
        if self._active_capture is not None:
            self._active_capture["parts"].append(data)

    def handle_endtag(self, tag):
        if self._active_capture is None:
            return

        self._active_capture["depth"] -= 1
        if self._active_capture["depth"] > 0:
            return

        capture = self._active_capture
        self._active_capture = None
        value = " ".join("".join(capture["parts"]).split())

        if capture["kind"] == "difficulty":
            self.difficulty_pills.append({
                "classes": capture["classes"],
                "text": value,
            })
        else:
            self.problem_titles.append(value)


def parse_neetcode_html(raw_html, requested_slug):
    slug = str(requested_slug or "").strip().lower()
    if not _SLUG_PATTERN.fullmatch(slug):
        return None

    parser = _NeetCodePageParser()
    parser.feed(raw_html or "")
    parser.close()

    if len(parser.difficulty_pills) != 1 or len(parser.problem_titles) != 1:
        return None
    if not parser.canonical_url:
        return None

    canonical = urlparse(parser.canonical_url)
    host = (canonical.hostname or "").lower()
    path_parts = [part for part in canonical.path.split("/") if part]
    if host not in {"neetcode.io", "www.neetcode.io"}:
        return None
    if len(path_parts) < 3 or path_parts[0] != "problems":
        return None
    if path_parts[1].lower() != slug or path_parts[2].lower() != "question":
        return None

    pill = parser.difficulty_pills[0]
    class_difficulties = {
        class_name.lower()
        for class_name in pill["classes"]
        if class_name.lower() in {"easy", "medium", "hard"}
    }
    text_difficulty = pill["text"].strip().upper()

    if len(class_difficulties) != 1 or text_difficulty not in POINTS_BY_DIFFICULTY:
        return None

    class_difficulty = next(iter(class_difficulties)).upper()
    if class_difficulty != text_difficulty:
        return None

    return _normalise_metadata(parser.problem_titles[0], text_difficulty)


def lookup_neetcode_metadata(problem_slug):
    slug = str(problem_slug or "").strip().lower()
    if not _SLUG_PATTERN.fullmatch(slug):
        return None

    cache_key = ("neetcode", slug)
    cached = _cache_get(cache_key)
    if cached:
        return cached

    url = f"https://neetcode.io/problems/{slug}/question"
    request = Request(
        url,
        headers={
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Language": "en-US,en;q=0.9",
            "User-Agent": USER_AGENT,
        },
    )

    try:
        with urlopen(request, timeout=12) as response:
            raw_html = response.read().decode(
                response.headers.get_content_charset() or "utf-8",
                errors="replace",
            )
    except (OSError, UnicodeDecodeError):
        logging.exception("Failed to fetch NeetCode metadata for %s", slug)
        return None

    metadata = parse_neetcode_html(raw_html, slug)
    if not metadata:
        logging.warning(
            "NeetCode metadata validation failed for %s; requiring manual difficulty selection.",
            slug,
        )
        return None

    _cache_set(cache_key, metadata)
    return metadata.copy()


def lookup_problem_metadata(problem_slug):
    value = str(problem_slug or "").strip()
    if ":" in value:
        platform, raw_slug = value.split(":", 1)
    else:
        platform, raw_slug = "leetcode", value

    platform = platform.lower().strip()
    if platform == "leetcode":
        return lookup_leetcode_metadata(raw_slug)
    if platform == "neetcode":
        return lookup_neetcode_metadata(raw_slug)
    return None
