from __future__ import annotations

from dataclasses import replace

from mailwyrm.models import AutomationPolicy


def render_policy_status(policy: AutomationPolicy) -> str:
    lines = [
        "# Mailwyrm Policy Status",
        "",
        "Automation policy is local and explicit. Gmail is not queried or modified by this command.",
        "",
        "## Mailbox Actions",
        "",
        f"Archive after digest: {_status(policy.archive_after_digest_enabled)}",
        f"Trash after digest: {_status(policy.trash_after_digest_enabled)}",
        "",
        "## Trust Boundary",
        "",
    ]
    if policy.trash_after_digest_enabled:
        lines.append("Trash automation is enabled in local policy.")
    else:
        lines.append(
            "Trash automation is disabled. Future trash commands must require explicit policy opt-in before mutating Gmail."
        )
    return "\n".join(lines)


def enable_trash_after_digest(policy: AutomationPolicy) -> AutomationPolicy:
    return replace(policy, trash_after_digest_enabled=True)


def _status(enabled: bool) -> str:
    return "enabled" if enabled else "disabled"
