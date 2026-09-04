def format_email_markdown(
    subject: str,
    author: str,
    recipient: str,
    email_thread: str,
    email_id: str | None = None,
) -> str:
    """Format an email as Markdown for the response-agent prompt."""

    id_section = f"\n**ID**: {email_id}" if email_id else ""

    return f"""
**Subject**: {subject}
**From**: {author}
**To**: {recipient}{id_section}

{email_thread}

---
"""
