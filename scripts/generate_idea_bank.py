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
    ("medical", "an emergency ward sealed for quarantine", [
        "every recovered patient forgot the same person", "an empty bed produced a perfect heartbeat on three monitors",
        "blood samples spelled room numbers as they separated", "the night surgeon received instructions in their own handwriting"], [
        "the cure worked by moving each illness into an erased human life", "the ward was growing a patient from discarded medical records",
        "the monitors were measuring a second hospital occupying the same rooms", "the operation had already happened and everyone present was donated tissue"], [
        "At discharge, the nurse called their family and nobody recognized the name.", "The empty bed was wheeled away, leaving fresh footprints beneath the sheet.",
        "The hospital reopened with one extra floor and no way to reach it.", "Their final scan listed every organ as belonging to tomorrow's patient."],
     ["empty emergency ward night", "dark hospital monitors", "sealed medical corridor"]),
    ("environmental", "a weather station inside a dead forest", [
        "rain fell upward only above polluted ground", "the wind repeated the names of extinct animals",
        "weather radar showed a storm shaped like a nervous system", "trees leaned away from anyone carrying plastic"], [
        "the atmosphere had developed an immune response to human settlement", "the forest fire was cauterizing something beneath the soil",
        "every forecast taught the storm a new human sense", "the ecosystem was rebuilding predators from industrial waste"], [
        "The forecast ended with a warning addressed to the entire species.", "Clear skies returned, but no bird would fly above the town.",
        "The storm followed their car without moving across the map.", "By morning every plastic object in the city was warm and breathing."],
     ["dead forest storm empty", "weather radar anomaly", "abandoned climate station"]),
    ("crime", "a police evidence warehouse after midnight", [
        "evidence arrived twenty-four hours before each crime", "a sealed confession changed names whenever it was read",
        "fingerprints from one case appeared at every unsolved scene", "a murder weapon called the warehouse phone"], [
        "future trials were manufacturing crimes to justify their verdicts", "the evidence belonged to victims who had successfully escaped their deaths",
        "the warehouse was choosing innocent people to complete abandoned cases", "the caller was the investigator after years of following the evidence backward"], [
        "The next evidence bag contained the investigator's keys and fresh blood.", "Every cold case closed at once under the same impossible name.",
        "The confession printed one final sentence while they watched: YOU BELIEVED IT.", "Police found the warehouse empty and every shelf labelled with tomorrow's date."],
     ["empty evidence warehouse", "sealed evidence bags dark", "forensic archive corridor"]),
    ("social", "a perfect gated community during a blackout", [
        "every helpful neighbour received someone else's good luck", "unpopular residents vanished from group photographs",
        "compliments left bruises shaped like fingerprints", "the community app assigned one household to blame each night"], [
        "collective approval had become a predator feeding on isolation", "the neighbourhood transferred every consequence to whoever had the fewest friends",
        "the residents were copies produced whenever the original broke a social rule", "the app was not ranking people; it was deciding who counted as real"], [
        "At sunrise, a whole new city sent them friend requests at once.", "Their house remained, but every neighbour insisted the street had always been empty.",
        "The app congratulated the final resident for achieving perfect agreement.", "Family photos updated with smiling strangers standing in their place."],
     ["empty gated community night", "identical suburban houses dark", "community notice board rain"]),
    ("alien contact", "a translation laboratory beneath an airfield", [
        "the visitors asked permission before making every harmless movement", "a signal translated itself differently for each listener",
        "the recovered object answered questions with childhood memories", "every device displayed the same polite request"], [
        "the visitors could not invade a species capable of refusing consistently", "the translation was editing human language to remove the word no",
        "the object was an escape pod for an idea rather than a body", "each answer given twice became consent on behalf of everyone"], [
        "Every screen on Earth lit up with the words PLEASE CONFIRM.", "The runway lights pointed upward and something enormous changed direction.",
        "They refused the final request; their own voice accepted it from behind them.", "The object departed, leaving one additional moon in the daylight sky."],
     ["empty airfield laboratory", "alien signal control room", "sealed hangar strange lights"]),
]

