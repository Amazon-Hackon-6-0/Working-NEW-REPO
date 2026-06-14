def anonymous_committee_message(category: str, description: str):
    committee = "Mess Committee" if "mess" in category.lower() or "food" in description.lower() else "Student Affairs"
    return {
        "committee": committee,
        "summary": f"Anonymous student report about {category}: {description}",
        "message": (
            "[CampusBuddy AI - Anonymous Report]\n"
            f"To: {committee}\n"
            f"Issue: {category}\n"
            f"Summary: {description}\n"
            "Privacy: Raw chats are never shared. Only this anonymous confirmed summary is sent.\n"
            "Action requested: Please review and update students through the normal committee channel."
        ),
    }
