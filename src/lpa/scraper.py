"""Scraper: recent coverage from Malaysian outlets, as Article records.

Reads each outlet's feed rather than crawling article pages. The feed carries
title, canonical URL, publication time and the full body in one request
instead of one per article — kinder to the outlet, less to go wrong, and no
HTML layout to track. RSS and Atom are both understood, so adding an outlet
stays a config edit.

Parsing is pure and tested against a fixture feed. The fetching half checks
robots.txt before every request and spaces requests out per host, robots.txt
included (issue #1, story 21).
"""

from __future__ import annotations

import html
import re
import time
import urllib.robotparser
import xml.etree.ElementTree as ElementTree
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Iterable
from urllib.parse import urljoin, urlparse

import httpx

from lpa.domain import Article, Outlet

USER_AGENT = (
    "live-political-analysis/0.1 "
    "(+https://github.com/IlhamKassim/live-political-analysis)"
)
ATOM = "{http://www.w3.org/2005/Atom}"
CONTENT_ENCODED = "{http://purl.org/rss/1.0/modules/content/}encoded"

# The second alternative catches a tag left unterminated by truncated or
# malformed markup, which would otherwise survive into the article text.
_TAG = re.compile(r"<[^>]*>|<[^>]*$")
_WHITESPACE = re.compile(r"\s+")


class UnreadableFeed(Exception):
    """The document fetched from an outlet is not a feed we can read."""


def parse_feed(feed_xml: str | bytes, source: str) -> list[Article]:
    """Turn an RSS or Atom feed into Article records. Pure — no network.

    Items missing a link or a title are skipped — there is no Article without
    them. A missing date is kept as `None` rather than guessed at: a wrong
    `published_at` would misdate a whole day's Sentiment, but an honestly
    absent one misdates nothing, and Bernama's feed dates no item at all.
    A document in neither format raises, because an outlet that has quietly
    changed format would otherwise look like an outlet with no news.
    """
    root = ElementTree.fromstring(feed_xml)
    if root.tag == f"{ATOM}feed":
        entries, read = list(root.iter(f"{ATOM}entry")), _atom_entry
    elif root.tag == "rss" or root.find("channel") is not None:
        entries, read = list(root.iter("item")), _rss_item
    else:
        raise UnreadableFeed(f"{source}: not an RSS or Atom feed (root <{root.tag}>)")

    articles = []
    for entry in entries:
        url, title, published_at, body = read(entry)
        if not (url and title):
            continue
        articles.append(
            Article(
                source=source,
                url=url,
                published_at=published_at,
                title=title,
                text=strip_html(body),
            )
        )
    return articles


def strip_html(markup: str) -> str:
    """Reduce an article body to the plain text the Sentiment Scorer reads.

    Entities are decoded before tags are stripped, so numeric and named
    escapes alike resolve and no markup survives into the text. WordPress
    feeds — which most of these outlets publish — emit them constantly.
    """
    return _WHITESPACE.sub(" ", _TAG.sub(" ", html.unescape(markup or ""))).strip()


class RateLimiter:
    """Spaces requests out per host, so one outlet never sets another's pace."""

    def __init__(self, min_interval: float = 2.0, sleep=time.sleep, now=time.monotonic):
        self.min_interval = min_interval
        self._sleep = sleep
        self._now = now
        self._last_request: dict[str, float] = {}

    def wait_turn(self, url: str, crawl_delay: float | None = None) -> None:
        """Wait until this host may be asked again, then record the request."""
        host = urlparse(url).netloc
        interval = max(self.min_interval, crawl_delay or 0.0)
        last = self._last_request.get(host)
        if last is not None:
            remaining = interval - (self._now() - last)
            if remaining > 0:
                self._sleep(remaining)
        self._last_request[host] = self._now()


