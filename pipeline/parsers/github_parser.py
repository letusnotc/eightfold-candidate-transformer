"""
GitHub Parser — fetches public profile data and repo language stats.

Uses the public GitHub REST API (no auth token required for public profiles).
Extracts: name, bio, location, blog, email, company, top languages, skills.
"""

from __future__ import annotations

import base64
import logging
import re
from collections import Counter
from typing import Optional

logger = logging.getLogger(__name__)

try:
    import httpx
    _HTTPX_AVAILABLE = True
except ImportError:
    _HTTPX_AVAILABLE = False
    logger.warning("httpx not installed — GitHub parser will not function")

_GITHUB_URL_RE = re.compile(r"github\.com/([A-Za-z0-9\-]+)(?:/.*)?$")
_API_BASE = "https://api.github.com"
_TIMEOUT = 10.0


def _build_headers() -> dict:
    import os
    headers = {
        "User-Agent": "eightfold-transformer/1.0",
        "Accept": "application/vnd.github+json",
    }
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers

_README_EMAIL_RE = re.compile(r"[\w.+\-]+@[\w\-]+\.[a-zA-Z]{2,}")
_README_URL_RE   = re.compile(r"https?://[^\s\"\'\)\]>]+")

# Known link classifiers — maps domain fragment → canonical key
_LINK_CLASSIFIERS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"linkedin\.com/in/",      re.I), "linkedin"),
    (re.compile(r"github\.com/",           re.I), "github"),
    (re.compile(r"twitter\.com/|x\.com/",  re.I), "twitter"),
    (re.compile(r"portfolio|personal|me\.", re.I), "portfolio"),
]


def _classify_url(url: str) -> str:
    """Return a semantic key for a URL, or 'other' if unknown."""
    for pattern, key in _LINK_CLASSIFIERS:
        if pattern.search(url):
            return key
    return "other"


