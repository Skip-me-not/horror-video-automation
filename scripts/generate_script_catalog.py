#!/usr/bin/env python3
"""Build 500 original motivation scripts from curated, license-free phrase sets."""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "data" / "quotes.json"
STATE_OUTPUT = ROOT / "data" / "state.json"

QUOTE_ENDINGS = (
    "builds a future that excuses cannot reach",
    "turns uncertainty into a direction you can follow",
    "gives tomorrow a stronger place to begin",
    "creates evidence that you can trust yourself again",
    "moves your life farther than waiting for perfect conditions",
    "becomes quiet proof that meaningful change is already happening",
)

ACTION_ENDINGS = (
    "and give it ten focused minutes before the day gets noisy",
    "then make the next useful move before you reconsider",
    "and record the result so progress becomes visible",
    "then remove one obstacle that makes tomorrow harder",
    "and finish a small version before seeking a perfect one",
    "then repeat it at the same time tomorrow",
)

CATEGORY_PARTS = {
    "discipline": {
        "subjects": (
            "A promise kept when motivation is absent",
            "One focused hour protected from distraction",
            "A difficult task finished before comfort takes over",
            "The routine you follow on an ordinary morning",
            "A clear boundary around your most important work",
            "One honest decision made without negotiating",
            "The standard you keep when nobody is watching",
            "A small responsibility completed without applause",
            "The first useful action after the alarm rings",
            "A distraction refused at the right moment",
            "The work you complete despite an imperfect mood",
            "A plan reduced to one nonnegotiable step",
            "The habit you protect during a difficult week",
            "One deliberate choice repeated without drama",
        ),
        "actions": (
            "Choose the task you have delayed most",
            "Protect one hour from every notification",
            "Begin with the duty you usually avoid",
            "Write one rule your morning must follow",
            "Close the easiest door to distraction",
            "Decide what will be finished before resting",
            "Keep one promise that nobody else can see",
            "Complete the smallest neglected responsibility",
            "Place tomorrow's first task where you can see it",
            "Say no to one impulse that steals your attention",
            "Work through the first wave of resistance",
            "Reduce today's plan to one essential step",
            "Schedule the habit that matters most",
            "Make one disciplined choice without announcing it",
        ),
        "searches": ("focused athlete training", "morning routine sunrise", "person working alone", "mountain trail determination"),
    },
    "success": {
        "subjects": (
            "A useful skill practiced beyond the beginner stage",
            "One thoughtful risk taken with preparation",
            "A long goal divided into visible milestones",
            "The lesson collected from an honest failure",
            "A quiet improvement repeated after others stop",
            "One opportunity met with practiced ability",
            "A strong reputation built through dependable work",
            "The patience to improve before demanding recognition",
            "A problem studied longer than the first frustration",
            "One clear priority protected from shallow urgency",
            "A brave attempt followed by careful reflection",
            "The value you create before asking for reward",
            "A meaningful goal supported by measurable habits",
            "The courage to begin before certainty arrives",
        ),
        "actions": (
            "Practice the skill your next opportunity will require",
            "Take one prepared risk you have been postponing",
            "Turn your largest goal into today's milestone",
            "Write the lesson hidden inside your latest failure",
            "Improve one detail that most people overlook",
            "Prepare today for an opportunity that has not arrived",
            "Deliver one piece of work exactly as promised",
            "Measure improvement before asking for recognition",
            "Stay with one problem past the first frustration",
            "Protect your highest priority from false urgency",
            "Review one brave attempt without judging yourself",
            "Create something useful before seeking a reward",
            "Attach one measurable habit to your main goal",
            "Begin one meaningful project with incomplete certainty",
        ),
        "searches": ("entrepreneur working focused", "city sunrise ambition", "craftsperson detailed work", "runner reaching mountain summit"),
    },
    "healing": {
        "subjects": (
            "A painful memory met with patient understanding",
            "One gentle boundary placed around your peace",
            "The rest you accept without calling it weakness",
            "A difficult feeling allowed to pass without control",
            "The kindness you offer your unfinished self",
            "One honest conversation with someone safe",
            "A heavy expectation released at the right time",
            "The space you create between hurt and reaction",
            "A quiet morning that asks nothing from you",
            "One old story questioned with compassion",
            "The courage to seek help before breaking alone",
            "A small return to something that makes you feel alive",
            "The forgiveness that frees you from constant replay",
            "One peaceful choice made after a painful season",
        ),
        "actions": (
            "Name the feeling you have been avoiding",
            "Set one gentle boundary around your peace",
            "Give your body the rest it has requested",
            "Let one difficult emotion exist without fixing it",
            "Speak to yourself as you would to a tired friend",
            "Share one honest sentence with someone safe",
            "Release one expectation that keeps hurting you",
            "Pause before answering from an old wound",
            "Create ten quiet minutes with no demand",
            "Question one painful story you repeat about yourself",
            "Ask for support before the weight becomes unbearable",
            "Return briefly to something that once brought joy",
            "Stop replaying one moment you cannot change",
            "Choose the response that protects your peace",
        ),
        "searches": ("calm ocean sunrise", "person walking peaceful forest", "soft rain window", "quiet lake reflection"),
    },
    "confidence": {
        "subjects": (
            "A small promise to yourself kept completely",
            "One opinion expressed without shrinking your voice",
            "The skill you practice instead of pretending certainty",
            "A mistake accepted without attacking your worth",
            "The room you enter without asking permission to belong",
            "One clear no spoken with calm respect",
            "The evidence collected from challenges already survived",
            "A comparison replaced by attention to your own path",
            "The imperfect work you allow others to see",
            "One strength named without apology",
            "The courage to learn where others might notice",
            "A decision made from values instead of approval",
            "The posture of someone willing to try again",
            "One truthful compliment you finally accept",
        ),
        "actions": (
            "Keep one promise you made only to yourself",
            "Express one useful opinion without softening it",
            "Practice the skill behind the confidence you want",
            "Correct one mistake without insulting yourself",
            "Enter one room as though you already belong",
            "Say one respectful no without adding an excuse",
            "List three challenges you have already survived",
            "Replace one comparison with your next personal step",
            "Share one piece of work before it feels perfect",
            "Name one strength without minimizing it",
            "Learn openly instead of hiding inexperience",
            "Make one decision without requesting unnecessary approval",
            "Try again with your shoulders relaxed",
            "Accept one sincere compliment without rejecting it",
        ),
        "searches": ("confident person city", "woman mountain overlook", "speaker empty stage", "person training boxing"),
    },
    "growth": {
        "subjects": (
            "A familiar belief examined with new evidence",
            "One uncomfortable lesson welcomed without defense",
            "The beginner stage accepted as part of mastery",
            "A better question asked after the old answer fails",
            "The identity you outgrow without hating your past",
            "One new environment that challenges your habits",
            "A weakness studied instead of hidden",
            "The feedback you use without surrendering your judgment",
            "A curious mind kept open during disagreement",
            "One outdated goal released for a truer direction",
            "The patience to become capable before becoming visible",
            "A difficult season converted into useful wisdom",
            "The choice to update your plan without abandoning yourself",
            "One question that expands the life you can imagine",
        ),
        "actions": (
            "Test one familiar belief against new evidence",
            "Write the lesson inside your latest discomfort",
            "Practice one skill badly enough to begin learning",
            "Ask a better question about a stubborn problem",
            "Release one identity that no longer fits",
            "Spend time in one environment that stretches you",
            "Study one weakness without trying to hide it",
            "Use one piece of feedback while keeping your judgment",
            "Listen for understanding during one disagreement",
            "Replace one outdated goal with a truer direction",
            "Build capability before seeking visibility",
            "Extract one useful principle from a difficult season",
            "Update one plan that reality has outgrown",
            "Ask what becomes possible if fear is not in charge",
        ),
        "searches": ("seedling sunlight growth", "person learning workshop", "winding road mountains", "student reading window"),
    },
    "consistency": {
        "subjects": (
            "A modest action repeated after excitement disappears",
            "One daily page written without waiting for inspiration",
            "The pace you can maintain during an ordinary month",
            "A simple system that survives a difficult day",
            "The return you make after missing one attempt",
            "One small improvement protected from impatience",
            "The calendar that records effort instead of intention",
            "A steady rhythm chosen over a dramatic beginning",
            "The minimum useful action completed on a tired day",
            "One routine adjusted instead of completely abandoned",
            "The patience to let repeated effort become visible",
            "A boring practice treated as part of the dream",
            "The next repetition completed without measuring applause",
            "One dependable step taken at the agreed time",
        ),
        "actions": (
            "Repeat one modest action after excitement fades",
            "Write one useful page without waiting for inspiration",
            "Choose a pace you could maintain for a month",
            "Simplify one system until it survives a difficult day",
            "Return today without punishing yesterday's missed attempt",
            "Protect one small improvement from impatience",
            "Mark completed effort on a visible calendar",
            "Choose a steady rhythm over a dramatic restart",
            "Complete the minimum useful action on a tired day",
            "Adjust one routine instead of abandoning it",
            "Let repeated effort remain invisible a little longer",
            "Treat one boring practice as part of the dream",
            "Complete the next repetition without checking applause",
            "Take one dependable step at the time you chose",
        ),
        "searches": ("daily journal coffee", "runner training road", "calendar habit tracking", "sunrise walking routine"),
    },
}