FORMS = ("confession", "incident report", "third-person tale", "emergency call", "recovered transcript")

MANIFESTATIONS = (
    "Something breathed against the back of their neck, although the wall was inches behind them.",
    "A wet handprint appeared on the inside of the locked door and slowly slid downward.",
    "The darkness in the corner stood up, unfolding joints that had been hidden in its silhouette.",
    "A voice under the floor whispered their full name, then began counting down from ten.",
    "The security feed showed a tall shape directly behind them; the room itself looked empty.",
    "Every reflection turned toward them at once, but none copied their movement.",
    "Bare footsteps crossed the ceiling and stopped exactly above their head.",
    "The emergency light flashed once, revealing finger marks pressed into the walls from inside.",
    "Their phone camera opened by itself and focused on a face peering around the doorway.",
    "A human-shaped patch of darkness crawled across the floor against the direction of the light.",
)

PANIC_BEATS = (
    "Their mouth tasted of blood. They could hear their heartbeat, then a second heartbeat matching it from the dark.",
    "Nobody screamed. The kind of fear that knows it is being hunted makes people painfully quiet.",
    "The handle began turning. They held it shut until something on the other side copied their grip.",
    "When they finally ran, the footsteps behind them never became faster, yet kept getting closer.",
    "The smell changed to damp soil and spoiled meat. Whatever was nearby had stopped pretending to be human.",
    "They covered the camera. The live feed continued, now showing the view from beneath their bed.",
    "A whisper came through the speaker: do not look behind you. Then the same whisper came from behind them.",
    "The lights went out from the far end of the corridor toward them, one bulb at a time.",
)

FINAL_WARNINGS = (
    "If you hear three knocks after this story ends, do not answer the third one.",
    "The recording stops here, but headphones reveal breathing for another eleven seconds.",
    "Police found no body. They did find fresh footprints beginning inside the sealed room.",
    "The final frame is a close-up of something smiling with the survivor's teeth.",
    "That night, everyone who watched the footage woke with mud beneath their fingernails.",
    "The last message arrived after the phone was destroyed: it says the viewer is next.",
    "The door is still locked from the inside, and something knocks whenever its name is mentioned.",
    "No one knows where the survivor went. Their shadow still appears in new recordings.",
)

