from __future__ import annotations

import re
from threading import Lock
from typing import Any

import httpx

from app.core.config import settings


DISCORD_API_BASE = "https://discord.com/api/v10"
CHANNEL_CREATION_LOCK = Lock()
VIEW_CHANNEL_PERMISSION = 1 << 10


def send_complaint_escalation_to_discord(escalation: dict) -> dict[str, Any]:
    if not campusbuddy_discord_configured():
        return disabled_result()

    channel_id = resolve_committee_channel_id(escalation.get("target_group"))
    if not channel_id:
        return {"sent": False, "reason": "discord_channel_not_found"}

    payload = {
        "allowed_mentions": {"parse": []},
        "content": "**CampusBuddy anonymous escalation reached threshold.**",
        "embeds": [
            {
                "title": "Anonymous campus issue escalation",
                "description": escalation.get("generalized_summary") or "Several students reported a recurring campus concern.",
                "color": 15158332,
                "fields": [
                    {"name": "Category", "value": str(escalation.get("category") or "general"), "inline": True},
                    {"name": "Target group", "value": str(escalation.get("target_group") or "student_council"), "inline": True},
                    {"name": "Unique reports", "value": str(escalation.get("complaint_count") or 0), "inline": True},
                    {
                        "name": "Privacy rule",
                        "value": "Only a generalized summary is sent. Student IDs and raw complaints are not shared.",
                    },
                ],
            }
        ],
    }
    response = send_channel_message(channel_id, payload)
    return {
        "sent": True,
        "channel_id": channel_id,
        "message_id": response.get("id"),
        "reason": None,
    }


def ensure_interest_group_channel(group: dict) -> dict[str, Any]:
    if not campusbuddy_discord_configured():
        return disabled_result()

    try:
        guild_id = resolve_guild_id()
        if not guild_id:
            return {"created": False, "sent": False, "reason": "discord_guild_not_found"}

        channel_name = channel_name_for_interest(group.get("hobby_label") or group.get("hobby_key") or "campusbuddy")
        with CHANNEL_CREATION_LOCK:
            channel = find_text_channel(guild_id, channel_name)
            created = False
            if not channel:
                channel = find_text_channel(guild_id, channel_name)
            if not channel:
                channel = create_text_channel(
                    guild_id,
                    channel_name,
                    topic=(
                        f"CampusBuddy opt-in group for {group.get('hobby_label', 'shared interest')}. "
                        "Students join voluntarily; identities are not exposed by CampusBuddy."
                    ),
                    private=False,
                )
                created = True
            else:
                channel = ensure_invite_joinable_channel(guild_id, channel)

        invite = create_channel_invite(channel["id"])
        announcement_channel_id = resolve_general_channel_id(guild_id)
        if not announcement_channel_id:
            return {
                "created": created,
                "sent": False,
                "private": False,
                "channel_id": channel["id"],
                "channel_name": channel["name"],
                "invite_url": invite.get("url"),
                "reason": "discord_general_channel_not_found",
            }

        payload = {
            "allowed_mentions": {"parse": []},
            "content": f"**{group.get('group_name', 'CampusBuddy group')} opt-in channel is ready.**\n{invite.get('url')}",
            "embeds": [
                {
                    "title": group.get("group_name") or "CampusBuddy interest group",
                    "description": (
                        group.get("group_summary")
                        or "A consent-based opt-in interest group is ready."
                    ),
                    "color": 5763719,
                    "fields": [
                        {"name": "Interest", "value": str(group.get("hobby_label") or "Shared interest"), "inline": True},
                        {
                            "name": "Interested students",
                            "value": str(consensus_count_for_group(group)),
                            "inline": True,
                        },
                        {"name": "Channel type", "value": "Invite-based opt-in channel", "inline": True},
                        {
                            "name": "How to join",
                            "value": "Use the invite link above. CampusBuddy does not expose who submitted the interest.",
                        },
                    ],
                }
            ],
        }
        message = send_channel_message(announcement_channel_id, payload)
        return {
            "created": created,
            "sent": True,
            "private": False,
            "channel_id": channel["id"],
            "channel_name": channel["name"],
            "announcement_channel_id": announcement_channel_id,
            "invite_code": invite.get("code"),
            "invite_url": invite.get("url"),
            "message_id": message.get("id"),
            "reason": None,
        }
    except httpx.HTTPError as exc:
        return {
            "created": False,
            "sent": False,
            "reason": f"discord_http_error: {str(exc)[:220]}",
        }


def campusbuddy_discord_configured() -> bool:
    return bool(
        settings.campusbuddy_discord_enabled
        and settings.discord_bot_token
        and (settings.discord_channel_id or settings.discord_guild_id)
    )


def disabled_result() -> dict[str, Any]:
    return {
        "created": False,
        "sent": False,
        "reason": "campusbuddy_discord_disabled_or_not_configured",
    }


def resolve_committee_channel_id(target_group: str | None) -> str | None:
    if target_group == "tech_support" and settings.discord_tech_support_channel_id:
        return settings.discord_tech_support_channel_id

    guild_id = resolve_guild_id()
    if not guild_id:
        return settings.discord_channel_id

    channel_name = channel_name_for_target_group(target_group)
    channel = find_text_channel(guild_id, channel_name)
    if channel:
        return channel["id"]
    return settings.discord_channel_id


