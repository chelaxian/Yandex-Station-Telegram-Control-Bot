"""Four digit frames using the segment names returned by LUNA, never sysfs."""
from .errors import InvalidInput, Unavailable

GLYPHS = dict(zip("0123456789", ["ABCDEF", "BC", "ABGED", "ABCDG", "FGBC", "AFGCD", "AFGECD", "ABC", "ABCDEFG", "ABCDFG"], strict=True))
GLYPHS.update({" ": "", "-": "G", "C": "ADEF", "O": "ABCDEF", "L": "DEF", "H": "BCEFG",
               "E": "ADEFG", "P": "ABEFG", "U": "BCDEF", "A": "ABCEFG", "t": "DEFG", "u": "CDE"})
PRESETS = {"1337": "1337", "2026": "2026", "cool": "COOL", "help": "HELP", "cat": " CAt", "uwu": "U U "}


def segment_frame(text: str, brightness: int, available: list[str]) -> dict[str, int]:
    if not 1 <= len(text) <= 4 or any(c not in GLYPHS for c in text):
        raise InvalidInput("Сегментный экран: до 4 символов 0–9, пробел, -, C O L H E P U A t u. /screen cool|help|cat|uwu")
    # Station backends advertise both zero- and one-based layouts. Inspect the
    # complete topology instead of deriving an index from the model name.
    start = next((base for base in (0, 1) if {f"{p}{i}" for p in "ABCDEFG" for i in range(base, base + 4)} <= set(available)), None)
    if start is None:
        raise Unavailable("LUNA не предоставляет четырёхзначную сегментную раскладку")
    frame = {f"{part}{i}": brightness for i, char in enumerate(text.rjust(4), start) for part in GLYPHS[char]}
    if not set(frame) <= set(available):
        raise Unavailable("LUNA не предоставляет сегменты для этого рисунка")
    return frame
