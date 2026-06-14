def people_matches(need: str):
    return [
        {
            "alias": "GraphGuide Senior",
            "fit": "Strong fit for DSA graphs, BFS/DFS, and placement prep.",
            "availability": "Tonight after 8 PM",
            "connection_modes": ["Stay anonymous", "Show limited profile", "Reveal identity later by mutual consent"],
        },
        {
            "alias": "Peer Buddy: Graph Sprint",
            "fit": "Practicing graph problems this week and open to one-to-one help.",
            "availability": "Tomorrow afternoon",
            "connection_modes": ["Stay anonymous", "Show limited profile", "Reveal identity later by mutual consent"],
        },
    ]


def group_matches(interest: str):
    return [
        {
            "name": "Chess Circle",
            "members_waiting": 8,
            "invite_preview": "CampusBuddy found students interested in chess. Join anonymously first and reveal your profile only if you choose.",
        },
        {
            "name": "Weekend Board Games",
            "members_waiting": 5,
            "invite_preview": "A smaller casual group for students who prefer low-pressure meetups.",
        },
    ]