def resolve_general_channel_id(guild_id: str) -> str | None:
    if settings.discord_channel_id:
        return settings.discord_channel_id

    channel = find_text_channel(guild_id, "general")
    if channel:
        return channel["id"]
    return None


def resolve_guild_id() -> str | None:
    if settings.discord_guild_id:
        return settings.discord_guild_id
    if not settings.discord_channel_id:
        return None

    with httpx.Client(timeout=20) as client:
        response = client.get(
            f"{DISCORD_API_BASE}/channels/{settings.discord_channel_id}",
            headers=discord_headers(),
        )
    response.raise_for_status()
    return response.json().get("guild_id")


def list_guild_channels(guild_id: str) -> list[dict[str, Any]]:
    with httpx.Client(timeout=20) as client:
        response = client.get(
            f"{DISCORD_API_BASE}/guilds/{guild_id}/channels",
            headers=discord_headers(),
        )
    response.raise_for_status()
    return response.json()


def find_text_channel(guild_id: str, channel_name: str) -> dict[str, Any] | None:
    normalized = normalize_channel_name(channel_name)
    for channel in list_guild_channels(guild_id):
        if channel.get("type") == 0 and normalize_channel_name(channel.get("name", "")) == normalized:
            return channel
    return None


def create_text_channel(guild_id: str, channel_name: str, topic: str, private: bool = False) -> dict[str, Any]:
    payload = {
        "name": normalize_channel_name(channel_name),
        "type": 0,
        "topic": topic[:1024],
    }
    if private:
        payload["permission_overwrites"] = private_channel_overwrites(guild_id)

    with httpx.Client(timeout=20) as client:
        response = client.post(
            f"{DISCORD_API_BASE}/guilds/{guild_id}/channels",
            headers=discord_headers(),
            json=payload,
        )
    response.raise_for_status()
    return response.json()


def ensure_invite_joinable_channel(guild_id: str, channel: dict[str, Any]) -> dict[str, Any]:
    overwrites = channel.get("permission_overwrites") or []
    everyone_overwrite = next(
        (
            overwrite
            for overwrite in overwrites
            if overwrite.get("id") == guild_id and overwrite.get("type") == 0
        ),
        None,
    )
    deny_value = int(everyone_overwrite.get("deny", "0")) if everyone_overwrite else 0
    if not (deny_value & VIEW_CHANNEL_PERMISSION):
        return channel

    next_overwrites = [
        overwrite
        for overwrite in overwrites
        if not (overwrite.get("id") == guild_id and overwrite.get("type") == 0)
    ]
    payload = {"permission_overwrites": next_overwrites}
    with httpx.Client(timeout=20) as client:
        response = client.patch(
            f"{DISCORD_API_BASE}/channels/{channel['id']}",
            headers=discord_headers(),
            json=payload,
        )
    response.raise_for_status()
    return response.json()


def consensus_count_for_group(group: dict[str, Any]) -> int:
    try:
        member_count = int(group.get("member_interest_count") or 0)
        threshold = int(group.get("threshold") or 0)
    except (TypeError, ValueError):
        return 0
    if threshold <= 0:
        return member_count
    return min(member_count, threshold)


def private_channel_overwrites(guild_id: str) -> list[dict[str, Any]]:
    return [
        {
            "id": guild_id,
            "type": 0,
            "allow": "0",
            "deny": str(VIEW_CHANNEL_PERMISSION),
        }
    ]


def create_channel_invite(channel_id: str) -> dict[str, Any]:
    payload = {
        "max_age": 0,
        "max_uses": 0,
        "temporary": False,
        "unique": False,
    }
    with httpx.Client(timeout=20) as client:
        response = client.post(
            f"{DISCORD_API_BASE}/channels/{channel_id}/invites",
            headers=discord_headers(),
            json=payload,
        )
    response.raise_for_status()
    invite = response.json()
    invite["url"] = f"https://discord.gg/{invite.get('code')}"
    return invite


def send_channel_message(channel_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    with httpx.Client(timeout=20) as client:
        response = client.post(
            f"{DISCORD_API_BASE}/channels/{channel_id}/messages",
            headers=discord_headers(),
            json=payload,
        )
    response.raise_for_status()
    return response.json()


def discord_headers() -> dict[str, str]:
    return {
        "Authorization": f"Bot {settings.discord_bot_token}",
        "Content-Type": "application/json",
    }


def channel_name_for_target_group(target_group: str | None) -> str:
    names = {
        "tech_support": "tech-support",
        "mess_committee": "mess-committee",
        "hostel_committee": "hostel-committee",
        "maintenance_team": "maintenance-team",
        "academic_committee": "academic-committee",
        "transport_committee": "transport-committee",
        "student_council": "student-council",
    }
    return names.get(target_group or "", "student-council")


def channel_name_for_interest(label: str) -> str:
    return f"{normalize_channel_name(label)}-circle"


def normalize_channel_name(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9-]+", "-", value.lower().strip())
    normalized = re.sub(r"-+", "-", normalized).strip("-")
    return normalized[:90] or "campusbuddy"
