#!/usr/bin/env python3
"""Expand hand-curated seeds into a broad, deterministic 500-story library."""

from __future__ import annotations

import hashlib
import random
from typing import Any


LENSES = [
    ("Maya", "she", 22, "6:17 AM", 11), ("Daniel", "he", 27, "11:48 PM", 9),
    ("Ari", "unnamed", 24, "2:06 AM", 14), ("Leah", "she", 29, "7:32 PM", 6),
    ("Marcus", "he", 31, "5:41 AM", 18), ("Nina", "she", 20, "12:23 PM", 7),
    ("Eli", "he", 26, "9:14 PM", 12), ("Sam", "unnamed", 23, "4:39 PM", 16),
    ("Chloe", "she", 28, "8:03 AM", 5), ("Owen", "he", 25, "1:27 AM", 21),
    ("Iris", "she", 32, "6:52 PM", 8), ("Theo", "he", 21, "10:11 AM", 13),
    ("Rina", "she", 30, "3:44 PM", 17), ("Alex", "unnamed", 24, "7:09 AM", 10),
    ("Jules", "unnamed", 27, "11:36 AM", 19), ("Lena", "she", 23, "8:58 PM", 4),
    ("Caleb", "he", 29, "5:26 PM", 15), ("Mina", "she", 26, "12:42 AM", 22),
    ("Jonah", "he", 28, "9:37 AM", 3), ("Rae", "unnamed", 25, "4:18 AM", 20),
]


