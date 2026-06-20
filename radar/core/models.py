import hashlib
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any
from urllib.parse import urlencode, urlparse, urlunparse, parse_qs


class SourceType(str, Enum):
    RSS = "rss"
    SITEMAP = "sitemap"
    GITHUB = "github"
    GITHUB_ORG = "github_org"
    REDDIT = "reddit"
    HTML_WATCH = "html_watch"


class Cadence(str, Enum):
    FAST = "fast"
    DAILY = "daily"
    WEEKLY = "weekly"


class Category(str, Enum):
    CTF = "ctf"
    BUG_BOUNTY = "bug_bounty"
    HACKATHON = "hackathon"
    FREE_CERT = "free_cert"
    EARLY_BIRD = "early_bird"
    ARCADE = "arcade"
    OPEN_SOURCE = "open_source"
    UNKNOWN = "unknown"
    NEEDS_REVIEW = "needs_review"


class Confidence(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class Status(str, Enum):
    NEW = "new"
    REVIEWED = "reviewed"
    INTERESTED = "interested"
    REGISTERED = "registered"
    IGNORED = "ignored"
    FALSE_POSITIVE = "false_positive"
    MISSED = "missed"
    COMPLETED = "completed"
    WON = "won"


class FeedbackLabel(str, Enum):
    GOOD = "good"
    FALSE_POSITIVE = "false_positive"
    MISSED = "missed"
    DUPLICATE = "duplicate"


_INDIA_KEYWORDS = [
    "india",
    "ist",
    "gujarat",
    "bangalore",
    "bengaluru",
    "mumbai",
    "delhi",
    "hyderabad",
    "pune",
    "chennai",
    "kochi",
    "kerala",
    "iit",
    "nit",
    "iiit",
    "acm india",
    "nullcon",
    "c0c0n",
    "inctf",
    "amrita",
    "iit madras",
    "iit bombay",
    "iit kanpur",
    "konfhub",
    "unstop",
    "internshala",
]

_PARTICIPATION_KEYWORDS = [
    "everyone who",
    "all participants",
    "participants receive",
    "guaranteed swag",
    "first n",
    "every registrant",
    "everyone gets",
]

_NEGATIVE_KEYWORDS = [
    "football",
    "sports",
    "capture the flag game",
    "paintball",
    "minecraft",
    "roblox",
    "flag football",
    "political campaign",
    "sales training",
    "physical security guard",
]

_TRACKING_PARAMS = {
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
    "fbclid",
    "gclid",
    "mc_cid",
    "mc_eid",
    "ref",
    "source",
}


def normalize_url(url: str) -> str:
    if not url:
        return url
    parsed = urlparse(url.lower())
    scheme = parsed.scheme
    netloc = parsed.netloc.replace("www.", "")
    path = parsed.path.rstrip("/")
    query = parse_qs(parsed.query, keep_blank_values=True)
    for param in _TRACKING_PARAMS:
        query.pop(param, None)
    sorted_query = urlencode(sorted(query.items()), doseq=True)
    fragment = ""
    result = urlunparse((scheme, netloc, path, parsed.params, sorted_query, fragment))
    return result


def normalize_title(title: str) -> str:
    title = title.strip()
    title = re.sub(r"\s+", " ", title)
    title = title.lower()
    title = re.sub(r"\s*[|—–-]\s*.*$", "", title)
    return title.strip()


def make_canonical_key(title: str, url: str) -> str:
    ntitle = normalize_title(title)
    nurl = normalize_url(url)
    raw = f"{ntitle}|{nurl}"
    return hashlib.sha256(raw.encode()).hexdigest()


def has_negative_keywords(text: str) -> bool:
    text_lower = text.lower()
    for kw in _NEGATIVE_KEYWORDS:
        if kw in text_lower:
            return True
    return False


@dataclass
class RawHit:
    source_id: str
    source_name: str
    title: str
    url: str
    canonical_url: str = ""
    snippet: str = ""
    content_hash: str = ""
    published_at: str = ""
    detector_hint: str = ""
    extra: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.canonical_url:
            self.canonical_url = normalize_url(self.url)
        if not self.content_hash:
            raw = f"{self.title}|{self.url}"
            self.content_hash = hashlib.md5(raw.encode()).hexdigest()

    def is_valid(self) -> bool:
        return bool(self.title) and bool(self.url)

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "source_name": self.source_name,
            "title": self.title,
            "url": self.url,
            "canonical_url": self.canonical_url,
            "snippet": self.snippet,
            "content_hash": self.content_hash,
            "published_at": self.published_at,
            "detector_hint": self.detector_hint,
            "extra": self.extra,
        }


