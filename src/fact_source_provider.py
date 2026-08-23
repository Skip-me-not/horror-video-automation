from __future__ import annotations

import json
import shutil
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .script_bank import atomic_write_json


LOC_API = "https://www.loc.gov/search/"
WIKIPEDIA_API = "https://en.wikipedia.org/w/api.php"
SEARCH_TERMS = (
    "ghost stories",
    "ghosts folklore", "supernatural belief", "witchcraft folklore", "haunted legends",
    "apparitions folklore", "spirit stories folklore", "death omens folklore", "burial customs folklore",
    "funeral customs folklore", "cemetery legends", "devil folklore", "demon folklore",
    "vampire folklore", "werewolf folklore", "monster folklore", "nightmare folklore",
    "possession folklore", "exorcism folklore", "shapeshifter folklore", "black magic folklore",
    "evil eye folklore", "death legends", "ghost oral history", "supernatural oral history",
)

DARK_TERMS = (
    "ghost", "witch", "supernatural", "haunt", "apparition", "demon", "devil", "vampire",
    "werewolf", "zombie", "occult", "evil eye", "black magic", "monster", "poltergeist",
    "exorcism", "possession", "shapeshift", "nightmare", "specter", "spectre", "phantom",
)
CONTEXT_TERMS = ("folklore", "legend", "tradition", "belief", "myth", "superstition", "oral history", "story")
WIKIPEDIA_CATEGORIES = (
    "Ghosts", "Reportedly haunted locations", "Urban legends", "Supernatural legends",
    "Legendary creatures", "Demons", "Vampires", "Werewolves", "Witchcraft", "Superstitions",
    "Death customs", "Funeral rites", "Paranormal", "Cryptids", "Exorcism", "Spirit possession",
    "Occult", "Monsters", "Mythological monsters", "Ghost stories", "Allegedly haunted objects",
    "Japanese legendary creatures", "Yōkai", "Slavic legendary creatures", "Celtic legendary creatures",
    "African legendary creatures", "Native American legendary creatures", "Philippine legendary creatures",
    "Indonesian legendary creatures", "Malaysian legendary creatures", "Thai legendary creatures",
    "Haunted locations in the United States", "Haunted locations in the United Kingdom",
    "Haunted locations in India", "Haunted locations in Japan", "Ghosts by country", "Ghost folklore",
    "Magic (supernatural)", "Curses", "Necromancy", "Death deities", "Underworlds",
    "European legendary creatures", "Asian legendary creatures", "Chinese legendary creatures",
    "Korean legendary creatures", "Burmese legendary creatures", "Indian legendary creatures",
    "Arabian legendary creatures", "Persian legendary creatures", "Greek legendary creatures",
    "Germanic legendary creatures", "Irish legendary creatures", "Scottish legendary creatures",
    "Welsh legendary creatures", "English legendary creatures", "French legendary creatures",
    "Romanian legendary creatures", "Russian legendary creatures", "Turkish legendary creatures",
    "Jewish legendary creatures", "Islamic legendary creatures", "Hindu legendary creatures",
    "Buddhist legendary creatures", "Mesoamerican legendary creatures", "South American legendary creatures",
    "Oceanian legendary creatures", "Australian legendary creatures", "Mythological humanoids", "Undead",
    "Revenants", "Ghouls", "Jinn", "Bogeymen", "Death in folklore", "Folk belief",
)
WIKIPEDIA_SEED_TITLES = (
    "La Llorona", "Kuchisake-onna", "Bloody Mary (folklore)", "Bell Witch", "Black Shuck", "Banshee",
    "Dullahan", "Pontianak (folklore)", "Krasue", "Penanggalan", "Manananggal", "Aswang", "Churel",
    "Vetala", "Nuckelavee", "Draugr", "Strigoi", "Dybbuk", "Ghoul", "Jinn", "Mothman", "Jersey Devil",
    "Baba Yaga", "Sleep paralysis", "Hat Man", "Old Hag", "White Lady", "Headless Horseman", "Wild Hunt",
    "Black-eyed children", "Vanishing hitchhiker", "Spring-heeled Jack", "Mad Gasser of Mattoon",
    "Enfield poltergeist", "Amityville haunting", "Borley Rectory", "Brown Lady of Raynham Hall", "Gef",
    "Bélmez Faces", "Devil's Footprints", "Hammersmith Ghost murder case", "Greenbrier Ghost",
    "Vampire of Highgate", "Beast of Gévaudan", "Monkey-man of Delhi", "Nale Ba", "Teke Teke", "Aka Manto",
    "Hanako-san", "Okiku", "Kunekune (urban legend)", "Slit-Mouthed Woman", "Candyman (urban legend)",
    "Resurrection Mary", "The Hands Resist Him", "Robert (doll)", "Annabelle (doll)", "The Anguished Man",
    "Flying Dutchman", "Mary Celeste", "Chase vault", "Cock Lane ghost", "Screaming Skull", "Grey Man of Ben MacDhui",
    "Bunny Man", "Goatman (urban legend)", "Pukwudgie", "Snallygaster", "Dover Demon", "Fresno nightcrawler",
    "Ammons haunting case", "A Haunting in Connecticut", "Bachelor's Grove Cemetery", "Winchester Mystery House",
    "Myrtles Plantation", "Ancient Ram Inn", "Pluckley", "Island of the Dolls", "Houska Castle", "Poveglia",
    "Hoia Forest", "Waverly Hills Sanatorium", "Trans-Allegheny Lunatic Asylum", "Eastern State Penitentiary",
    "RMS Queen Mary", "Alcatraz Federal Penitentiary", "Hinterkaifeck murders", "Dyatlov Pass incident",
    "Flannan Isles Lighthouse", "Lead Masks Case", "Yuba County Five", "Dancing plague of 1518",
    "Great Amherst Mystery", "Green children of Woolpit", "Eilean Mòr", "Devil's Tramping Ground",
    "Clinton Road (New Jersey)", "Crybaby Bridge", "Emily's Bridge", "Lake Lanier",
)