class RobotsPolicy:
    """What an outlet's robots.txt permits, fetched once per host.

    robots.txt is fetched with the same declared User-Agent as everything else
    rather than through `RobotFileParser.read()`, whose stock urllib agent some
    outlets' CDNs refuse. A 403 there would otherwise read as "everything is
    disallowed" and silently stop the Scraper on a feed that is in fact allowed.

    Note that Python's `RobotFileParser` takes the first matching rule rather
    than the longest, unlike Google's parser. Where the two disagree it refuses
    more than it should, which is the safe direction to be wrong in.
    """

    def __init__(
        self,
        user_agent: str = USER_AGENT,
        client: httpx.Client | None = None,
        limiter: RateLimiter | None = None,
    ) -> None:
        self.user_agent = user_agent
        self.client = client or new_client(user_agent)
        self.limiter = limiter or RateLimiter()
        self._by_host: dict[str, urllib.robotparser.RobotFileParser] = {}

    def rules_for(self, url: str) -> urllib.robotparser.RobotFileParser:
        host = urlparse(url).netloc
        if host not in self._by_host:
            self._by_host[host] = self._read(urljoin(url, "/robots.txt"))
        return self._by_host[host]

    def _read(self, robots_url: str) -> urllib.robotparser.RobotFileParser:
        rules = urllib.robotparser.RobotFileParser()
        self.limiter.wait_turn(robots_url)
        try:
            response = self.client.get(robots_url)
        except httpx.HTTPError:
            # No answer is not permission: fail closed and try again next run.
            rules.disallow_all = True
            return rules
        if response.status_code in (401, 403) or response.status_code >= 500:
            # Forbidden, or the outlet is unwell. Either way, don't assume yes.
            rules.disallow_all = True
        elif response.status_code >= 400:
            rules.allow_all = True  # No robots.txt published means no rules.
        else:
            rules.parse(response.text.splitlines())
        return rules

    def is_allowed(self, url: str) -> bool:
        return self.rules_for(url).can_fetch(self.user_agent, url)

    def crawl_delay(self, url: str) -> float | None:
        delay = self.rules_for(url).crawl_delay(self.user_agent)
        return float(delay) if delay is not None else None


class Scraper:
    """Fetches outlet feeds, obeying robots.txt and a per-host request spacing."""

    def __init__(
        self,
        client: httpx.Client | None = None,
        robots: RobotsPolicy | None = None,
        limiter: RateLimiter | None = None,
    ) -> None:
        self.client = client or new_client()
        self.limiter = limiter or RateLimiter()
        self.robots = robots or RobotsPolicy(client=self.client, limiter=self.limiter)

    def __enter__(self) -> "Scraper":
        return self

    def __exit__(self, *exc_info) -> None:
        self.close()

    def close(self) -> None:
        self.client.close()

    def fetch(self, outlet: Outlet) -> list[Article]:
        """Fetch one outlet's recent Articles, or none if robots.txt forbids it."""
        if not self.robots.is_allowed(outlet.feed_url):
            return []
        self.limiter.wait_turn(
            outlet.feed_url, self.robots.crawl_delay(outlet.feed_url)
        )
        response = self.client.get(outlet.feed_url)
        response.raise_for_status()
        return parse_feed(response.content, outlet.name)

    def fetch_all(self, outlets: Iterable[Outlet]) -> list[Article]:
        """Fetch every outlet, carrying on past any one that fails.

        The daily job is unattended (ADR 0002), so one outlet's outage must
        not cost the run every other outlet's coverage.
        """
        articles: list[Article] = []
        for outlet in outlets:
            try:
                articles.extend(self.fetch(outlet))
            except (httpx.HTTPError, UnreadableFeed, ElementTree.ParseError) as error:
                print(f"skipping {outlet.name}: {type(error).__name__}: {error}")
        return articles


def new_client(user_agent: str = USER_AGENT) -> httpx.Client:
    return httpx.Client(
        headers={"User-Agent": user_agent}, timeout=30.0, follow_redirects=True
    )


def _rss_item(item: ElementTree.Element):
    return (
        _text(item, "link"),
        _text(item, "title"),
        _published_at(_text(item, "pubDate")),
        _text(item, CONTENT_ENCODED) or _text(item, "description"),
    )


def _atom_entry(entry: ElementTree.Element):
    link = entry.find(f"{ATOM}link")
    return (
        (link.get("href") or "").strip() if link is not None else "",
        _text(entry, f"{ATOM}title"),
        _published_at(
            _text(entry, f"{ATOM}published") or _text(entry, f"{ATOM}updated")
        ),
        _text(entry, f"{ATOM}content") or _text(entry, f"{ATOM}summary"),
    )


def _text(element: ElementTree.Element, tag: str) -> str:
    found = element.find(tag)
    return (found.text or "").strip() if found is not None else ""


def _published_at(raw: str) -> datetime | None:
    """Read a feed timestamp, RFC 822 (RSS) or ISO 8601 (Atom)."""
    if not raw:
        return None
    for read in (parsedate_to_datetime, datetime.fromisoformat):
        try:
            published = read(raw)
        except (TypeError, ValueError):
            continue
        return published if published.tzinfo else published.replace(tzinfo=timezone.utc)
    return None


def main() -> None:
    """Fetch the configured outlets and print the Articles for inspection."""
    import json

    from lpa.config import load_outlets

    with Scraper() as scraper:
        articles = scraper.fetch_all(load_outlets())

    for article in articles:
        print(
            json.dumps(
                {
                    "source": article.source,
                    "url": article.url,
                    "published_at": (
                        article.published_at.isoformat()
                        if article.published_at
                        else None
                    ),
                    "title": article.title,
                    "text": article.text[:200],
                },
                ensure_ascii=False,
            )
        )
    print(f"\n{len(articles)} Articles from {len({a.source for a in articles})} outlets.")


if __name__ == "__main__":
    main()
