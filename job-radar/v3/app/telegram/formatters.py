"""Job card formatting for Telegram."""


def format_job_card(job: dict, index: int = 0) -> str:
    """Format a single job for Telegram digest."""
    hot = "🔥 " if job.get('score_composite', 0) >= 70 else ""

    # Confidence indicator
    conf = job.get('confidence', 'medium')
    def fmt_score(s, c=conf):
        if c == 'low':
            return f"?{s}"
        if c == 'medium':
            return f"~{s}"
        return str(s)

    # Staleness
    staleness = ""
    if job.get('staleness_days', 0) >= 14:
        staleness = f" | ⏳ {job['staleness_days']}d ago"

    # YoE
    yoe_str = ""
    if job.get('yoe_min') is not None:
        yoe_max = job.get('yoe_max', '?')
        yoe_str = f"{job['yoe_min']}-{yoe_max}yr YoE"
    elif job.get('seniority_signal') == 'junior':
        yoe_str = "Entry-level"

    # Contractor
    contractor = " | Contractor OK" if job.get('contractor_ok') else ""

    # Tech stack (max 5)
    tech = ", ".join((job.get('tech_stack') or [])[:5])

    # Remote policy display
    remote_display = {
        'worldwide': 'Remote worldwide',
        'americas': 'Remote Americas',
        'colombia': 'Remote Colombia',
        'latam': 'Remote LATAM',
        'us_only': 'US only',
        'hybrid': 'Hybrid',
        'remote_unspecified': 'Remote (region unclear)',
        'unknown': 'Unknown location',
    }.get(job.get('remote_policy', ''), 'Remote')

    # Hidden junior badge
    hidden = ""
    if job.get('hidden_junior'):
        hidden = "\n   🎓 No seniority in title, ≤5 requirements"

    lines = [
        f"{hot}{index}. {job.get('title', '?')} @ {job.get('company_name', '?')}",
        f"   📊 Opp: {job.get('score_opportunity', 0)} | Jr: {fmt_score(job.get('score_junior', 0))} | COL: {fmt_score(job.get('score_colombia', 0))} → {job.get('score_composite', 0)}",
    ]
    if tech:
        lines.append(f"   🏷 {tech}")
    lines.append(f"   📍 {remote_display}{contractor}{staleness}")
    if yoe_str:
        lines.append(f"   🎓 {yoe_str}")
    if hidden:
        lines.append(hidden)
    lines.append(f"   📋 Apply: {job.get('apply_notes') or 'See posting'}")
    lines.append(f"   🔗 {job.get('apply_url') or job.get('url', '')}")

    return "\n".join(lines)


def format_digest(jobs: list[dict], digest_type: str = "am", stats: dict | None = None) -> str:
    """Format a full digest message."""
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    date_str = now.strftime("%Y-%m-%d")

    type_label = {
        "am": "Morning Scout",
        "pm": "Evening Update",
        "weekly": "Weekly Report",
    }.get(digest_type, "Scout")

    new_count = sum(1 for j in jobs if j.get('status') == 'new')
    hot_count = sum(1 for j in jobs if j.get('score_composite', 0) >= 70)

    header = f"🔍 Job Radar — {type_label}\n📅 {date_str} | 🆕 {new_count} new | 🔥 {hot_count} hot leads"
    sep = "━" * 30

    # Split into hot leads and hidden junior
    hot_jobs = [j for j in jobs if j.get('score_composite', 0) >= 70 and not j.get('hidden_junior')]
    hidden_jobs = [j for j in jobs if j.get('hidden_junior')]
    regular_jobs = [j for j in jobs if j.get('score_composite', 0) < 70 and not j.get('hidden_junior')]

    sections = [header, sep]
    idx = 1

    for job in hot_jobs:
        sections.append(format_job_card(job, idx))
        sections.append(sep)
        idx += 1

    if hidden_jobs:
        sections.append("\n🕵️ Hidden Junior Opportunities:")
        for job in hidden_jobs:
            sections.append(format_job_card(job, idx))
            sections.append(sep)
            idx += 1

    for job in regular_jobs:
        sections.append(format_job_card(job, idx))
        sections.append(sep)
        idx += 1

    # Footer
    if stats:
        footer = f"📊 Pipeline: {stats.get('saved', 0)} saved | {stats.get('applied', 0)} applied | {stats.get('interviewing', 0)} interviewing"
        sections.append(footer)

    sections.append("💡 Tip: Save or Pass jobs to improve future recommendations.")
    return "\n".join(sections)


def format_job_detail(job: dict) -> str:
    """Format detailed job view for Telegram callback."""
    tech = ", ".join(job.get('tech_stack') or [])
    reqs = job.get('requirements') or []
    req_str = "\n".join(f"• {r}" for r in reqs[:8]) if reqs else "Not parsed"

    lines = [
        f"📋 {job.get('title', '?')} @ {job.get('company_name', '?')}",
        "",
        f"Company: {job.get('company_name', '?')}",
        f"ATS: {job.get('ats_platform', 'unknown')}",
        "",
        f"Role: {(job.get('description_snippet', '') or '')[:300]}",
        "",
        f"Tech Stack: {tech or 'Not detected'}",
        "",
        f"Requirements:",
        req_str,
        "",
        "Scores:",
        f"  ✅ Opp {job.get('score_opportunity', 0)}: Tech stack + company signal",
        f"  ✅ Jr {job.get('score_junior', 0)}: Accessibility + YoE",
        f"  ✅ COL {job.get('score_colombia', 0)}: Remote policy + timezone",
        "",
        f"📋 Apply: {job.get('apply_url') or job.get('url', '')}",
        f"Method: {job.get('apply_notes', 'See posting')}",
    ]
    return "\n".join(lines)


def format_stats(stats: dict) -> str:
    """Format pipeline stats for /stats command."""
    lines = [
        f"📊 Job Radar — Pipeline Health ({stats.get('window_days', 7)}d)",
        "━" * 30,
        f"Total discovered: {stats.get('total_discovered', 0)}",
        "",
        "By Status:",
    ]
    for s in stats.get('by_status', []):
        lines.append(f"  {s['status']}: {s['count']}")

    lines.append("\nBy Source:")
    for s in stats.get('by_source', []):
        lines.append(f"  {s['source']}: {s['count']}")

    if stats.get('dismiss_reasons'):
        lines.append("\nDismiss Reasons:")
        for s in stats.get('dismiss_reasons', []):
            lines.append(f"  {s['reason']}: {s['count']}")

    return "\n".join(lines)
