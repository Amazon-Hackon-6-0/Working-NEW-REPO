from app.agents.campusbuddy.classifier_agent import classify_student_message


def create_friend_response(message: str):
    intent = classify_student_message(message)
    interest = _extract_interest(message)
    replies = {
        "personal_support": "I am really glad you said that here. Feeling lonely in college can hurt, especially when everyone else seems settled. We can keep this private and take one gentle step: a low-pressure interest circle, an anonymous buddy chat, or a small group where you reveal identity only when you feel ready.",
        "academic_help": "That is exactly the kind of thing CampusBuddy can help with. I will classify this as academic help and look for DSA graph helpers. You can stay anonymous, show a limited profile, or reveal your identity later only if both sides agree.",
        "offer_help": f"That is useful. CampusBuddy can remember this as a skill only if you choose, so you may be suggested as an anonymous helper for {interest}-related requests.",
        "community_group": f"That sounds like a good community seed. I can look for students who consented to {interest} or similar interests and create an opt-in invite. Nobody is exposed by default.",
        "campus_issue": "I can help turn this into an anonymous committee-ready summary. Raw chats are never shared. You will see the WhatsApp preview and confirm before simulated sending.",
        "general": "I am listening. You can talk freely here, and you control what I remember or share.",
    }
    memory_candidate = None
    if intent in {"personal_support", "academic_help", "community_group", "offer_help"}:
        memory_candidate = {
            "text": message,
            "label": helper_skill_label(message, interest) if intent == "offer_help" else f"Interested in {interest}" if intent == "community_group" else message,
            "reason": "This can help CampusBuddy suggest you as an anonymous helper only if you choose to remember it." if intent == "offer_help" else "This can help personalize support or suggest safer connections if you choose to remember it.",
            "requires_consent": True,
            "used_for": {
                "personalization": True,
                "peer_matching": True,
                "group_suggestions": False,
                "anonymous_campus_insight": False,
            } if intent == "offer_help" else None,
        }
    return {
        "reply": replies[intent],
        "intent": intent,
        "memory_candidate": memory_candidate,
        "actions": _actions_for(intent, interest),
    }


def _actions_for(intent: str, interest: str):
    actions = {
        "personal_support": [
            "Start with one anonymous buddy chat.",
            "Try a small opt-in interest circle instead of a large public group.",
            "Reveal identity only when you feel comfortable.",
        ],
        "academic_help": [
            "Find DSA graph helpers anonymously.",
            "Share only your branch/year if you choose.",
            "Reveal identity later only by mutual consent.",
        ],
        "offer_help": [
            "Remember this skill so CampusBuddy can suggest you as a helper with consent.",
            "Keep your identity anonymous unless both students later agree to reveal.",
            "Use this only for peer matching after you click Remember.",
        ],
        "community_group": [
            f"Draft an opt-in {interest} group invite.",
            f"Match with students who consented to {interest} or similar interests.",
            "Let students join voluntarily.",
        ],
        "campus_issue": [
            "Summarize the issue anonymously.",
            "Hide raw chat and identity.",
            "Ask for confirmation before simulated WhatsApp send.",
        ],
    }
    return actions.get(intent, [])


def helper_skill_label(message: str, interest: str) -> str:
    if interest and interest != "this interest":
        return f"Student can help with {interest.upper() if interest == 'dsa' else interest}"
    return f"Student can help with {message}"


def _extract_interest(message: str) -> str:
    text = message.lower()
    known_interests = [
        "football",
        "chess",
        "gym",
        "music",
        "anime",
        "coding",
        "cricket",
        "basketball",
        "badminton",
        "dance",
        "art",
        "photography",
        "dsa",
        "graphs",
        "dynamic programming",
        "java",
        "machine learning",
    ]
    for interest in known_interests:
        if interest in text:
            return interest
    for marker in ["play ", "start a ", "join a ", "interested in "]:
        if marker in text:
            after_marker = text.split(marker, 1)[1]
            words = [word.strip(".,!?") for word in after_marker.split()]
            if words:
                return words[0]
    return "this interest"
