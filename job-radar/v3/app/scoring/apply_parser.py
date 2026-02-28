"""Extract how-to-apply info from job postings. No LLM calls."""
import re


def parse_apply_info(url: str, description: str, ats_platform: str = "") -> dict:
    result = {
        "apply_url": url,
        "apply_method": "unknown",
        "apply_notes": "",
    }

    if 'greenhouse.io' in url:
        result["apply_method"] = "ats_form"
        result["apply_notes"] = "Apply via Greenhouse form on the posting page."
        if '#app' not in url:
            result["apply_url"] = url.split('?')[0] + '#app'
    elif 'lever.co' in url:
        result["apply_method"] = "ats_form"
        result["apply_notes"] = "Apply via Lever. Click 'Apply for this job' at bottom."
        if '/apply' not in url:
            result["apply_url"] = url.rstrip('/') + '/apply'
    elif 'ashbyhq.com' in url:
        result["apply_method"] = "ats_form"
        result["apply_notes"] = "Apply via Ashby form on the posting page."
    elif 'workable.com' in url:
        result["apply_method"] = "ats_form"
        result["apply_notes"] = "Apply via Workable. Look for 'Apply' button."
    elif 'wellfound.com' in url:
        result["apply_method"] = "ats_form"
        result["apply_notes"] = "Apply via Wellfound. Requires Wellfound account."

    # Check for email apply
    email_match = re.search(
        r'(?:apply|send|email|resume|cv).{0,30}?([\w.+-]+@[\w-]+\.[\w.]+)',
        description, re.IGNORECASE
    )
    if email_match:
        result["apply_method"] = "email"
        result["apply_url"] = f"mailto:{email_match.group(1)}"
        result["apply_notes"] = f"Email resume to {email_match.group(1)}"

    # Check for custom apply links
    custom_apply = re.search(
        r'(?:apply|application)\s*(?:here|at|:)\s*:?\s*(https?://\S+)',
        description, re.IGNORECASE
    )
    if custom_apply:
        result["apply_url"] = custom_apply.group(1)
        result["apply_method"] = "custom"
        result["apply_notes"] = f"Direct apply link: {custom_apply.group(1)}"

    return result