@dataclass
class DetectorResult:
    matched: bool = False
    confidence: Confidence = Confidence.LOW
    category: Category = Category.UNKNOWN
    tags: list[str] = field(default_factory=list)
    why_found: list[str] = field(default_factory=list)
    event_date: str = ""


@dataclass
class Opportunity:
    title: str
    url: str
    category: Category
    confidence: Confidence = Confidence.LOW
    status: Status = Status.NEW
    snippet: str = ""
    event_date: str = ""
    deadline_date: str = ""
    is_past: bool = False
    tags: list[str] = field(default_factory=list)
    canonical_key: str = ""
    first_seen_at: str = ""
    last_seen_at: str = ""
    alerted: bool = False
    notes: str = ""

    def __post_init__(self) -> None:
        if not self.canonical_key:
            self.canonical_key = make_canonical_key(self.title, self.url)
        now_utc = datetime.now(timezone.utc).isoformat()
        if not self.first_seen_at:
            self.first_seen_at = now_utc
        if not self.last_seen_at:
            self.last_seen_at = now_utc

    def apply_india_tag(self) -> None:
        text = f"{self.title} {self.snippet}".lower()
        for kw in _INDIA_KEYWORDS:
            if kw in text:
                if "india_friendly" not in self.tags:
                    self.tags.append("india_friendly")
                break

    def apply_participation_tag(self) -> None:
        text = f"{self.title} {self.snippet}".lower()
        for kw in _PARTICIPATION_KEYWORDS:
            if kw in text:
                if "participation_reward" not in self.tags:
                    self.tags.append("participation_reward")
                break

    def apply_is_past_tag(self) -> None:
        if self.is_past:
            if "is_past" not in self.tags:
                self.tags.append("is_past")

    def apply_cross_cut_tags(self) -> None:
        self.apply_india_tag()
        self.apply_participation_tag()
        self.apply_is_past_tag()

    def short_summary(self) -> str:
        tags_str = ", ".join(self.tags[:5])
        date_str = self.event_date or "No event date"
        return f"{self.title} | {self.category.value} | {self.confidence.value} | Tags: {tags_str} | Event: {date_str}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "url": self.url,
            "category": self.category.value,
            "confidence": self.confidence.value,
            "status": self.status.value,
            "snippet": self.snippet,
            "event_date": self.event_date,
            "deadline_date": self.deadline_date,
            "is_past": self.is_past,
            "tags": self.tags,
            "canonical_key": self.canonical_key,
            "first_seen_at": self.first_seen_at,
            "last_seen_at": self.last_seen_at,
            "alerted": self.alerted,
        }


@dataclass
class SourceMeta:
    name: str
    source_type: SourceType
    url: str
    cadence: Cadence
    detector_hint: str = ""
    watch_patterns: list[str] = field(default_factory=list)
    enabled: bool = True

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "SourceMeta":
        return cls(
            name=d["name"],
            source_type=SourceType(d["type"]),
            url=d["url"],
            cadence=Cadence(d.get("cadence", "daily")),
            detector_hint=d.get("detector_hint", ""),
            watch_patterns=d.get("watch_patterns", []),
            enabled=d.get("enabled", True),
        )
