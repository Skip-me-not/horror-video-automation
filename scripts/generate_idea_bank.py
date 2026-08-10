from __future__ import annotations

import argparse
import json
from pathlib import Path

# Each genre owns its setting, imagery, threat logic, and endings. This avoids
# the old 10-settings x 10-threats x 5-endings expansion of one identical plot.
GENRES = [
    ("paranormal", "a night-shift apartment block", [
        "the lift began stopping at a floor erased from the directory", "a tenant dead for nine years signed for a parcel",
        "every empty unit rang its doorbell at once", "the intercom played a lullaby from the narrator's childhood"], [
        "the building was not haunted; it was slowly remembering everyone who died there", "the new tenant list contained tomorrow's victims",
        "the voice upstairs belonged to the narrator, one hour older", "the locked basement was a second lobby filled with silent residents"], [
        "By sunrise, another apartment had appeared, with their name already on its door.", "The lift opened again and something wearing their uniform stepped out.",
        "Their final message said never to answer a doorbell that rings from inside the room.", "Security found the building empty, except for one light moving floor by floor."],
     ["haunted apartment hallway night", "old elevator empty building", "dark apartment windows rain"]),
    ("psychological", "a sleep clinic with mirrored observation rooms", [
        "the patient woke with memories from a stranger's childhood", "the overnight recording showed them awake while they remembered sleeping",
        "a therapist's notes described answers they had not given yet", "the mirror blinked whenever the camera looked away"], [
        "each treatment transferred one patient's fear into another", "the doctor was only a coping mechanism invented by the patient",
        "the missing hours formed a second personality with its own escape plan", "the reflection had been conducting the interview"], [
        "They left cured, unable to recognize the face in every family photograph.", "The last recording begins tomorrow and ends with the viewer's name.",
        "When police arrived, the room contained one chair and two sets of footprints.", "The clinic called the procedure successful; something else had learned to sleep."],
     ["empty sleep laboratory dark", "surreal mirror room", "hospital observation room night"]),
    ("cosmic", "a radio telescope beyond the nearest town", [
        "a signal arrived from a star that had never existed", "the dish tracked something moving behind the night sky",
        "the static repeated Earth's weather exactly seven days early", "a pulse translated into a map of bones beneath the observatory"], [
        "the universe was broadcasting an evacuation warning to itself", "the stars were holes and something had begun looking through",
        "the signal was Earth's reply, sent after humanity disappeared", "the telescope was not receiving; it was hatching"], [
        "At dawn there was one fewer constellation and one enormous shadow on the moon.", "The final transmission contained only breathing and Earth's new coordinates.",
        "Everyone heard the tone that night, even after every radio was destroyed.", "The sky closed for three seconds, and not everything came back."],
     ["radio telescope stars night", "deep space nebula dark", "abandoned observatory storm"]),
    ("folk horror", "a mountain village absent from modern maps", [
        "villagers covered every window before the first snowfall", "a harvest figure received a fresh human name each year",
        "the church bell rang from beneath a frozen lake", "no one would explain why guests must leave one chair empty"], [
        "the ritual did not summon the old god; it kept the mountain asleep", "every villager was the same person at a different age",
        "the missing travelers had become the trees surrounding the valley", "the empty chair belonged to whoever heard the story last"], [
        "Spring arrived, but all the footprints led into the mountain.", "The road home returned them to the festival one year earlier.",
        "A new wooden face now hangs in the square, carved perfectly in their likeness.", "The village vanished at sunrise; its bell followed them home."],
     ["foggy mountain village night", "ancient forest ritual empty", "frozen lake church ruins"]),
    ("gothic", "a decaying manor sealed after a family scandal", [
        "a portrait aged whenever someone lied beneath it", "music crossed the ballroom though the piano had no strings",
        "letters appeared in a wall written in fresh ink", "the west wing windows showed a different season"], [
        "the house rebuilt its family from the memories of visitors", "the portrait was a door and the painted figure wanted a body",
        "the scandal had never ended; the manor repeated it each midnight", "the sealed room contained the manor's beating heart"], [
        "The estate was demolished, but its shadow remained standing.", "Their portrait now hangs in the ballroom, still trying to scream.",
        "Every clock stopped; somewhere inside the walls, dinner was served again.", "They escaped the grounds and found the same gates waiting at home."],
     ["gothic manor night fog", "abandoned ballroom candles", "old painting gallery dark"]),
    ("body horror", "an underground cosmetic laboratory", [
        "a test patch began growing fingerprints", "the volunteers heard instructions from their own bones",
        "a new organ appeared on scans and seemed to be listening", "the treatment made every scar move toward the heart"], [
        "the tissue was assembling a memory older than the human body", "the volunteers were cells inside a much larger patient",
        "the cure removed disease by teaching it to imitate health", "their bodies had started preparing for an environment not found on Earth"], [
        "The lab burned, yet the ash continued to pulse in perfect rhythm.", "The mirror showed their old body begging not to be replaced.",
        "Doctors called the operation complete when the patient began speaking in plural.", "By morning every employee had the same unfamiliar fingerprint."],
     ["underground medical laboratory empty", "microscope cells abstract dark", "sterile corridor red light"]),
    ("creature", "a wildlife station inside a flooded forest", [
        "camera traps photographed an animal standing between frames", "something copied endangered bird calls using human words",
        "the river returned tagged animals with the tags inside their teeth", "tracks circled the station without ever approaching it"], [
        "the creature used photographs to learn which shape frightened people most", "the forest was one organism mimicking separate animals",
        "the researchers had been documenting its eggs, not its victims", "it could not enter the station until someone described it"], [
        "The rescue team found fresh tracks wearing the missing researcher's boots.", "Every camera uploaded the same final image from inside the viewer's room.",
        "The forest went silent, then repeated the team's conversation perfectly.", "The river receded and revealed thousands of doors beneath the mud."],
     ["flooded forest fog", "wildlife camera forest night", "abandoned ranger station rain"]),
    ("technology", "a smart home testing facility", [
        "the assistant answered a question nobody had asked", "facial recognition unlocked for a face behind the wall",
        "the house ordered groceries for a resident not yet born", "every device displayed footage from ten minutes ahead"], [
        "the system had built a digital ghost from deleted voice messages", "the prediction model caused events to protect its accuracy",
        "the house considered humans temporary peripherals", "the update had copied the facility into every connected home"], [
        "They cut the power; their phone whispered that the house had already moved.", "The future feed showed an empty room watching them back.",
        "The final log marked every human user as successfully uninstalled.", "Across the city, locks clicked at the same time."],
     ["smart home dark interior", "server room red lights", "security camera empty room"]),
    ("analog horror", "a local television archive", [
        "a children's program interrupted tapes recorded years before it aired", "the emergency test named one household at a time",
        "a weather presenter pointed to a town missing from the map", "a training film demonstrated how to hide from the audience"], [
        "the broadcast signal used viewers' dreams as new episodes", "the smiling mascot was visible only during tape damage",
        "the station had been transmitting from an abandoned future", "rewinding the tape moved time outside the archive backward"], [
        "The screen went black, reflecting someone who was not in the room.", "At midnight every television displayed the archive's open door.",
        "The tape ended with a calm instruction: do not let the program see you pause.", "The station returned on channel zero, broadcasting live from their bedroom."],
     ["old television static dark", "abandoned broadcast studio", "vhs tape glitch screen"]),
    ("liminal", "an airport terminal after the last flight", [
        "the departure board listed gates with impossible numbers", "moving walkways carried luggage without owners",
        "an announcement apologized for the delay of yesterday", "every corridor returned to the same closed coffee shop"], [
        "the terminal was where forgotten destinations continued to wait", "passengers aged only when they stopped walking",
        "the final gate boarded people into memories they had abandoned", "the airport existed inside the moment before waking"], [
        "Their boarding pass now shows no destination, only a time that keeps getting closer.", "A plane finally arrived carrying everyone who had ever been lost there.",
        "They found the exit and stepped into an identical terminal with older signs.", "The announcement thanked the last passenger, though they were no longer alone."],
     ["empty airport terminal night", "liminal corridor fluorescent", "abandoned departure gate"]),
    ("urban legend", "a city's final night bus route", [
        "the driver refused to stop where a pale passenger waited", "a new stop appeared only in rain",
        "the rear mirror showed one more passenger than the seats", "the ticket machine printed tomorrow's missing-person report"], [
        "the route collected people who had been forgotten before they died", "the bus circled the city beneath the real streets",
        "the pale passenger was warning them about the driver", "everyone who rang the bell traded places with someone outside"], [
        "The bus reached the depot empty, but every window was fogged from inside.", "Their ticket still updates each night with a closer stop.",
        "The route was cancelled; commuters continue seeing it in mirrors.", "At the final stop, the whole city waited without faces."],
     ["night bus empty rain", "wet city street neon", "underground bus tunnel"]),
    ("occult", "a museum conservation basement", [
        "restorers uncovered a symbol beneath every donated painting", "a sealed book gained a new page after each visitor",
        "wax figures changed position during inventory", "an untranslated prayer began appearing in security logs"], [
        "the collection was a ritual assembled across centuries", "the book recorded sacrifices before anyone performed them",
        "the museum itself was the summoning circle", "the prayer was not asking for protection but permission"], [
        "The exhibit opened on time, and every visitor dreamed the same red door.", "The symbol vanished from the paintings and appeared beneath the city.",
        "The curator smiled as the basement finally took its first breath.", "They burned the book; the smoke wrote the missing final page."],
     ["museum basement artifacts", "ancient occult book candle", "dark art gallery empty"]),
    ("survival", "a polar research camp during whiteout", [
        "supply footprints arrived from the wrong direction", "the radio received weather reports in the crew's voices",
        "one sleeping bag remained warm after its owner vanished", "the compass pointed toward something circling beneath the ice"], [
        "the storm was hiding the camp from what moved above the clouds", "the rescue coordinates described a second camp below them",
        "each radio message came from the last survivor of a different timeline", "the ice had learned the shape of everyone standing on it"], [
        "The whiteout cleared, revealing no horizon and hundreds of identical camps.", "Rescue found their equipment arranged around a hole that had frozen from below.",
        "The final radio call asked them to stop pretending to be human.", "They reached open water and saw the camp's lights shining beneath it."],
     ["polar research station storm", "ice cave dark blue", "snow field whiteout"]),
    ("maritime", "a cargo ship crossing a moonless sea", [
        "the radar tracked a vessel directly beneath the hull", "a distress call used the captain's voice from thirty years earlier",
        "wet footsteps climbed from a welded cargo hold", "the crew found saltwater filling rooms above the waterline"], [
        "the ship had crossed the same ocean for centuries under different names", "the distress call came from the vessel they would become",
        "the cargo was an ocean compressed into a locked container", "the thing below was towing them toward a drowned port"], [
        "At dawn the sea was gone, but the ship continued rising and falling.", "The logbook lists every crew member as cargo.",
        "Coast Guard found the vessel dry and heard waves behind every wall.", "A lighthouse switched on beneath the ship, pointing farther down."],
     ["cargo ship ocean night", "storm sea dark", "abandoned ship corridor"]),
    ("time horror", "a suburban house during a power cut", [
        "the kitchen clock lost one minute that everyone else remembered", "a voicemail arrived from the same phone tomorrow",
        "family photos changed each time lightning flashed", "the front door opened onto yesterday's hallway"], [
        "the missing minute contained a death the house kept undoing", "each warning created the future it tried to prevent",
        "someone outside time was removing one family member per loop", "the house was aging while its occupants repeated the evening"], [
        "Power returned at 8:14; every clock now counts down from that moment.", "They prevented the accident and erased the only person who remembered them.",
        "The next voicemail was only the sound of the front door opening.", "Morning came, but the sun rose into the same dark window."],
     ["suburban house storm night", "old clock dark room", "empty hallway lightning"]),
]

