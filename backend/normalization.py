"""Bounded lexical normalization with a reversible map to original character spans.

Only a small known vocabulary is folded. URLs are never rewritten. Emoji are
interpreted only inside an otherwise complete known word, not as a risk signal.
"""

import re
import unicodedata

VERSION = "lexical-view-1.0"
GLYPHS = {
    "к": ("к", "k"), "а": ("а", "a", "@", "🅰", "🅰️"), "з": ("з", "z", "3"),
    "и": ("и", "i", "u", "ℹ", "ℹ️"), "н": ("н", "h", "n"), "о": ("о", "o", "0", "🅾", "🅾️"),
    "с": ("с", "c", "s"), "л": ("л", "l"), "т": ("т", "t"), "р": ("р", "p", "r"),
    "у": ("у", "y", "u"), "е": ("е", "e"), "ф": ("ф", "f"), "п": ("п", "p", "n"),
    "б": ("б", "b", "6"),
}
WORDS = ("казино", "слот", "рулетка", "фриспин", "бонус")
GAP = r"[\s._\-\u200b\u200c\u200d]{0,3}"
PATTERNS = [(word, re.compile(r"(?<!\w)" + GAP.join(
    "(" + "|".join(re.escape(x) for x in sorted(GLYPHS.get(c, (c,)), key=len, reverse=True)) + ")"
    for c in word) + r"(?=[\s\W]|$|(?:ға|да|дан|ның|ны|ты|тар|қа|лар|ов|ами|ы|а|у|и|е)\b)", re.I))
            for word in WORDS]


def lexical_view(original):
    chars, spans = [], []
    for index, char in enumerate(original):
        expanded = unicodedata.normalize("NFKC", char).casefold()
        chars.extend(expanded)
        spans.extend([(index, index + 1)] * len(expanded))
    text = "".join(chars)
    protected = [m.span() for m in re.finditer(r"https?://\S+", text, re.I)]
    replacements = []
    for word, pattern in PATTERNS:
        for match in pattern.finditer(text):
            if any(a < match.end() and b > match.start() for a, b in protected):
                continue
            if any(a < match.end() and b > match.start() for a, b, _, _ in replacements):
                continue
            mapped = [(spans[match.start(i)][0], spans[match.end(i) - 1][1]) for i in range(1, len(word) + 1)]
            replacements.append((match.start(), match.end(), word, mapped))
    for start, end, word, mapped in sorted(replacements, reverse=True):
        chars[start:end] = list(word)
        spans[start:end] = mapped
    return "".join(chars), spans