SCENARIOS = [
    ("portfolio", "career fear", "an aspiring designer", "closed the portfolio tab before sending it", "kept polishing colors nobody had reviewed", "another application deadline passed", "sent one imperfect page to a working designer", "asked for one specific criticism each Friday", "three revisions came from real feedback", "The portfolio improved only after it became visible", "Unsent Portfolio", "designer laptop portfolio", "design feedback video call"),
    ("coding", "feeling behind", "a self-taught developer", "deleted the same broken project for the third time", "watched tutorials instead of reading the error", "the unfinished app became proof of imagined failure", "copied the error into a notebook and solved one line", "committed one small fix before every new lesson", "the app finally opened without crashing", "Skill appeared when confusion stopped being an exit", "Broken App", "developer code error laptop", "working app screen celebration"),
    ("debt", "money shame", "a worker facing debt", "ignored the red banking notification again", "called every small purchase harmless", "interest kept charging for the comfort of not looking", "listed every balance on one sheet of paper", "paid the smallest amount every payday", "one account reached zero before life felt richer", "Control arrived earlier than wealth", "Red Notification", "banking alert phone bills", "debt payment notebook relief"),
    ("fitness", "starting over", "a beginner runner", "turned around before reaching the first corner", "compared today's lungs with an old photograph", "embarrassment kept the shoes unusually clean", "walked the block without recording the distance", "returned before motivation had another opinion", "the route became longer without a dramatic promise", "Consistency began too small for pride to notice", "Clean Running Shoes", "beginner running shoes street", "morning walk progress"),
    ("loneliness", "social courage", "a newcomer", "ate beside the same empty chair", "memorized strangers' routines instead of introducing themselves", "quiet evenings made the new city feel temporary", "asked one person if the seat was free", "returned to the same table the following week", "a familiar hello became a weekend invitation", "Belonging started as one interruptible sentence", "Empty Chair", "person alone cafe chair", "new friends cafe conversation"),
    ("exam", "academic failure", "a struggling student", "folded another failed test into a backpack", "highlighted pages without testing what was remembered", "long study hours produced the same red score", "answered ten questions before opening the notes", "tracked mistakes by type instead of hiding them", "the next score rose because weak spots became visible", "Failure became useful when it turned specific", "Folded Test", "student failed exam paper", "student practice questions desk"),
    ("job_search", "rejection", "an unemployed graduate", "received rejection number twenty-one", "rewrote the résumé without asking why interviews failed", "silence made every application feel identical", "sent one recruiter a short request for feedback", "practiced the weak interview answer aloud", "the next conversation lasted past the first round", "A no became direction instead of identity", "Rejection Folder", "job rejection email laptop", "job interview practice mirror"),
    ("small_business", "slow progress", "a market seller", "packed every unsold candle back into a box", "changed prices weekly without speaking to buyers", "guessing made a quiet stall feel personal", "asked five visitors what stopped the purchase", "changed the scent labels instead of the dream", "the first repeat customer returned with a friend", "Listening did what hoping could not", "Unsold Box", "market stall unsold products", "happy customer market seller"),
    ("public_speaking", "fear of judgment", "a quiet employee", "muted the microphone during another good idea", "edited the sentence until the meeting had moved on", "silence protected comfort and erased contribution", "said one prepared sentence before fear settled", "volunteered for the next two-minute update", "their voice shook less because it was finally used", "Confidence followed evidence from speaking", "Muted Microphone", "online meeting muted microphone", "employee speaking presentation"),
    ("burnout", "toxic productivity", "an exhausted freelancer", "completed sixteen tiny tasks and avoided the important one", "used a full checklist to disguise fear", "busyness ended each day without meaningful movement", "hid the list and opened the difficult proposal", "worked on it for one protected hour", "an imperfect draft reached the client", "Priority felt worse than productivity and worked better", "Sixteen Distractions", "busy checklist freelancer", "sending proposal laptop"),
    ("phone_addiction", "lost attention", "a tired commuter", "unlocked the phone before the alarm stopped", "filled every quiet second with somebody else's updates", "personal plans stayed blurry while feeds stayed endless", "removed social apps from the home screen", "read two pages during each commute", "a finished book replaced hours they could not remember", "Attention returned when friction changed sides", "First Unlock", "phone alarm morning scrolling", "reading book train commute"),
    ("creative_block", "perfectionism", "an aspiring writer", "renamed an empty document for the eighth time", "planned a perfect opening instead of writing a bad one", "the untouched page preserved talent and produced nothing", "typed one deliberately ugly paragraph", "kept drafting without using backspace for ten minutes", "the first chapter became editable", "Bad work opened a door perfection kept locked", "Eighth Filename", "writer blank document night", "writer drafting manuscript"),
    ("breakup", "self abandonment", "someone after a breakup", "checked an old message before getting out of bed", "treated every memory like evidence to return", "the future stayed arranged around somebody absent", "moved one shared photograph into a drawer", "planned one Saturday that required no permission", "the empty hours slowly became personal space", "Healing began when absence stopped setting the schedule", "Old Message", "sad person old phone message", "person solo weekend outdoors"),
    ("family_pressure", "borrowed expectations", "a dutiful graduate", "accepted an interview for a life they did not want", "called obedience gratitude and anxiety ambition", "every achievement made the wrong future more expensive", "wrote what they wanted without showing anyone", "declined one opportunity and kept one honest choice", "disappointment arrived but relief stayed longer", "Respect did not require surrendering authorship", "Borrowed Future", "graduate family expectations", "person choosing own career path"),
    ("habit_restart", "self trust", "a serial restarter", "missed one day and nearly abandoned the month", "used perfect streaks as the price of continuing", "fresh calendars collected promises old ones had heard", "made one rule to never miss twice", "returned the day after every imperfect day", "uneven checkmarks finally crossed three months", "Trust grew from returning, not remaining flawless", "Second Day", "missed habit tracker calendar", "consistent habit checkmarks"),
    ("learning_music", "talent comparison", "a beginner pianist", "closed the piano after hearing a flawless performance", "compared a first lesson with someone else's thousandth hour", "protecting the idea of talent prevented practice", "repeated four difficult measures slowly", "recorded mistakes instead of deleting them", "the passage became recognizable weeks later", "Talent looked different after counting survived mistakes", "Four Measures", "beginner pianist discouraged", "piano slow practice metronome"),
    ("boundary", "people pleasing", "a reliable coworker", "agreed to another favor while already exhausted", "confused immediate approval with being valued", "resentment grew behind every helpful smile", "answered one request with an honest no", "left one evening empty without explaining it", "the team found another solution in minutes", "A believable yes required the existence of no", "Honest No", "overworked coworker requests", "calm evening boundary"),
    ("sleep", "late-night avoidance", "a person rebuilding mornings", "watched sunrise through a phone screen again", "called the scrolling rest while waking exhausted", "each late start made the day feel already lost", "moved the charger outside the bedroom", "put shoes beside the door for a ten-minute walk", "mornings became usable before they became perfect", "The day changed after the night lost one habit", "Outside Charger", "late night phone sunrise", "morning walk sunrise"),
    ("promotion", "career comparison", "an overlooked analyst", "muted the group chat after another promotion post", "counted other people's titles instead of missing skills", "comparison made vague disappointment feel permanent", "asked a manager which result would change the next review", "built one visible project around that answer", "the next conversation contained evidence, not envy", "Direction replaced the scoreboard", "Muted Group Chat", "promotion social media phone", "analyst presenting project"),
    ("moving_home", "fear of change", "a first-time renter", "left the last moving box sealed for six weeks", "kept the room temporary to avoid admitting change", "an unpacked home made every evening feel borrowed", "hung one photograph above the empty desk", "invited one friend before everything looked finished", "the apartment began collecting ordinary memories", "Home appeared through use, not readiness", "Last Moving Box", "sealed moving box apartment", "friends new apartment dinner"),
    ("grief", "moving forward guilt", "a grieving sibling", "laughed once and immediately felt disloyal", "treated pain as the final proof of love", "good moments arrived carrying unnecessary shame", "wrote the memory behind the laughter down", "allowed joy and missing someone into the same day", "the story stayed even when the guilt softened", "Love did not require permanent suffering", "Guilty Laugh", "grieving person photograph", "memory journal sunlight"),
    ("language", "embarrassment", "an immigrant learner", "ordered lunch by pointing at the menu again", "studied grammar privately to avoid public mistakes", "perfect exercises did not create a usable voice", "asked the cashier one memorized question", "used one new sentence in public each day", "a stranger finally answered without switching languages", "Fluency began with imperfect exposure", "Pointed Menu", "person ordering food shy", "language conversation cafe"),
    ("savings", "impulse spending", "a young worker", "opened a delivery app after promising to save", "called convenience a reward for surviving work", "small comforts repeatedly borrowed from bigger freedom", "created a separate account without a payment card", "moved a little money there on payday", "the balance became enough for one emergency", "Freedom grew where impulse could not easily reach", "Cardless Account", "food delivery app spending", "savings account phone"),
    ("friendship", "outgrowing people", "a loyal friend", "left another gathering feeling smaller", "kept confusing shared history with present safety", "old jokes had become permission for disrespect", "declined the next invitation without inventing an excuse", "used the evening to call someone who listened", "distance revealed which connection could breathe", "Longevity was not the same as loyalty", "Smaller After", "uncomfortable friend gathering", "supportive phone conversation"),
    ("side_project", "waiting for time", "a busy parent", "found the sketchbook under another pile of laundry", "waited for a free weekend that never appeared", "the private idea aged while responsibilities stayed real", "drew for twelve minutes before the house woke", "protected the same tiny window three mornings a week", "a complete series formed across ordinary weeks", "A dream survived by fitting inside real life", "Twelve Minutes", "sketchbook laundry busy home", "parent drawing early morning"),
]


