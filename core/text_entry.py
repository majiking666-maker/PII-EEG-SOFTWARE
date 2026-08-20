"""
Text entry for PII: hierarchical SSVEP keyboard + predictions.

Design (Grok Notes 10/11, design_decisions.md, 2026-08-20 clarification):
- PII owns its own keyboard surface (v1), not the native OS keyboard.
- Hierarchical pages so simultaneous SSVEP frequencies stay within the
  TargetRegistry dynamic pool (~4 usable after confirm/scroll reserved).
- Predictions live on their OWN page (not mixed into groups). Open via a
  PREDICT target on the groups page. Each committed letter updates the
  prefix; opening the predictions page shows suggestions for current text.
- Confirm uses the shared confirm contract (mental Yes/No or SSVEP yes/no
  targets depending on UserProfile.mode).
- All targets go through TargetRegistry so frequencies never collide with
  confirm/scroll markers.

This module is the keyboard *state machine and target builder*. It does not
render UI or detect EEG; it produces UIElements / target ids that the rest
of the stack already understands.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from core.ssvep_targets import UIElement, TargetRegistry, TargetGroup


DEFAULT_LETTER_GROUPS: dict[str, str] = {
    "A-G": "ABCDEFG",
    "H-N": "HIJKLMN",
    "O-U": "OPQRSTU",
    "V-Z": "VWXYZ",
}

SPECIAL_KEYS = ("SPACE", "DELETE", "DONE")


class KeyboardPage(Enum):
    GROUPS = "groups"             # letter groups + specials + PREDICT + 123
    LETTERS = "letters"           # letters inside one group
    PREDICTIONS = "predictions"   # suggestion chips only + BACK
    NUMBERS = "numbers"


@dataclass
class PredictionEngine:
    """
    Minimal prediction interface.

    get_predictions(prefix, highlighted_group_letters, max_n) returns up to
    max_n word suggestions. Pipeline is solid (updates as each letter is
    committed). Quality is limited: tiny offline list, not a real LM.
    Swap this class later without changing TextKeyboard.
    """

    _COMMON: tuple[str, ...] = (
        "the", "to", "and", "of", "a", "in", "is", "it", "you", "that",
        "he", "was", "for", "on", "are", "with", "as", "I", "his", "they",
        "be", "at", "one", "have", "this", "from", "or", "had", "by",
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
        "great", "think", "say", "help", "low", "line", "hello", "help",
        "home", "hand", "here", "high", "hour", "house", "yes", "you",
    )

    def get_predictions(
        self,
        prefix: str,
        highlighted_group_letters: str | None = None,
        max_n: int = 6,
    ) -> list[str]:
        prefix = prefix.lower().strip()
        if " " in prefix:
            current = prefix.rsplit(" ", 1)[-1]
        else:
            current = prefix

        candidates = [w for w in self._COMMON if w.startswith(current)]
        if not current:
            candidates = list(self._COMMON[:40])

        boost = set((highlighted_group_letters or "").lower())

        def score(word: str) -> tuple:
            next_idx = len(current)
            in_group = 0
            if next_idx < len(word) and word[next_idx] in boost:
                in_group = 1
            return (-in_group, len(word), word)

        candidates.sort(key=score)
        seen: set[str] = set()
        out: list[str] = []
        for w in candidates:
            if w not in seen:
                seen.add(w)
                out.append(w)
            if len(out) >= max_n:
                break
        return out


@dataclass
class KeyboardState:
    text: str = ""
    page: KeyboardPage = KeyboardPage.GROUPS
    active_group: str | None = None
    highlighted_id: str | None = None


class TextKeyboard:
    """
    Hierarchical SSVEP keyboard.

    Letter-by-letter: each confirmed letter is appended to text immediately.
    Predictions always reflect current text when the predictions page is open.
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
        self._pending_select: str | None = None

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
        elements: list[UIElement] = []

        def add(eid: str, label: str, row: int, col: int) -> None:
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

        if self.state.page == KeyboardPage.GROUPS:
            # Groups only — no prediction chips here (they have their own page)
            for i, gname in enumerate(self.letter_groups):
                add(f"group:{gname}", gname, 0, i)
            for i, sk in enumerate(SPECIAL_KEYS):
                add(f"special:{sk}", sk, 1, i)
            add("page:PREDICTIONS", "PREDICT", 1, len(SPECIAL_KEYS))
            add("page:NUMBERS", "123", 1, len(SPECIAL_KEYS) + 1)

        elif self.state.page == KeyboardPage.LETTERS:
            letters = self.letter_groups.get(self.state.active_group or "", "")
            for i, ch in enumerate(letters):
                add(f"letter:{ch}", ch, 0, i % 6)
            add("nav:BACK", "BACK", 1, 0)
            for i, sk in enumerate(SPECIAL_KEYS):
                add(f"special:{sk}", sk, 1, i + 1)
            add("page:PREDICTIONS", "PREDICT", 1, len(SPECIAL_KEYS) + 1)

        elif self.state.page == KeyboardPage.PREDICTIONS:
            preds = self.predictions.get_predictions(
                self.state.text,
                highlighted_group_letters=self.highlighted_group_letters(),
                max_n=self.max_predictions,
            )
            for i, word in enumerate(preds):
                add(f"pred:{word}", word, 0, i)
            add("nav:BACK", "BACK", 1, 0)

        elif self.state.page == KeyboardPage.NUMBERS:
            for i, ch in enumerate("0123456789"):
                add(f"letter:{ch}", ch, 0, i % 5)
            add("nav:BACK", "BACK", 1, 0)
            for i, sk in enumerate(SPECIAL_KEYS):
                add(f"special:{sk}", sk, 1, i + 1)

        return elements

    def prepare_visible_targets(self) -> list[TargetGroup]:
        elements = self.visible_elements()
        max_n = self.registry.max_dynamic_targets_per_group()
        if len(elements) > max_n:
            elements = elements[:max_n]
        return self.registry.prepare_dynamic_screen(
            elements, self.screen_width, self.screen_height
        )

    def highlight(self, target_id: str) -> None:
        self.state.highlighted_id = target_id

    def request_select(self, target_id: str) -> str:
        self._pending_select = target_id
        self.state.highlighted_id = target_id
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
            # Letter-by-letter: append immediately; predictions update next time
            # the predictions page is opened (or any UI that re-queries them).
            self.state.text += target_id[7:]
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
            return True

        if target_id == "nav:BACK":
            self.state.page = KeyboardPage.GROUPS
            self.state.active_group = None
            return True

        if target_id == "page:NUMBERS":
            self.state.page = KeyboardPage.NUMBERS
            self.state.active_group = None
            return True

        if target_id == "page:PREDICTIONS":
            self.state.page = KeyboardPage.PREDICTIONS
            return True

        return False
