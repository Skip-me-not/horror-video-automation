#!/usr/bin/env python3
"""Build the committed deterministic BL template and metadata catalogs."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

CATEGORY_COUNTS = {
    "breaking_news": 10, "casting": 10, "series_announcement": 8,
    "trailer_release": 6, "release_date": 5, "actor_update": 8,
    "agency_update": 5, "fan_meeting": 5, "award": 5, "interview": 5,
    "viral_moment": 6, "milestone": 5, "comeback": 4, "collaboration": 4,
    "clarification": 4, "controversy_confirmed": 3, "weekly_roundup": 3,
    "general_entertainment": 4,
}

BLUEPRINTS = {
    "breaking_news": (
        ["{actor} fans just got a major official update.", "This BL announcement changed today's conversation.", "{company} has confirmed the news fans were waiting for.", "Stop scrolling: this {country} BL update is now official.", "A new official update about {actor} has arrived."],
        ["{company} announced {event}.", "The confirmed detail is {detail}.", "Here is the context: {context}.", "The source lists {date} as the key date.", "This matters because {achievement}."],
    ),
    "casting": (
        ["A new BL cast combination has officially entered the chat.", "{actor} and {actor_2} are connected to a confirmed new project.", "This casting announcement could shape the next BL season.", "Fans asked who would lead {series}; now there is an answer.", "The cast reveal for {series} is finally here."],
        ["{company} confirmed {actor} and {actor_2} for {series}.", "The project is being produced for {network}.", "The announcement describes {context}.", "The key casting detail is {detail}.", "Production information points to {date}."],
    ),
    "series_announcement": (
        ["A brand-new BL series was just made official.", "{series} may be the next title on your watchlist.", "This {country} BL project has moved from talk to confirmation.", "{company} just unveiled its next BL series.", "Here is what is confirmed about {series}."],
        ["{company} announced {series} for {network}.", "The official premise says {context}.", "The first confirmed production detail is {detail}.", "The announcement names {actor} in the project.", "More information is scheduled for {date}."],
    ),
    "trailer_release": (
        ["The first look at {series} is finally out.", "This trailer just gave BL fans a lot to unpack.", "{series} revealed its tone in one official preview.", "The teaser for {series} has officially landed.", "Watchlist alert: {series} just released new footage."],
        ["{company} released the official trailer through {network}.", "The preview highlights {context}.", "One confirmed detail is {detail}.", "{actor} appears in the newly released footage.", "The source was published on {date}."],
    ),
    "release_date": (
        ["Set a reminder: {series} now has an official release date.", "The wait for {series} has a confirmed end date.", "BL fans can finally put {series} on the calendar.", "{network} just locked in the premiere for {series}.", "This release-date update is now official."],
        ["{series} premieres on {release_date}.", "The confirmed platform or network is {network}.", "{company} included this detail: {detail}.", "The schedule context is {context}.", "The announcement was posted on {date}."],
    ),
    "actor_update": (
        ["{actor} just shared an update fans should know.", "Here is the confirmed context behind {actor}'s latest update.", "A new public update from {actor} is getting attention.", "{actor}'s newest professional move is official.", "This is what actually changed for {actor}."],
        ["The update concerns {event}.", "The official context is {context}.", "The key detail is {detail}.", "{company} published the information on {date}.", "The update marks {achievement}."],
    ),
    "agency_update": (
        ["{company} released an official statement about {actor}.", "An agency update just clarified what happens next.", "This contract or management update is now confirmed.", "Here is what {company} actually announced.", "The official statement changed the timeline for {actor}."],
        ["The statement confirms {event}.", "Its central detail is {detail}.", "The relevant context is {context}.", "The notice was issued on {date}.", "The original statement says: {official_statement}."],
    ),
    "fan_meeting": (
        ["{actor} fans have a new event to plan for.", "A BL fan meeting has officially been announced.", "{venue} is hosting a newly confirmed fan event.", "Here are the confirmed details for {event}.", "This fan meeting announcement includes an important date."],
        ["{event} takes place at {venue}.", "The announced date is {date}.", "{company} says {detail}.", "The event context is {context}.", "Official information names {actor}."],
    ),
    "award": (
        ["{actor} just reached a major awards milestone.", "This BL title is officially in the awards conversation.", "{series} received a confirmed nomination or win.", "The latest award result is in.", "Here is why this recognition matters for {series}."],
        ["{actor} was recognized for {award}.", "The result is {achievement}.", "The official listing includes {series}.", "The supporting context is {context}.", "The result was published on {date}."],
    ),
    "interview": (
        ["One interview answer from {actor} deserves its full context.", "Here is what {actor} actually said in the new interview.", "This quote is circulating, but the context matters.", "{actor} explained a key part of {series}.", "A new interview revealed a confirmed production detail."],
        ["Speaking with {source_name}, {actor} discussed {event}.", "The full context is {context}.", "The confirmed detail is {detail}.", "The published quote is: {official_statement}.", "The interview appeared on {date}."],
    ),
    "viral_moment": (
        ["This public BL moment is everywhere for a reason.", "A moment involving {actor} is drawing huge public attention.", "Here is the verified context behind today's viral clip.", "This event moment moved fast across fan timelines.", "Before sharing this viral moment, know the source."],
        ["The moment happened during {event}.", "The public context is {context}.", "The verifiable detail is {detail}.", "{source_name} documented it on {date}.", "The moment involved {actor_2}."],
    ),
    "milestone": (
        ["{series} just crossed a measurable new milestone.", "The numbers behind this BL achievement are now official.", "{actor} added another confirmed career milestone.", "This ranking result is worth putting in context.", "A new public benchmark has been reached."],
        ["The confirmed achievement is {achievement}.", "The ranking or measurement came from {source_name}.", "The relevant period is {date}.", "The context behind the number is {context}.", "The reported detail is {detail}."],
    ),
    "comeback": (
        ["A BL reunion fans discussed for months is now official.", "{actor} and {actor_2} are working together again.", "This comeback has moved beyond fan speculation.", "A familiar BL team just confirmed a new chapter.", "The reunion update fans wanted is finally sourced."],
        ["{company} announced {event}.", "The returning names are {actor} and {actor_2}.", "The comeback context is {context}.", "The confirmed detail is {detail}.", "The announcement date is {date}."],
    ),
    "collaboration": (
        ["An unexpected BL collaboration is now official.", "{actor} and {actor_2} just announced a joint project.", "Two parts of the BL industry are teaming up.", "This collaboration connects {company} and {network}.", "Here is the verified scope of the new partnership."],
        ["The collaboration centers on {event}.", "{company} confirmed the partnership with {network}.", "The project includes {actor} and {actor_2}.", "The key detail is {detail}.", "Its context is {context}."],
    ),
    "clarification": (
        ["An official correction has changed this BL story.", "Here is the confirmed version after today's clarification.", "A circulating claim now has an official response.", "{company} clarified an important detail about {actor}.", "Before repeating the headline, read the correction."],
        ["The clarification concerns {event}.", "The corrected detail is {detail}.", "The earlier context was {context}.", "The official statement says: {official_statement}.", "It was published on {date}."],
    ),
    "controversy_confirmed": (
        ["A confirmed entertainment dispute now has an official record.", "This sensitive BL news requires facts, not speculation.", "An official statement addressed the current controversy.", "Here is only what reliable sources have confirmed.", "The verified timeline is clearer after a new statement."],
        ["The confirmed event is {event}.", "{company} stated {official_statement}.", "The documented context is {context}.", "The independently reported detail is {detail}.", "The statement date is {date}."],
    ),
    "weekly_roundup": (
        ["Five BL entertainment updates you may have missed this week.", "This week's BL news moved fast; here is the sourced recap.", "From casting to release dates, these are the confirmed updates.", "Your weekly BL entertainment briefing starts now.", "Here is the no-rumor BL roundup for this week."],
        ["First: {context}.", "Next: {detail}.", "The headline event was {event}.", "A key date to remember is {date}.", "The week's milestone was {achievement}."],
    ),
    "general_entertainment": (
        ["This BL entertainment update is worth a closer look.", "Here is today's sourced BL industry briefing.", "A confirmed update is changing the BL calendar.", "This is the context missing from the headline.", "One verified BL update, explained quickly."],
        ["The central event is {event}.", "The relevant company is {company}.", "The verified context is {context}.", "The important detail is {detail}.", "The source published it on {date}."],
    ),
}

REQUIRED = {
    "casting": ["actor", "actor_2", "series", "company"],
    "series_announcement": ["series", "company"], "trailer_release": ["series"],
    "release_date": ["series", "release_date"], "actor_update": ["actor"],
    "agency_update": ["company", "actor"], "fan_meeting": ["event", "date"],
    "award": ["award", "achievement"], "interview": ["actor", "source_name"],
    "viral_moment": ["event", "context"], "milestone": ["achievement", "source_name"],
    "comeback": ["actor", "actor_2", "company"], "collaboration": ["event", "company"],
    "clarification": ["event", "official_statement"],
    "controversy_confirmed": ["event", "official_statement"],
    "weekly_roundup": ["context", "detail", "event"],
    "breaking_news": ["event", "company"], "general_entertainment": ["event", "context"],
}

TITLE_PATTERNS = [
    "{actor} Just Got a Major Official Update", "{actor} & {actor_2} Are Officially Teaming Up",
    "{series} Finally Has a Release Date", "A New BL Pairing Was Just Announced",
    "{company} Just Confirmed It", "The Official Update About {actor}",
    "{series}: What Was Actually Announced", "This {country} BL News Is Now Official",
    "The Cast of {series} Is Taking Shape", "{actor}'s Next Project Is Confirmed",
    "The First Look at {series} Is Here", "Save the Date for {series}",
    "{company}'s New BL Series Explained", "A New Update From {actor}'s Agency",
    "{actor} Fans Have a New Date to Save", "{series} Just Reached a New Milestone",
    "The Verified Context Behind This Viral BL Moment", "What {actor} Actually Said",
    "This Week's Biggest Confirmed BL Updates", "{actor} and {actor_2} Are Working Together Again",
    "An Official Correction Changed This Story", "The Confirmed Timeline Behind {event}",
    "{award}: The Result BL Fans Are Discussing", "{series} Just Released Its Official Trailer",
    "A New BL Collaboration Is Official", "The News Behind {achievement}",
    "{network} Confirmed the Premiere", "Everything Confirmed About {event}",
    "A New Chapter for {actor}", "The Official {series} Announcement in 60 Seconds",
    "This BL Event Has a Confirmed Venue", "The Source Behind Today's BL Headline",
    "{actor}'s Latest Career Move Explained", "A Confirmed Cast Reunion Is Happening",
    "{company} Released a New Statement", "The Release Calendar Just Changed",
    "Why {series} Is Trending Today", "The Numbers Behind {achievement}",
    "A Major BL Award Update Just Arrived", "This Interview Added Important Context",
    "The No-Rumor Version of Today's BL News", "The Official Details Fans Should Know",
    "A New {country} BL Project Is Coming", "The Announcement That Changed This Week",
    "{actor}'s Public Update, With Full Context", "The Next Confirmed BL Premiere",
    "A Fan Meeting Has Officially Been Announced", "The BL Roundup You May Have Missed",
    "The Verified Story Behind the Clip", "One Confirmed BL Update in Under a Minute",
    "{series} Is Officially Moving Forward", "The Latest From {company}",
]

DESCRIPTION_TEMPLATES = [
    "A sourced update about {event}. Read the attribution below before joining the discussion.",
    "Here is the verified context behind {event}, based on {source_name}.",
    "A quick, source-attributed briefing on {series} and the latest confirmed detail.",
    "What was announced, what it means, and where the information came from.",
    "The confirmed facts about {actor}'s latest professional update.",
    "A concise BL entertainment update with the original source linked below.",
    "No rumor framing: only the details supported by the cited source.",
    "The latest official information from {company}, summarized with context.",
    "A fast explanation of today's confirmed {country} BL entertainment news.",
    "The release, cast, and timing details currently confirmed for {series}.",
    "A source-first recap of the announcement BL fans are discussing.",
    "The public facts and timeline behind this entertainment update.",
    "A quick breakdown of {achievement} and why it matters.",
    "The verified context behind a widely shared public moment.",
    "A clear summary of an agency statement, without private speculation.",
    "The important date, venue, and official source for this fan event.",
    "A short recap of this week's confirmed BL announcements.",
    "The full context behind a quote circulating from a public interview.",
    "A factual correction and the official statement that supports it.",
    "BL entertainment news with transparent source attribution and story ID.",
]

CTAS = [
    "What do you think about this confirmed update?", "Is this going on your watchlist?",
    "Which detail matters most to you?", "Will you be watching on release day?",
    "Who else should be included in the next update?", "Did this announcement surprise you?",
    "Save this so you remember the date.", "Share your take without spreading rumors.",
    "Which confirmed update should we explain next?", "Follow for source-attributed BL news.",
]

HASHTAGS = [
    ["#BL", "#BLSeries", "#EntertainmentNews", "#Shorts"],
    ["#ThaiBL", "#BLUpdate", "#SeriesNews", "#Shorts"],
    ["#KoreanBL", "#KBL", "#BLNews", "#Shorts"],
    ["#JapaneseBL", "#JBL", "#Entertainment", "#Shorts"],
    ["#TaiwaneseBL", "#BLDrama", "#News", "#Shorts"],
    ["#BLActors", "#CastingNews", "#BLFans", "#Shorts"],
    ["#BLTrailer", "#NewSeries", "#Watchlist", "#Shorts"],
    ["#BLRelease", "#DramaUpdate", "#ReleaseDate", "#Shorts"],
    ["#CelebrityNews", "#BLCommunity", "#VerifiedNews", "#Shorts"],
    ["#Lululala", "#BLRoundup", "#EntertainmentUpdate", "#Shorts"],
]


def build_templates() -> list[dict]:
    templates = []
    layout_index = 0
    caption_ids = ["bold_center", "minimal_bottom", "news_lower_third", "keyword_emphasis", "clean_white", "large_hook"]
    music = ["news", "upbeat", "emotional", "elegant", "neutral"]
    for category, count in CATEGORY_COUNTS.items():
        hooks, lines = BLUEPRINTS[category]
        for index in range(count):
            rotation = index % len(lines)
            body = [lines[(rotation + offset) % len(lines)] for offset in range(4)]
            templates.append({
                "id": f"{category}_{index + 1:03d}", "category": category,
                "duration_target": 36 + ((index * 7 + len(category)) % 25),
                "hook_pattern": f"{category}_hook_{index % len(hooks) + 1}",
                "hook": hooks[index % len(hooks)], "body": body,
                "cta": CTAS[(index + len(category)) % len(CTAS)],
                "visual_style": ["news_fast", "editorial_clean", "warm_update", "timeline_focus", "headline_first"][index % 5],
                "scene_layout": f"layout_{layout_index % 18 + 1:02d}",
                "music_profile": music[(index + layout_index) % len(music)],
                "caption_profile": caption_ids[(index * 2 + layout_index) % len(caption_ids)],
                "headline_style": ["direct", "question", "date_led", "source_led", "context_led"][index % 5],
                "transition_ms": 120 + (index % 5) * 40,
                "required_fields": REQUIRED[category],
                "allowed_source_types": ["official", "reputable_media", "social_verified"],
            })
            layout_index += 1
    return templates


def main() -> None:
    target = ROOT / "templates"
    target.mkdir(parents=True, exist_ok=True)
    templates = build_templates()
    manifest = {"version": 2, "template_count": len(templates), "category_counts": CATEGORY_COUNTS, "templates": templates}
    (target / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    metadata = {"title_patterns": TITLE_PATTERNS, "description_templates": DESCRIPTION_TEMPLATES, "cta_patterns": CTAS, "hashtag_sets": HASHTAGS}
    (target / "metadata.json").write_text(json.dumps(metadata, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote {len(templates)} templates across {len(CATEGORY_COUNTS)} categories")


if __name__ == "__main__":
    main()