@dataclass(frozen=True)
class FactSource:
    source_id: str
    source_title: str
    source_url: str
    source_institution: str
    source_date: str
    source_collection: str
    source_rights: str
    evidence_type: str
    location: str
    contributors: tuple[str, ...]
    subjects: tuple[str, ...]
    notes: tuple[str, ...]
    original_format: tuple[str, ...]
    online_format: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        value = asdict(self)
        for field in ("contributors", "subjects", "notes", "original_format", "online_format"):
            value[field] = list(value[field])
        return value


def _strings(value: Any) -> tuple[str, ...]:
    if isinstance(value, str):
        return (value.strip(),) if value.strip() else ()
    if isinstance(value, list):
        return tuple(str(item).strip() for item in value if str(item).strip())
    return ()


def _first(value: Any, fallback: str = "") -> str:
    values = _strings(value)
    return values[0] if values else fallback


def _evidence_type(result: dict[str, Any]) -> str:
    searchable = " ".join(
        _strings(result.get("original_format"))
        + _strings(result.get("type"))
        + _strings(result.get("subject"))
        + _strings(result.get("item", {}).get("genre"))
    ).casefold()
    if any(term in searchable for term in ("interview", "field recording", "sound recording", "spoken word")):
        return "oral_history"
    if any(term in searchable for term in ("ghost stories", "folklore", "superstition", "legend")):
        return "folklore_record"
    return "archival_record"