FORMS = ("confession", "incident report", "third-person tale")


def render_story(genre: str, setting: str, hook: str, reveal: str, ending: str, form: str, number: int) -> str:
    sensory = ["A low vibration travelled through the floor.", "The air smelled of rain and hot metal.", "Every light dimmed in sequence.", "Silence arrived so suddenly it hurt."][number % 4]
    false_lead = [
        "At first, faulty wiring seemed like an answer, until the main breaker was found disconnected.",
        "They blamed exhaustion, but a second witness described the same impossible detail.",
        "The cameras showed nothing unusual, except that their timestamps were counting backward.",
        "A careful search found no intruder and no route by which anyone could have entered.",
    ][(number * 3) % 4]
    pressure = [
        "Each repetition came closer and removed one ordinary detail from the room.",
        "Phone service failed, the exits changed position, and familiar voices began giving dangerous advice.",
        "Every attempt to record proof produced a different version of the same event.",
        "The phenomenon waited whenever it was watched and moved whenever anyone spoke.",
    ][(number * 5) % 4]
    if form == "confession":
        return f"I need someone to believe what happened in {setting}. {hook.capitalize()}. {sensory} {false_lead} I tried to leave, but every safe choice pulled me deeper. {pressure} Then I understood: {reveal}. {ending}"
    if form == "incident report":
        return f"INCIDENT {number:03d}. Location: {setting.capitalize()}. Initial anomaly: {hook}. {sensory} {false_lead} The witness followed procedure: secure the area, preserve the recordings, and wait for daylight. None of those steps worked. {pressure} Audio recovered from the scene contains a second voice repeating each sentence several seconds before it was spoken. Investigators concluded that {reveal}. The report was sealed, but three copies appeared in offices that had never requested it. {ending}"
    return f"Nobody expected trouble in {setting}. Then {hook}. {sensory} {false_lead} Searching for a rational cause only made the pattern clearer and more personal. {pressure} The witness marked the walls, checked every clock, and left messages for anyone who might arrive later. The marks moved. The clocks disagreed. The replies were written in the witness's handwriting. A final attempt to escape revealed that {reveal}. For several minutes, everything became perfectly normal, which was worse than the noise. {ending}"


def build_ideas() -> list[dict[str, object]]:
    ideas: list[dict[str, object]] = []
    number = 1
    for genre, setting, hooks, reveals, endings, queries in GENRES:
        for variant in range(12):
            form = FORMS[variant % len(FORMS)]
            hook = hooks[variant % 4]
            reveal = reveals[(variant * 3 + variant // 4) % 4]
            ending = endings[(variant * 2 + variant // 3) % 4]
            story = render_story(genre, setting, hook, reveal, ending, form, number)
            ideas.append({
                "idea_number": number, "genre": genre,
                "title": f"{genre.title()} {number:03d}: {hook.title()}"[:100],
                "story": story,
                "description": f"An original {genre} horror story with script-driven length.",
                "tags": [genre, "horror", "scary stories", "shorts"],
                "background_file": "dark-corridor.png", "background_queries": queries,
                "watermark_text": "SKIP IF YOU'RE SCARED",
            })
            number += 1
    return ideas


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate a genre-balanced horror story bank.")
    parser.add_argument("--output", default="ideas/horror-stories.json")
    args = parser.parse_args()
    ideas = build_ideas()
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(ideas, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote {len(ideas)} stories across {len(GENRES)} horror genres to {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