# Each pressure changes the escalation, survival decision, and lasting cost.
PLOT_PRESSURES = [
    ("It only advanced while nobody was speaking", "keep one terrified witness talking or let the silence reach them", "Their voice never returned, but something now answers when they think."),
    ("Every locked exit transferred the danger to a different room", "open the final door without knowing who was behind it", "All their doors now open into places they have tried to forget."),
    ("Recording proof made the next event happen sooner", "destroy the evidence or preserve a warning nobody would believe", "The deleted footage reappeared on a stranger's phone."),
    ("Each person remembered a different version of the first incident", "choose one memory to make real and erase the others", "Their chosen memory still changes whenever they sleep."),
    ("The safest instruction became dangerous after it was obeyed twice", "break the rule before a frightened stranger repeated it", "A printed copy of the rule arrived at their home."),
    ("It copied useful objects but always added one tiny flaw", "identify the original before someone used the copy", "Their reflection now has the same tiny flaw."),
    ("Every warning saved one person and selected another", "stop the warning or knowingly pass the risk onward", "The next warning arrived in their own voice."),
    ("The phenomenon could only enter places described accurately", "lie about the room while trapped people demanded directions", "Maps now blur around every place they visit."),
    ("Fear made it visible, but calm allowed it to move", "keep watching without reacting until the exit opened", "They have not felt fear since, even when they should."),
    ("It exchanged one private memory for each clue", "forget someone they loved or remain without the final answer", "A stranger remembers the relationship they sacrificed."),
    ("Every attempt to escape removed five minutes from the night", "spend the remaining time rescuing someone else", "Their clocks lose five minutes whenever the phone rings."),
    ("It obeyed literal requests and punished their intended meaning", "give an instruction with no hidden assumption", "Ordinary conversation now changes small parts of reality."),
    ("Only the least trusted witness could see the safe route", "follow the person everyone had already accused", "Nobody remembers the witness, except the survivor."),
    ("The building rearranged itself around every lie", "confess the secret holding the final wall in place", "A new room appears at home whenever they avoid the truth."),
    ("Each light revealed the danger but erased a possible exit", "switch on the last lamp or step into darkness", "Their shadow still searches for the exit they erased."),
    ("The threat treated written names as invitations", "erase their identity from every surviving record", "They escaped, but official systems insist they never existed."),
    ("Helping an injured person made the helper share the wound", "divide the final injury among everyone present", "Old scars appear whenever someone nearby asks for help."),
    ("The anomaly repeated choices rather than actions", "make a decision they could not predict themselves", "Sometimes their body chooses several seconds before they do."),
    ("It remained harmless until someone correctly explained it", "leave the mystery unsolved while an expert approached the truth", "The explanation appears word by word in their dreams."),
    ("Every electronic signal strengthened it while analog noise confused it", "destroy the last working phone and trust an obsolete machine", "Static follows every call they make."),
    ("It could imitate anyone except the person who hated it most", "ask a cruel question only the real person could answer", "The correct answer ruined the relationship it saved."),
    ("The event reset whenever somebody died", "escape without allowing the exhausted group to trigger another reset", "They remember hundreds of deaths that never happened."),
    ("It moved through promises that people intended to keep", "break a sacred promise before the promise carried it outside", "Nobody trusts them now, which may be the only protection."),
    ("The danger ignored observers who genuinely did not care", "abandon the need to understand what was happening", "Curiosity now causes the same sound behind their walls."),
    ("It offered a perfect rescue in exchange for one unknown future consequence", "refuse certainty and attempt an ordinary, dangerous escape", "Years later, the unused rescue offer is still counting down."),
]