def _parse_readme(readme_text: str) -> dict:
    """
    Generically extract fields from any GitHub profile README.
    No platform-specific hardcoding beyond the well-known canonical ones
    (linkedin, github). Everything else lands in links_other.
    """
    out: dict = {}

    # Email — mailto: first (most reliable), then bare address
    mailto_m = re.search(r"mailto:([\w.+\-]+@[\w\-]+\.[a-zA-Z]{2,})", readme_text)
    email_m  = mailto_m or _README_EMAIL_RE.search(readme_text)
    if email_m:
        raw = email_m.group(1) if mailto_m else email_m.group(0)
        out["emails"] = [raw.lower().strip()]

    # All URLs — classify into known keys or collect as other
    links: dict[str, list[str]] = {}
    for url in _README_URL_RE.findall(readme_text):
        # Strip trailing punctuation artifacts
        url = url.rstrip(".,;)")
        # Skip image/badge/stats URLs — not useful as profile links
        if any(skip in url for skip in (
            "shields.io", "readme-typing", "github-readme-stats",
            "github-readme-activity", "devicons", "githubusercontent",
            "vercel.app/api", "badgen.net", "wikimedia.org", "wikipedia.org",
            "giphy.com", "imgur.com", "flaticon.com", "iconfinder.com",
            "svgshare.com", "cdn.jsdelivr.net",
        )):
            continue
        # Skip URLs that are just image/font files
        lower_url = url.lower().split("?")[0]
        if lower_url.endswith((".svg", ".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".woff", ".woff2")):
            continue
        key = _classify_url(url)
        links.setdefault(key, [])
        if url not in links[key]:
            links[key].append(url)

    if links.get("linkedin"):
        out["linkedin"] = links["linkedin"][0]
    if links.get("twitter"):
        out["twitter"] = links["twitter"][0]
    if links.get("portfolio"):
        out["portfolio"] = links["portfolio"][0]

    # Everything else (Kaggle, LeetCode, Codeforces, personal sites, etc.)
    other = links.get("other", [])
    # Also include twitter/portfolio in other if we want full list
    if other:
        out["links_other"] = other

    # Headline — first meaningful text line (strip markdown/HTML)
    for line in readme_text.splitlines():
        clean = re.sub(r"<[^>]+>|[#*_`\[\]!|]", "", line).strip()
        if clean and len(clean) > 20 and "http" not in clean and "svg" not in clean.lower():
            out["headline"] = clean[:200]
            break

    # Skills — from markdown table cells and bullet lists
    skills: list[str] = []
    seen_s: set[str] = set()

    # Table rows: | Category | tool1, tool2, tool3 |
    for cell in re.findall(r"\|([^|]+)\|", readme_text):
        cell_clean = re.sub(r"<img[^>]*/>|<[^>]+>|\*\*|`", "", cell)
        for token in re.split(r"[,&\n ]+", cell_clean):
            token = token.strip().strip("*• ").strip()
            if 2 < len(token) < 40 and not token.startswith("http") and token.lower() not in seen_s:
                seen_s.add(token.lower())
                skills.append(token)

    # Bullet list items that look like skill names
    for line in readme_text.splitlines():
        stripped = line.strip().lstrip("-•*").strip()
        if len(stripped) < 3 or len(stripped) > 40:
            continue
        if "http" in stripped or re.search(r"[<>|#]", stripped):
            continue
        if stripped.lower() not in seen_s:
            seen_s.add(stripped.lower())
            skills.append(stripped)

    if skills:
        out["readme_skills"] = skills

    return out


def _extract_username(github_input: str) -> Optional[str]:
    """
    Accept a GitHub username or full URL.
    Returns the username string, or None if it can't be determined.
    """
    if not github_input:
        return None

    github_input = github_input.strip()

    # Full URL?
    m = _GITHUB_URL_RE.search(github_input)
    if m:
        return m.group(1)

    # Bare username (no slashes, no dots except possibly github.com prefix)
    if "/" not in github_input and " " not in github_input:
        return github_input.lstrip("@")

    return None


async def _aggregate_languages_by_bytes(
    client: "httpx.AsyncClient", username: str, repos: list[dict]
) -> list[str]:
    """
    Fetch per-repo language byte counts and aggregate across all repos.
    Returns languages sorted by total bytes written (most to least).
    Falls back to primary-language counting if requests fail.
    """
    byte_totals: Counter = Counter()
    fallback: Counter = Counter()

    for repo in repos:
        name = repo.get("name")
        primary = repo.get("language")
        if primary:
            fallback[primary] += 1
        if not name:
            continue
        try:
            resp = await client.get(f"{_API_BASE}/repos/{username}/{name}/languages")
            if resp.is_success:
                for lang, b in resp.json().items():
                    byte_totals[lang] += b
        except Exception:
            pass

    if byte_totals:
        return [lang for lang, _ in byte_totals.most_common()]
    return [lang for lang, _ in fallback.most_common()]


async def parse_github(github_input: str) -> dict:
    """
    Parse a GitHub profile from a username or URL.

    Returns:
      {"source": "github", "data": {...extracted fields...}}

    Never raises — on any error returns {"source": "github", "data": {}}.
    """
    empty = {"source": "github", "data": {}}

    if not _HTTPX_AVAILABLE:
        logger.error("httpx is required for GitHub parsing")
        return empty

    username = _extract_username(github_input)
    if not username:
        logger.warning("Could not extract GitHub username from: %r", github_input)
        return empty

    try:
        async with httpx.AsyncClient(headers=_build_headers(), timeout=_TIMEOUT) as client:
            # Fetch user profile
            user_resp = await client.get(f"{_API_BASE}/users/{username}")

            if user_resp.status_code == 404:
                logger.warning("GitHub user not found: %r", username)
                return empty

            if user_resp.status_code == 403:
                logger.warning("GitHub rate limit hit for user: %r", username)
                return empty

            if not user_resp.is_success:
                logger.warning("GitHub API error %d for user: %r", user_resp.status_code, username)
                return empty

            profile = user_resp.json()

            # Fetch repos for language analysis
            repos_resp = await client.get(
                f"{_API_BASE}/users/{username}/repos",
                params={"per_page": 100, "sort": "updated"},
            )
            repos = repos_resp.json() if repos_resp.is_success and isinstance(repos_resp.json(), list) else []

            # Aggregate language bytes across all repos (richer than primary-lang count)
            languages = await _aggregate_languages_by_bytes(client, username, repos)

            # Fetch profile README ({username}/{username} repo — GitHub convention)
            readme_data: dict = {}
            try:
                readme_resp = await client.get(f"{_API_BASE}/repos/{username}/{username}/readme")
                if readme_resp.is_success:
                    content = readme_resp.json().get("content", "")
                    if content:
                        readme_text = base64.b64decode(content).decode("utf-8", errors="replace")
                        readme_data = _parse_readme(readme_text)
                        logger.info("GitHub: profile README parsed for %r", username)
            except Exception as e:
                logger.debug("GitHub profile README not available for %r: %s", username, e)

    except httpx.TimeoutException:
        logger.warning("GitHub API timeout for user: %r", username)
        return empty
    except Exception as e:
        logger.warning("GitHub API unexpected error for %r: %s", username, e)
        return empty

    # Extract repo topics / descriptions for additional skill signals
    repo_topics: list[str] = []
    recently_active: list[str] = []
    for repo in repos:
        topics = repo.get("topics", [])
        if isinstance(topics, list):
            repo_topics.extend(topics)
        name = repo.get("name", "")
        # Collect names of non-fork, non-test repos with actual code as activity signal
        if (
            name
            and not repo.get("fork")
            and repo.get("language")
            and name.lower() not in {"test", username.lower()}
        ):
            recently_active.append(name)

    # Build data dict (only non-null/non-empty values)
    data: dict = {}

    def _add(key: str, value) -> None:
        if value is not None and value != "" and value != []:
            data[key] = value

    _add("full_name", profile.get("name"))
    _add("headline", profile.get("bio") or readme_data.get("headline"))
    _add("company", profile.get("company", "").strip().lstrip("@") if profile.get("company") else None)
    _add("location", profile.get("location"))
    _add("portfolio", profile.get("blog") or None)
    _add("github", f"https://github.com/{username}")
    _add("public_repos", profile.get("public_repos"))
    _add("recently_active_repos", recently_active[:10])

    # Email: profile API first, then README
    email = profile.get("email")
    if email:
        data["emails"] = [email.strip().lower()]
    elif readme_data.get("emails"):
        data["emails"] = readme_data["emails"]

    # Links from README (linkedin, twitter, portfolio, other)
    if readme_data.get("linkedin"):
        data["linkedin"] = readme_data["linkedin"]
    if readme_data.get("portfolio"):
        data["portfolio"] = readme_data["portfolio"]
    if readme_data.get("links_other"):
        data["links_other"] = readme_data["links_other"]

    # Skills = languages (by bytes) + repo topics + README tech stack (deduplicated)
    readme_skills = readme_data.get("readme_skills", [])
    skills: list[str] = []
    seen: set[str] = set()
    for item in languages + repo_topics + readme_skills:
        key = item.lower()
        if key not in seen:
            seen.add(key)
            skills.append(item)
    _add("skills", skills)

    logger.debug("GitHub parser extracted %d fields for %r", len(data), username)
    return {"source": "github", "data": data}
