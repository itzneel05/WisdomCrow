import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

CATEGORY_LABELS = {
    "ctf": "CTF Competitions",
    "bug_bounty": "Bug Bounties",
    "free_cert": "Free Certifications",
    "hackathon": "Hackathons & Conferences",
    "early_bird": "Early Birds & Discounts",
    "arcade": "Arcade & Gamified Events",
    "open_source": "Open Source Tools",
    "unknown": "Uncategorized",
    "needs_review": "Needs Review",
}

CATEGORY_EMOJIS = {
    "ctf": "\U0001f3f0",
    "bug_bounty": "\U0001f4b0",
    "free_cert": "\U0001f393",
    "hackathon": "\U0001f525",
    "early_bird": "\U0001f426",
    "arcade": "\U0001f3ae",
    "open_source": "\U0001f4e6",
    "unknown": "\U00002753",
    "needs_review": "\U0001f50d",
}

CONFIDENCE_ICONS = {
    "high": "\U0001f7e2",
    "medium": "\U0001f7e1",
    "low": "\U0001f7eb",
}


def _build_frontmatter(report_type: str, stats: dict[str, Any]) -> str:
    now = datetime.now(timezone.utc)
    date_str = now.strftime("%Y-%m-%d")
    lines = ["---"]
    lines.append(f"title: WisdomCrow {report_type.title()} Report - {date_str}")
    lines.append(f"date: {now.strftime('%Y-%m-%dT%H:%M:%SZ')}")
    lines.append("type: radar-report")
    lines.append(f"report_type: {report_type}")
    lines.append(f"total_opportunities: {stats.get('total', 0)}")
    lines.append("tags:")
    lines.append("  - radar")
    lines.append(f"  - {report_type}")
    lines.append("---")
    return "\n".join(lines)


def _build_summary(opportunities: list[dict[str, Any]]) -> str:
    total = len(opportunities)
    by_category: dict[str, int] = {}
    for opp in opportunities:
        cat = opp.get("category", "unknown")
        by_category[cat] = by_category.get(cat, 0) + 1

    lines = ["## Summary", "", f"**Total opportunities:** {total}", ""]
    lines.append("| Category | Count |")
    lines.append("|----------|-------|")
    for cat, count in sorted(by_category.items(), key=lambda x: -x[1]):
        emoji = CATEGORY_EMOJIS.get(cat, "")
        label = CATEGORY_LABELS.get(cat, cat)
        lines.append(f"| {emoji} {label} | {count} |")
    lines.append("")
    return "\n".join(lines)


def _build_category_section(category: str, opps: list[dict[str, Any]]) -> str:
    emoji = CATEGORY_EMOJIS.get(category, "")
    label = CATEGORY_LABELS.get(category, category)
    lines = [f"## {emoji} {label}", ""]

    for opp in opps:
        title = opp.get("title", "Untitled")
        url = opp.get("url", "")
        confidence = opp.get("confidence", "low")
        icon = CONFIDENCE_ICONS.get(confidence, "")
        tags = opp.get("tags") or []
        event_date = opp.get("event_date") or ""
        snippet = opp.get("snippet", "")
        is_past = opp.get("is_past", False)

        if is_past:
            lines.append(f"~~[{title}]({url})~~ (past)")
        else:
            lines.append(f"- [{title}]({url})")
        details = []
        details.append(f"  - Confidence: {icon} {confidence.upper()}")
        if tags:
            tags_str = ", ".join(f"`{t}`" for t in tags[:5])
            details.append(f"  - Tags: {tags_str}")
        if event_date:
            details.append(f"  - Event: {event_date}")
        if snippet:
            clean = snippet.replace("\n", " ").strip()[:200]
            details.append(f"  - _{clean}_")
        lines.extend(details)
        lines.append("")

    return "\n".join(lines)


def generate_report(
    opportunities: list[dict[str, Any]],
    output_dir: str | Path,
    report_type: str = "daily",
) -> Path | None:
    if not opportunities:
        logger.info("No opportunities for report, skipping")
        return None

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    now = datetime.now(timezone.utc)
    date_str = now.strftime("%Y-%m-%d")
    filename = f"radar-{report_type}-{date_str}.md"
    filepath = output_path / filename

    by_category: dict[str, list[dict[str, Any]]] = {}
    for opp in opportunities:
        cat = opp.get("category", "unknown")
        by_category.setdefault(cat, []).append(opp)

    stats = {"total": len(opportunities)}

    sections = [
        _build_frontmatter(report_type, stats),
        f"\n# WisdomCrow {report_type.title()} Report",
        "",
        _build_summary(opportunities),
    ]

    category_order = [
        "ctf",
        "bug_bounty",
        "free_cert",
        "hackathon",
        "early_bird",
        "arcade",
        "open_source",
        "needs_review",
        "unknown",
    ]

    for cat in category_order:
        opps = by_category.pop(cat, None)
        if opps:
            opps_sorted = sorted(
                opps,
                key=lambda o: list(CONFIDENCE_ICONS.keys()).index(
                    o.get("confidence", "low")
                ),
            )
            sections.append(_build_category_section(cat, opps_sorted))

    for cat, opps in sorted(by_category.items()):
        if opps:
            sections.append(_build_category_section(cat, opps))

    content = "\n".join(sections)

    filepath.write_text(content, encoding="utf-8")
    logger.info(f"Report generated: {filepath} ({len(opportunities)} opportunities)")
    return filepath