def render_story(
    genre: str, setting: str, hook: str, reveal: str, ending: str,
    form: str, number: int, pressure: tuple[str, str, str],
) -> str:
    escalation, decision, cost = pressure
    escalation_mid = escalation[:1].lower() + escalation[1:]
    manifestation = MANIFESTATIONS[(number * 7) % len(MANIFESTATIONS)]
    panic = PANIC_BEATS[(number * 5) % len(PANIC_BEATS)]
    warning = FINAL_WARNINGS[(number * 3) % len(FINAL_WARNINGS)]
    sensory = [
        "A low vibration travelled through the floor.", "The air smelled of rain and hot metal.",
        "Every light dimmed in sequence.", "Silence arrived so suddenly it hurt.",
        "Condensation formed on the wrong side of the glass.", "Every clock stopped with a distant alarm.",
        "Dust rose from the floor in the shape of footprints.", "The temperature dropped whenever anyone said they were safe.",
    ][number % 8]
    false_lead = [
        "At first, faulty wiring seemed like an answer, until the main breaker was found disconnected.",
        "They blamed exhaustion, but a second witness described the same impossible detail.",
        "The cameras showed nothing unusual, except that their timestamps were counting backward.",
        "A careful search found no intruder and no route by which anyone could have entered.",
        "A maintenance log offered an answer, but its author did not exist.",
        "A second witness laughed until the same detail appeared in a private photograph.",
        "Dispatch confirmed the address, then insisted the building did not exist.",
        "They found a mechanical cause, but it continued after the mechanism was removed.",
    ][(number * 3) % 8]
    scene_pressure = [
        "Each repetition came closer and removed one ordinary detail from the room.",
        "Phone service failed, the exits changed position, and familiar voices began giving dangerous advice.",
        "Every attempt to record proof produced a different version of the same event.",
        "The phenomenon waited whenever it was watched and moved whenever anyone spoke.",
        "The group separated briefly and returned with incompatible memories.",
        "The only safe room shrank each time they checked it.",
        "An ordinary object moved closer during every distraction.",
        "Emergency lights formed an arrow pointing away from every marked exit.",
    ][(number * 5) % 8]
    if form == "confession":
        return f"I need someone to believe what happened in {setting}. {hook.capitalize()}. {sensory} {false_lead} {manifestation} I tried to leave, but every safe choice pulled me deeper. {scene_pressure} {panic} We learned the rule too late: {escalation}. I had to {decision}. Then I understood that {reveal}. {ending} {cost} {warning}"
    if form == "incident report":
        return f"INCIDENT {number:03d}. Location: {setting.capitalize()}. Initial anomaly: {hook}. {sensory} {false_lead} Standard containment failed. {manifestation} {scene_pressure} {panic} Recovered audio captured chewing directly behind the witness, although the camera showed nothing there. Evidence established a rule: {escalation}. The only remaining choice was to {decision}. Investigators concluded that {reveal}. {ending} {cost} {warning}"
    if form == "emergency call":
        return f"CALLER: I am inside {setting}. {hook.capitalize()}. DISPATCH: Stay calm and find an exit. CALLER: There are no exits now. {sensory} {manifestation} DISPATCH: What is breathing beside you? CALLER: I am alone. {false_lead} {scene_pressure} {panic} Listen carefully: {escalation}. If the line cuts out, I must {decision}. DISPATCH: Do not turn around. CALLER: Too late. {reveal.capitalize()}. {ending} {cost} {warning}"
    if form == "recovered transcript":
        return f"RECOVERED FILE {number:03d}. [00:01] {hook.capitalize()}. [00:07] {sensory} [00:14] {manifestation} [00:22] {scene_pressure} [00:31] {panic} [00:39] Rule confirmed: {escalation}. [00:47] The recorder says they must {decision}. [00:55] A second voice answers from inches away. Final analysis: {reveal}. [01:03] {ending} Archive note: {cost} {warning}"
    return f"Nobody expected trouble in {setting}. Then {hook}. {sensory} {false_lead} {manifestation} Searching for a rational cause made the pattern personal. {scene_pressure} {panic} The survivors discovered that {escalation_mid}. Their last move was to {decision}. Only then did they learn that {reveal}. For several minutes everything became perfectly normal. Then the breathing started again. {ending} {cost} {warning}"


def creepy_query(query: str) -> str:
    """Bias every provider toward empty, ominous footage instead of generic stock video."""
    words = f"eerie creepy horror night fog shadows empty {query}".split()
    value = " ".join(dict.fromkeys(words))
    return value[:80].rstrip()


def build_ideas() -> list[dict[str, object]]:
    ideas: list[dict[str, object]] = []
    number = 1
    # Interleave genres so scheduled uploads never repeat a genre back-to-back.
    for variant, pressure in enumerate(PLOT_PRESSURES):
        for genre_index, (genre, setting, hooks, reveals, endings, queries) in enumerate(GENRES):
            form = FORMS[(variant + genre_index) % len(FORMS)]
            hook = hooks[variant % 4]
            reveal = reveals[(variant // 4 + genre_index) % 4]
            ending = endings[(variant * 3 + genre_index) % 4]
            story = render_story(genre, setting, hook, reveal, ending, form, number, pressure)
            ideas.append({
                "idea_number": number, "genre": genre,
                "title": f"{genre.title()} {number:03d}: {hook.title()}"[:100],
                "story": story,
                "description": f"An original {genre} horror story.",
                "tags": [genre, "horror", "scary stories", "shorts"],
                "background_file": "dark-corridor.png",
                "background_queries": [creepy_query(query) for query in queries],
                "watermark_text": "SKIP IF YOU'RE SCARED",
            })
            number += 1
    return ideas


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate 500 premise-distinct, genre-balanced horror scripts.")
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