def build_catalog() -> list[dict[str, str]]:
    entries: list[dict[str, str]] = []
    for category, parts in CATEGORY_PARTS.items():
        for subject_index, subject in enumerate(parts["subjects"]):
            for ending_index, ending in enumerate(QUOTE_ENDINGS):
                action = parts["actions"][subject_index]
                entry_number = len(entries) + 1
                entries.append(
                    {
                        "id": f"m{entry_number:03d}",
                        "quote": f"{subject} {ending}.",
                        "insight": f"{action} {ACTION_ENDINGS[ending_index]}.",
                        "pexels_search": parts["searches"][(subject_index + ending_index) % len(parts["searches"])],
                        "category": category,
                    }
                )
    entries = entries[:500]
    if len(entries) != 500:
        raise RuntimeError(f"Expected 500 scripts, generated {len(entries)}")
    if len({entry["quote"].casefold() for entry in entries}) != len(entries):
        raise RuntimeError("Generated duplicate quotes")
    if len({entry["insight"].casefold() for entry in entries}) != len(entries):
        raise RuntimeError("Generated duplicate insights")
    return entries


def main() -> None:
    entries = build_catalog()
    OUTPUT.write_text(json.dumps(entries, indent=2) + "\n", encoding="utf-8")
    STATE_OUTPUT.write_text(
        json.dumps({"version": 1, "cycle": 1, "used_ids": [], "history": []}, indent=2)
        + "\n",
        encoding="utf-8",
    )
    print(f"Wrote {len(entries)} original scripts to {OUTPUT}")


if __name__ == "__main__":
    main()
