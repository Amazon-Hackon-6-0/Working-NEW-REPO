from app.agents.campusbuddy.escalation_agent import anonymous_committee_message


def prepare_escalation(category: str, description: str):
    report = anonymous_committee_message(category, description)
    return {
        "confirmation_required": True,
        "committee": report["committee"],
        "anonymous_summary": report["summary"],
        "whatsapp_preview": report["message"],
        "privacy_note": "Raw chats are never shared. Only anonymous confirmed summaries are sent.",
    }


def committee_dashboard():
    return {
        "privacy": "Only anonymized, confirmed reports appear here.",
        "issues": [
            {
                "id": 101,
                "category": "Mess Food",
                "committee": "Mess Committee",
                "summary": "Students reported mess food quality concerns across 3 days.",
                "status": "Awaiting review",
                "count": 5,
            },
            {
                "id": 102,
                "category": "Wi-Fi",
                "committee": "IT Support Committee",
                "summary": "Multiple students report unstable hostel Wi-Fi during evening study hours.",
                "status": "Sent to committee",
                "count": 4,
            },
        ],
    }
