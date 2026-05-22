from __future__ import annotations

import html

from atv_player.ui.theme import current_resolved_theme, current_theme_manager


def external_link_html(url: str, label: str) -> str:
    escaped_url = html.escape(url)
    escaped_label = html.escape(label)
    accent = current_theme_manager().tokens_for(current_resolved_theme()).accent
    return (
        f'<a href="{escaped_url}" style=" text-decoration:none; '
        f'color:{accent}; font-weight:600;">'
        f"{escaped_label}</a>"
    )