def normalize_loc_result(result: dict[str, Any]) -> FactSource | None:
    item = result.get("item") if isinstance(result.get("item"), dict) else {}
    url = str(result.get("url") or result.get("id") or "").replace("http://", "https://")
    if not url.startswith("https://www.loc.gov/item/") or result.get("access_restricted"):
        return None
    title = str(result.get("title") or item.get("title") or "").strip()
    if not title:
        return None
    relevance = " ".join(
        (title,)
        + _strings(result.get("subject")) + _strings(item.get("subjects"))
        + _strings(item.get("genre")) + _strings(item.get("notes"))
    ).casefold()
    direct_match = any(term in relevance for term in DARK_TERMS)
    contextual_match = any(term in relevance for term in ("death", "burial", "funeral", "omen", "cemetery")) and any(
        term in relevance for term in CONTEXT_TERMS
    )
    if not (direct_match or contextual_match):
        return None
    source_id = url.rstrip("/").rsplit("/", 1)[-1]
    location = _first(item.get("created_published")) or _first(result.get("location"), "location not specified")
    collection = _first(item.get("source_collection")) or _first(result.get("partof"), "Library of Congress digital collection")
    rights = str(item.get("rights") or result.get("rights") or "See the Library of Congress item page for rights information.")
    return FactSource(
        source_id=source_id,
        source_title=title,
        source_url=url,
        source_institution="Library of Congress",
        source_date=str(result.get("date") or item.get("date") or "date not specified"),
        source_collection=collection,
        source_rights=rights,
        evidence_type=_evidence_type(result),
        location=location,
        contributors=_strings(item.get("contributors") or result.get("contributor")),
        subjects=_strings(item.get("subjects") or result.get("subject")),
        notes=_strings(item.get("notes")),
        original_format=_strings(result.get("original_format") or item.get("format")),
        online_format=_strings(result.get("online_format")),
    )


class LibraryOfCongressProvider:
    """Fetches archival metadata only; it never treats a supernatural claim as verified."""

    def __init__(self, timeout: int = 20, delay_seconds: float = 0.1) -> None:
        self.timeout = timeout
        self.delay_seconds = delay_seconds

    def _search(self, term: str, count: int = 100, page: int = 1) -> list[dict[str, Any]]:
        query = urlencode({"fo": "json", "q": term, "c": min(100, count), "sp": page, "at": "results"})
        url = f"{LOC_API}?{query}"
        curl = shutil.which("curl.exe") or shutil.which("curl")
        if curl:
            try:
                completed = subprocess.run(
                    [curl, "-L", "--silent", "--show-error", "--max-time", str(self.timeout), url],
                    check=True, capture_output=True, timeout=self.timeout + 5,
                )
                payload = json.loads(completed.stdout)
                results = payload.get("results", [])
                return [item for item in results if isinstance(item, dict)] if isinstance(results, list) else []
            except (OSError, subprocess.SubprocessError, json.JSONDecodeError) as exc:
                print(f"WARNING: curl LOC query failed for {term!r} page {page}: {exc}")
                return []
        request = Request(
            url,
            headers={"User-Agent": "sourced-horror-facts/1.0 (metadata research)"},
        )
        last_error: Exception | None = None
        for attempt in range(2):
            try:
                with urlopen(request, timeout=self.timeout) as response:
                    payload = json.load(response)
                break
            except Exception as exc:
                last_error = exc
                time.sleep(0.5 * (attempt + 1))
        else:
            print(f"WARNING: skipping LOC query {term!r} page {page}: {last_error}")
            return []
        results = payload.get("results", [])
        if not isinstance(results, list):
            raise RuntimeError("Library of Congress API returned an invalid results payload")
        return [item for item in results if isinstance(item, dict)]

    def fetch(self, target: int = 500) -> list[FactSource]:
        found: dict[str, FactSource] = {}
        requests = [(term, page) for term in SEARCH_TERMS for page in (1, 2, 3)]
        with ThreadPoolExecutor(max_workers=1) as pool:
            futures = {pool.submit(self._search, term, 100, page): (term, page) for term, page in requests}
            for future in as_completed(futures):
                for raw in future.result():
                    source = normalize_loc_result(raw)
                    if source:
                        found.setdefault(source.source_url, source)
                if len(found) >= target:
                    break
                time.sleep(self.delay_seconds)
        return list(found.values())[:target]


