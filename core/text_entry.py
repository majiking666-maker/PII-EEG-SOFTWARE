"""
Text entry for PII: hierarchical SSVEP keyboard + predictions.

Design (Grok Notes 10/11, design_decisions.md):
- PII owns its own keyboard surface (v1), not the native OS keyboard.
- Hierarchical letter groups so simultaneous SSVEP frequencies stay within
  the TargetRegistry dynamic pool (~4-6 usable after confirm/scroll reserved).
- Predictions (~4-6) conditioned on committed text + currently highlighted
  group (soft boost for letters in that group). Simple prefix engine for now;
  interface allows swapping in a real language model later.
- Confirm uses the shared confirm contract (mental Yes/No or SSVEP yes/no
  targets depending on UserProfile.mode).
- All targets go through TargetRegistry so frequencies never collide with
  confirm/scroll markers.

This module is the keyboard *state machine and target builder*. It does not
render UI or detect EEG; it produces UIElements / target ids that the rest
of the stack already understands.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from core.ssvep_targets import UIElement, TargetRegistry, TargetGroup


# Default hierarchical groups (fits typical dynamic pool of 4+ after reserves)
DEFAULT_LETTER_GROUPS: dict[str, str] = {
    "A-G": "ABCDEFG",
    "H-N": "HIJKLMN",
    "O-U": "OPQRSTU",
    "V-Z": "VWXYZ",
}

SPECIAL_KEYS = ("SPACE", "DELETE", "DONE")


class KeyboardPage(Enum):
    GROUPS = "groups"           # top level: letter groups + specials + predictions
    LETTERS = "letters"         # inside one group
    NUMBERS = "numbers"         # optional second page


@dataclass
class PredictionEngine:
    """
    Minimal prediction interface.

    get_predictions(prefix, highlighted_group_letters, max_n) returns up to
    max_n word suggestions. highlighted_group_letters is a soft bias: words
    whose next character falls in that set can be ranked higher. Replace
    this class later with a real on-device LM without changing Keyboard.
    """

    # Tiny built-in list for offline demos / tests (not a real vocabulary)
    _COMMON: tuple[str, ...] = (
        "the", "to", "and", "of", "a", "in", "is", "it", "you", "that",
        "he", "was", "for", "on", "are", "with", "as", "I", "his", "they",
        "be", "at", "one", "have", "this", "from", "or", "had", "by", "hot",
        "word", "but", "what", "some", "we", "can", "out", "other", "were",
        "all", "there", "when", "up", "use", "your", "how", "said", "an",
        "each", "she", "which", "do", "their", "time", "if", "will", "way",
        "about", "many", "then", "them", "write", "would", "like", "so",
        "these", "her", "long", "make", "thing", "see", "him", "two", "has",
        "look", "more", "day", "could", "go", "come", "did", "number",
        "sound", "no", "most", "people", "my", "over", "know", "water",
        "than", "call", "first", "who", "may", "down", "side", "been",
        "now", "find", "any", "new", "work", "part", "take", "get", "place",
        "made", "live", "where", "after", "back", "little", "only", "round",
        "man", "year", "came", "show", "every", "good", "me", "give",
        "our", "under", "name", "very", "through", "just", "form", "sentence",
        "great", "think", "say", "help", "low", "line", "differ", "turn",
        "cause", "much", "mean", "before", "move", "right", "boy", "old",
        "too", "same", "tell", "does", "set", "three", "want", "air", "well",
        "also", "play", "small", "end", "put", "home", "read", "hand",
        "port", "large", "spell", "add", "even", "land", "here", "must",
        "big", "high", "such", "follow", "act", "why", "ask", "men",
        "change", "went", "light", "kind", "off", "need", "house", "picture",
        "try", "us", "again", "animal", "point", "mother", "world", "near",
        "build", "self", "earth", "father", "head", "stand", "own", "page",
        "should", "country", "found", "answer", "school", "grow", "study",
        "still", "learn", "plant", "cover", "food", "sun", "four", "between",
        "state", "keep", "eye", "never", "last", "let", "thought", "city",
        "tree", "cross", "farm", "hard", "start", "might", "story", "saw",
        "far", "sea", "draw", "left", "late", "run", "don't", "while",
        "press", "close", "night", "real", "life", "few", "north", "open",
        "seem", "together", "next", "white", "children", "begin", "got",
        "walk", "example", "ease", "paper", "group", "always", "music",
        "those", "both", "mark", "often", "letter", "until", "mile", "river",
        "car", "feet", "care", "second", "book", "carry", "took", "science",
        "eat", "room", "friend", "began", "idea", "fish", "mountain", "stop",
        "once", "base", "hear", "horse", "cut", "sure", "watch", "color",
        "face", "wood", "main", "enough", "plain", "girl", "usual", "young",
        "ready", "above", "ever", "red", "list", "though", "feel", "talk",
        "bird", "soon", "body", "dog", "family", "direct", "pose", "leave",
        "song", "measure", "door", "product", "black", "short", "numeral",
        "class", "wind", "question", "happen", "complete", "ship", "area",
        "half", "rock", "order", "fire", "south", "problem", "piece", "told",
        "knew", "pass", "since", "top", "whole", "king", "space", "heard",
        "best", "hour", "better", "true", "during", "hundred", "five",
        "remember", "step", "early", "hold", "west", "ground", "interest",
        "reach", "fast", "verb", "sing", "listen", "six", "table", "travel",
        "less", "morning", "ten", "simple", "several", "vowel", "toward",
        "war", "lay", "against", "pattern", "slow", "center", "love",
        "person", "money", "serve", "appear", "road", "map", "rain", "rule",
        "govern", "pull", "cold", "notice", "voice", "unit", "power", "town",
        "fine", "certain", "fly", "fall", "lead", "cry", "dark", "machine",
        "note", "wait", "plan", "figure", "star", "box", "noun", "field",
        "rest", "correct", "able", "pound", "done", "beauty", "drive",
        "stood", "contain", "front", "teach", "week", "final", "gave",
        "green", "oh", "quick", "develop", "ocean", "warm", "free", "minute",
        "strong", "special", "mind", "behind", "clear", "tail", "produce",
        "fact", "street", "inch", "multiply", "nothing", "course", "stay",
        "wheel", "full", "force", "blue", "object", "decide", "surface",
        "deep", "moon", "island", "foot", "system", "busy", "test", "record",
        "boat", "common", "gold", "possible", "plane", "stead", "dry",
        "wonder", "laugh", "thousand", "ago", "ran", "check", "game", "shape",
        "equate", "hot", "miss", "brought", "heat", "snow", "tire", "bring",
        "yes", "distant", "fill", "east", "paint", "language", "among",
        "grand", "ball", "yet", "wave", "drop", "heart", "am", "present",
        "heavy", "dance", "engine", "position", "arm", "wide", "sail",
        "material", "size", "vary", "settle", "speak", "weight", "general",
        "ice", "matter", "circle", "pair", "include", "divide", "syllable",
        "felt", "perhaps", "pick", "sudden", "count", "square", "reason",
        "length", "represent", "art", "subject", "region", "energy", "hunt",
        "probable", "bed", "brother", "egg", "ride", "cell", "believe",
        "fraction", "forest", "sit", "race", "window", "store", "summer",
        "train", "sleep", "prove", "lone", "leg", "exercise", "wall",
        "catch", "mount", "wish", "sky", "board", "joy", "winter", "sat",
        "written", "wild", "instrument", "kept", "glass", "grass", "cow",
        "job", "edge", "sign", "visit", "past", "soft", "fun", "bright",
        "gas", "weather", "month", "million", "bear", "finish", "happy",
        "hope", "flower", "clothe", "strange", "gone", "jump", "baby",
        "eight", "village", "meet", "root", "buy", "raise", "solve", "metal",
        "whether", "push", "seven", "paragraph", "third", "shall", "held",
        "hair", "describe", "cook", "floor", "either", "result", "burn",
        "hill", "safe", "cat", "century", "consider", "type", "law", "bit",
        "coast", "copy", "phrase", "silent", "tall", "sand", "soil", "roll",
        "temperature", "finger", "industry", "value", "fight", "lie", "beat",
        "excite", "natural", "view", "sense", "ear", "else", "quite", "broke",
        "case", "middle", "kill", "son", "lake", "moment", "scale", "loud",
        "spring", "observe", "child", "straight", "consonant", "nation",
        "dictionary", "milk", "speed", "method", "organ", "pay", "age",
        "section", "dress", "cloud", "surprise", "quiet", "stone", "tiny",
        "climb", "bad", "oil", "blood", "touch", "grew", "cent", "mix",
        "team", "wire", "cost", "lost", "brown", "wear", "garden", "equal",
        "sent", "choose", "fell", "fit", "flow", "fair", "bank", "collect",
        "save", "control", "decimal", "gentle", "woman", "captain", "practice",
        "separate", "difficult", "doctor", "please", "protect", "noon",
        "whose", "locate", "ring", "character", "insect", "caught", "period",
        "indicate", "radio", "spoke", "atom", "human", "history", "effect",
        "electric", "expect", "crop", "modern", "element", "hit", "student",
        "corner", "party", "supply", "bone", "rail", "imagine", "provide",
        "agree", "thus", "capital", "won't", "chair", "danger", "fruit",
        "rich", "thick", "soldier", "process", "operate", "guess", "necessary",
        "sharp", "wing", "create", "neighbor", "wash", "bat", "rather",
        "crowd", "corn", "compare", "poem", "string", "bell", "depend",
        "meat", "rub", "tube", "famous", "dollar", "stream", "fear", "sight",
        "thin", "triangle", "planet", "hurry", "chief", "colony", "clock",
        "mine", "tie", "enter", "major", "fresh", "search", "send", "yellow",
        "gun", "allow", "print", "dead", "spot", "desert", "suit", "current",
        "lift", "rose", "continue", "block", "chart", "hat", "sell", "success",
        "company", "subtract", "event", "particular", "deal", "swim", "term",
        "opposite", "wife", "shoe", "shoulder", "spread", "arrange", "camp",
        "invent", "cotton", "born", "determine", "quart", "nine", "truck",
        "noise", "level", "chance", "gather", "shop", "stretch", "throw",
        "shine", "property", "column", "molecule", "select", "wrong", "gray",
        "repeat", "require", "broad", "prepare", "salt", "nose", "plural",
        "anger", "claim", "continent", "oxygen", "sugar", "death", "pretty",
        "skill", "women", "season", "solution", "magnet", "silver", "thank",
        "branch", "match", "suffix", "especially", "fig", "afraid", "huge",
        "sister", "steel", "discuss", "forward", "similar", "guide", "experience",
        "score", "apple", "bought", "led", "pitch", "coat", "mass", "card",
        "band", "rope", "slip", "win", "dream", "evening", "condition", "feed",
        "tool", "total", "basic", "smell", "valley", "nor", "double", "seat",
        "arrive", "master", "track", "parent", "shore", "division", "sheet",
        "substance", "favor", "connect", "post", "spend", "chord", "fat",
        "glad", "original", "share", "station", "dad", "bread", "charge",
        "proper", "bar", "offer", "segment", "slave", "duck", "instant",
        "market", "degree", "populate", "chick", "dear", "enemy", "reply",
        "drink", "occur", "support", "speech", "nature", "range", "steam",
        "motion", "path", "liquid", "log", "meant", "quotient", "teeth",
        "shell", "neck",
    )

    def get_predictions(
        self,
        prefix: str,
        highlighted_group_letters: str | None = None,
        max_n: int = 6,
    ) -> list[str]:
        prefix = prefix.lower().strip()
        # Current word being typed (after last space)
        if " " in prefix:
            current = prefix.rsplit(" ", 1)[-1]
            committed = prefix[: -len(current)] if current else prefix
        else:
            current = prefix
            committed = ""

        candidates = [w for w in self._COMMON if w.startswith(current)]
        if not current:
            # No prefix yet: still offer common starters
            candidates = list(self._COMMON[:40])

        boost = set((highlighted_group_letters or "").lower())

        def score(word: str) -> tuple:
            # Prefer words whose next char is in the highlighted group
            next_idx = len(current)
            in_group = 0
            if next_idx < len(word) and word[next_idx] in boost:
                in_group = 1
            # Prefer shorter completions, then alphabetical
            return (-in_group, len(word), word)

        candidates.sort(key=score)
        # Deduplicate while preserving order
        seen = set()
        out = []
        for w in candidates:
            if w not in seen:
                seen.add(w)
                out.append(w)
            if len(out) >= max_n:
                break
        return out


@dataclass
class KeyboardState:
    """Mutable state of one text-entry session."""
    text: str = ""
    page: KeyboardPage = KeyboardPage.GROUPS
    active_group: str | None = None  # e.g. "A-G" when on LETTERS page
    highlighted_id: str | None = None


class TextKeyboard:
    """
    Hierarchical SSVEP keyboard.

    Usage sketch:
      kb = TextKeyboard(registry)
      elements = kb.visible_elements()          # assign frequencies via registry
      # user fixates target_id -> kb.select(target_id) may need confirm
      # after confirm accepted -> kb.commit_selection()
    """

    def __init__(
        self,
        registry: TargetRegistry,
        letter_groups: dict[str, str] | None = None,
        prediction_engine: PredictionEngine | None = None,
        max_predictions: int = 6,
        screen_width: float = 400.0,
        screen_height: float = 300.0,
    ):
        self.registry = registry
        self.letter_groups = letter_groups or dict(DEFAULT_LETTER_GROUPS)
        self.predictions = prediction_engine or PredictionEngine()
        self.max_predictions = max_predictions
        self.screen_width = screen_width
        self.screen_height = screen_height
        self.state = KeyboardState()

        # Pending selection waiting for confirm (target_id string)
        self._pending_select: str | None = None

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    def current_text(self) -> str:
        return self.state.text

    def highlighted_group_letters(self) -> str | None:
        if self.state.page == KeyboardPage.LETTERS and self.state.active_group:
            return self.letter_groups.get(self.state.active_group)
        if self.state.highlighted_id and self.state.highlighted_id.startswith("group:"):
            g = self.state.highlighted_id.split(":", 1)[1]
            return self.letter_groups.get(g)
        return None

    def visible_elements(self) -> list[UIElement]:
        """
        Build the current page's interactive elements (no frequencies yet).
        Caller (or prepare_visible_targets) assigns frequencies via registry.
        """
        elements: list[UIElement] = []
        y = 10.0
        x = 10.0
        slot = 0

        def add(eid: str, label: str, row: int, col: int) -> None:
            nonlocal slot
            elements.append(
                UIElement(
                    element_id=eid,
                    label=label,
                    x=10.0 + col * 70.0,
                    y=10.0 + row * 40.0,
                    width=60.0,
                    height=30.0,
                )
            )
            slot += 1

        # Prediction bar (row 0)
        preds = self.predictions.get_predictions(
            self.state.text,
            highlighted_group_letters=self.highlighted_group_letters(),
            max_n=self.max_predictions,
        )
        for i, word in enumerate(preds):
            add(f"pred:{word}", word, 0, i)

        if self.state.page == KeyboardPage.GROUPS:
            # Letter groups (row 1)
            for i, gname in enumerate(self.letter_groups):
                add(f"group:{gname}", gname, 1, i)
            # Specials (row 2)
            for i, sk in enumerate(SPECIAL_KEYS):
                add(f"special:{sk}", sk, 2, i)
            add("page:NUMBERS", "123", 2, len(SPECIAL_KEYS))

        elif self.state.page == KeyboardPage.LETTERS:
            letters = self.letter_groups.get(self.state.active_group or "", "")
            for i, ch in enumerate(letters):
                add(f"letter:{ch}", ch, 1, i % 6)
            add("nav:BACK", "BACK", 2, 0)
            for i, sk in enumerate(SPECIAL_KEYS):
                add(f"special:{sk}", sk, 2, i + 1)

        elif self.state.page == KeyboardPage.NUMBERS:
            for i, ch in enumerate("0123456789"):
                add(f"letter:{ch}", ch, 1, i % 5)
            add("nav:BACK", "BACK", 2, 0)
            for i, sk in enumerate(SPECIAL_KEYS):
                add(f"special:{sk}", sk, 2, i + 1)

        return elements

    def prepare_visible_targets(self) -> list[TargetGroup]:
        """Assign SSVEP frequencies to the current page via TargetRegistry."""
        elements = self.visible_elements()
        # Cap to dynamic pool size; if over, caller should paginate further
        max_n = self.registry.max_dynamic_targets_per_group()
        if len(elements) > max_n:
            elements = elements[:max_n]
        return self.registry.prepare_dynamic_screen(
            elements, self.screen_width, self.screen_height
        )

    # ------------------------------------------------------------------
    # Selection / commit
    # ------------------------------------------------------------------

    def highlight(self, target_id: str) -> None:
        """User is fixating this target (pre-confirm)."""
        self.state.highlighted_id = target_id

    def request_select(self, target_id: str) -> str:
        """
        User wants to select this target. Returns a subject_label string
        suitable for start_confirm(...). Does not mutate text until
        commit_selection() after ACCEPTED.
        """
        self._pending_select = target_id
        self.state.highlighted_id = target_id
        # Human-readable subject for the confirm prompt
        if target_id.startswith("pred:"):
            return f"prediction '{target_id[5:]}'"
        if target_id.startswith("group:"):
            return f"group {target_id[6:]}"
        if target_id.startswith("letter:"):
            return f"letter {target_id[7:]}"
        if target_id.startswith("special:"):
            return f"key {target_id[8:]}"
        if target_id.startswith("nav:"):
            return f"nav {target_id[4:]}"
        if target_id.startswith("page:"):
            return f"page {target_id[5:]}"
        return target_id

    def commit_selection(self) -> bool:
        """
        Apply the pending selection after confirm was ACCEPTED.
        Returns True if state changed.
        """
        tid = self._pending_select
        self._pending_select = None
        if not tid:
            return False
        return self._apply(tid)

    def cancel_selection(self) -> None:
        self._pending_select = None

    def _apply(self, target_id: str) -> bool:
        if target_id.startswith("pred:"):
            word = target_id[5:]
            # Replace current partial word with the full prediction + space
            if " " in self.state.text:
                head, _ = self.state.text.rsplit(" ", 1)
                self.state.text = (head + " " + word + " ").lstrip()
            else:
                self.state.text = word + " "
            self.state.page = KeyboardPage.GROUPS
            self.state.active_group = None
            return True

        if target_id.startswith("group:"):
            self.state.active_group = target_id[6:]
            self.state.page = KeyboardPage.LETTERS
            return True

        if target_id.startswith("letter:"):
            self.state.text += target_id[7:]
            # Stay on letters page so user can continue the word
            return True

        if target_id == "special:SPACE":
            self.state.text += " "
            self.state.page = KeyboardPage.GROUPS
            self.state.active_group = None
            return True

        if target_id == "special:DELETE":
            if self.state.text:
                self.state.text = self.state.text[:-1]
            return True

        if target_id == "special:DONE":
            # Caller handles closing the keyboard; we just mark
            return True

        if target_id == "nav:BACK":
            self.state.page = KeyboardPage.GROUPS
            self.state.active_group = None
            return True

        if target_id == "page:NUMBERS":
            self.state.page = KeyboardPage.NUMBERS
            self.state.active_group = None
            return True

        return False