PILLARS = ["transformation", "failure_comeback", "relatable_pain", "future_self", "disappear_rebuild", "hard_truth_story"]
HOOK_TYPES = ["specific_time", "confession", "object_detail", "money_stakes", "relatable_moment"]

BEAT_TEMPLATES = [
    [
        "For weeks, {subject} {clause}.", "Most days ended the same way: {subject} {clause}.",
        "Behind the excuses, {subject} {clause}.", "Nobody watching knew that {subject} {clause}.",
        "The private routine was predictable—{subject} {clause}.",
    ],
    [
        "The hidden cost was simple: {clause}.", "What looked harmless kept producing one result: {clause}.",
        "Meanwhile, {clause}.", "The price never appeared on a receipt; {clause}.",
        "Avoidance stayed quiet while {clause}.",
    ],
    [
        "Waiting felt safer, but day {number} looked exactly like day one.",
        "By attempt {number}, preparation had become a comfortable hiding place.",
        "Nothing collapsed dramatically; another {number} days simply disappeared.",
        "The calendar reached day {number} without producing new evidence.",
        "Safety won for {number} days and changed nothing.",
    ],
    [
        "Then {subject} {clause}.", "On an ordinary {day}, {subject} finally {clause}.",
        "The turning point looked unimpressive: {subject} {clause}.",
        "Instead of another promise, {subject} {clause}.",
        "At {clock}, the pattern broke when {subject} {clause}.",
    ],
    [
        "The next step was smaller: {subject} {clause}.", "No grand routine followed; {subject} simply {clause}.",
        "Before confidence arrived, {subject} {clause}.", "The experiment continued when {subject} {clause}.",
        "On difficult days, the only rule was this: {subject} {clause}.",
    ],
    [
        "Nothing looked dramatic until {clause}.", "The first honest evidence appeared when {clause}.",
        "Weeks later, the quiet repetition had an outcome: {clause}.", "Then something measurable happened—{clause}.",
        "The change became impossible to dismiss after {clause}.",
    ],
    [
        "{clause}.", "That was the lesson: {clause}.", "The result left one hard truth: {clause}.",
        "No miracle arrived. {clause}.", "Looking back, the meaning was clear: {clause}.",
    ],
]

DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def varied_beat(beat_index: int, clause: str, *, subject: str, number: int, clock: str, seed: str) -> str:
    digest = int(hashlib.sha256(seed.encode("utf-8")).hexdigest(), 16)
    chooser = random.Random(digest)
    template = chooser.choice(BEAT_TEMPLATES[beat_index])
    return template.format(
        subject=subject,
        clause=clause[0].lower() + clause[1:],
        number=number,
        clock=clock,
        day=DAYS[digest % len(DAYS)],
    )


def expand_stories(seed_stories: list[dict[str, Any]], target: int = 500) -> list[dict[str, Any]]:
    stories = list(seed_stories)
    next_id = len(stories) + 1
    for scenario_index, scenario in enumerate(SCENARIOS):
        (topic, theme, protagonist, failure, hiding, cost, action, repeat, evidence,
         payoff, title_object, hook_visual, end_visual) = scenario
        for lens_index, (name, perspective, age, clock, count) in enumerate(LENSES):
            if len(stories) >= target:
                return stories
            pillar = PILLARS[(scenario_index + lens_index) % len(PILLARS)]
            subject = name
            number = count + scenario_index
            hooks = [
                f"At {clock}, {subject} {failure}.",
                f"At {age}, {subject} had repeated the same escape {number} times.",
                f"The {title_object.lower()} had become {subject}'s quiet evidence of delay.",
            ]
            visual_base = hook_visual
            phases = ["problem", "problem", "problem", "turn", "turn", "turn", "payoff"]
            clauses = [hiding, cost, "unused", action, repeat, evidence, payoff]
            texts = [
                varied_beat(
                    beat_index, clause, subject=subject, number=number, clock=clock,
                    seed=f"{topic}|{name}|{beat_index}",
                )
                for beat_index, clause in enumerate(clauses)
            ]
            visuals = [visual_base, visual_base, visual_base, visual_base, visual_base, end_visual, end_visual]
            stories.append({
                "id": f"s{next_id:03d}", "pillar": pillar, "topic": topic,
                "theme": theme, "perspective": perspective, "protagonist": protagonist,
                "hook_type": HOOK_TYPES[(scenario_index + lens_index) % len(HOOK_TYPES)],
                "hook_candidates": hooks, "hook_visual": hook_visual,
                "beats": [
                    {"phase": phase, "text": text, "visual_search": visual}
                    for phase, text, visual in zip(phases, texts, visuals, strict=True)
                ],
                "title_candidates": [f"{subject} and the {title_object}", f"Day {number}: The {title_object}"],
                "ending_concept": payoff.casefold(),
                "key_phrases": [title_object.casefold(), action],
                "music_searches": ["sad reflective piano", "hopeful emotional piano"],
            })
            next_id += 1
    if len(stories) < target:
        raise RuntimeError(f"Only generated {len(stories)} stories; target is {target}")
    return stories