class WikimediaProvider:
    """Uses attributed reference summaries; it does not promote alleged events to proven facts."""

    def __init__(self, timeout: int = 25) -> None:
        self.timeout = timeout

    def _category(self, category: str) -> list[dict[str, Any]]:
        query = urlencode({
            "action": "query", "generator": "categorymembers", "gcmtitle": f"Category:{category}",
            "gcmnamespace": 0, "gcmlimit": 100, "prop": "extracts|info", "inprop": "url",
            "exintro": 1, "explaintext": 1, "exlimit": "max", "format": "json", "formatversion": 2,
        })
        curl = shutil.which("curl.exe") or shutil.which("curl")
        if not curl:
            raise RuntimeError("curl is required for Wikimedia source refresh")
        try:
            completed = subprocess.run(
                [curl, "-L", "--silent", "--show-error", "--max-time", str(self.timeout), f"{WIKIPEDIA_API}?{query}"],
                check=True, capture_output=True, timeout=self.timeout + 5,
            )
            payload = json.loads(completed.stdout)
        except (OSError, subprocess.SubprocessError, json.JSONDecodeError) as exc:
            print(f"WARNING: Wikimedia category {category!r} failed: {exc}")
            return []
        pages = payload.get("query", {}).get("pages", [])
        return [page for page in pages if isinstance(page, dict)] if isinstance(pages, list) else []

    def _titles(self, titles: tuple[str, ...]) -> list[dict[str, Any]]:
        query = urlencode({
            "action": "query", "titles": "|".join(titles), "prop": "extracts|info", "inprop": "url",
            "exintro": 1, "explaintext": 1, "format": "json", "formatversion": 2,
        })
        curl = shutil.which("curl.exe") or shutil.which("curl")
        if not curl:
            return []
        try:
            completed = subprocess.run(
                [curl, "-L", "--silent", "--show-error", "--max-time", str(self.timeout), f"{WIKIPEDIA_API}?{query}"],
                check=True, capture_output=True, timeout=self.timeout + 5,
            )
            pages = json.loads(completed.stdout).get("query", {}).get("pages", [])
            return [page for page in pages if isinstance(page, dict)] if isinstance(pages, list) else []
        except (OSError, subprocess.SubprocessError, json.JSONDecodeError) as exc:
            print(f"WARNING: Wikimedia title batch failed: {exc}")
            return []

    @staticmethod
    def _source(page: dict[str, Any], category: str) -> FactSource | None:
        title = str(page.get("title", "")).strip()
        extract = " ".join(str(page.get("extract", "")).split())
        url = str(page.get("fullurl", ""))
        if not title or len(extract) < 80 or not url.startswith("https://en.wikipedia.org/wiki/"):
            return None
        return FactSource(
            source_id=f"wiki-{page.get('pageid')}", source_title=title, source_url=url,
            source_institution="Wikimedia / English Wikipedia", source_date=str(page.get("touched", "date not specified")),
            source_collection=f"Wikipedia category: {category}",
            source_rights="Wikipedia text is available under CC BY-SA 4.0; see the article history for attribution.",
            evidence_type="reference_summary", location="location varies by subject", contributors=(),
            subjects=(category,), notes=(extract,), original_format=("reference article",), online_format=("text",),
        )

    def fetch(self, target: int = 600, skip_categories: set[str] | None = None) -> list[FactSource]:
        found: dict[str, FactSource] = {}
        for offset in range(0, len(WIKIPEDIA_SEED_TITLES), 50):
            for page in self._titles(WIKIPEDIA_SEED_TITLES[offset:offset + 50]):
                source = self._source(page, "Curated horror and folklore topics")
                if source:
                    found.setdefault(source.source_url, source)
        for category in WIKIPEDIA_CATEGORIES:
            if category in (skip_categories or set()):
                continue
            pages = self._category(category)
            if not pages:
                continue
            for page in pages:
                source = self._source(page, category)
                if source:
                    found.setdefault(source.source_url, source)
                if len(found) >= target:
                    return list(found.values())
            time.sleep(0.2)
        return list(found.values())


def load_source_cache(path: Path) -> list[FactSource]:
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid source cache JSON: {path}") from exc
    if not isinstance(payload, list):
        raise ValueError("fact source cache must be a JSON array")
    sources = []
    for item in payload:
        if not isinstance(item, dict):
            raise ValueError("fact source cache entries must be objects")
        converted = dict(item)
        for field in ("contributors", "subjects", "notes", "original_format", "online_format"):
            converted[field] = tuple(converted.get(field, []))
        sources.append(FactSource(**converted))
    return sources


def save_source_cache(path: Path, sources: Iterable[FactSource]) -> None:
    atomic_write_json(path, [source.to_dict() for source in sources])
