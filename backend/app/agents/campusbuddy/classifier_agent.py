def classify_student_message(message: str) -> str:
    text = message.lower()
    offer_help_phrases = [
        "i am good at",
        "i am very good at",
        "i know",
        "i can help",
        "i can teach",
        "i can mentor",
        "i am strong in",
        "i have experience in",
    ]
    if any(phrase in text for phrase in offer_help_phrases):
        return "offer_help"
    if any(word in text for word in ["mess", "food", "wifi", "wi-fi", "hostel", "water", "electricity"]):
        return "campus_issue"
    if any(word in text for word in ["dsa", "graphs", "graph", "exam", "assignment", "placement", "study"]):
        return "academic_help"
    if any(word in text for word in ["chess", "football", "music", "anime", "gym", "coding", "group"]):
        return "community_group"
    if any(word in text for word in ["stress", "lonely", "friends", "friend", "anxious", "sad", "overwhelmed"]):
        return "personal_support"
    return "general"
