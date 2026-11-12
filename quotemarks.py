"""Put back quote marks and end punctuation that Vision misreads.

Apple Vision's accurate text model (macOS 27) reads a quote mark that sits
against punctuation, most of all a closing quote over its period (`you.”`),
as one or more Vietnamese letters: `you.” He` comes out "youạẠạHe",
`company.”` "companyiạẠạ", `me?”` "meại". No setting picks the right
characters: every revision, language setting and lower-ranked candidate
carries the same letters. Less often it reads an opening quote as `«`, `*`
or `i` ("iWell,"), a closing one as `»`, `*`, `®` or a lone `i` ("himi"),
and `.”` as `.?`.

A run of those letters stands for a quote and, where Vision didn't read it
separately, the punctuation under it. Where that punctuation can't be read
off the run it's taken from the sentence: a question opening (who, what,
did, is...) gives `?`, a speech tag after it (`" she said`) a comma, and
anything else a period, which ends the sentence either way. clean.py only
keeps a paragraph break after a finished sentence, so a garbled closing quote
used to merge one speaker's paragraph into the next.

The letters never end an English word, and a run is left alone when it sits
inside one ("Phạm"). The ASCII stand-ins (`.?`, `.*`, `.®`, a lone `i`)
are only changed inside a quote, since in nonfiction `.?` and `.*` after a
sentence are footnote numbers.
"""
import re
from typing import Callable, Optional

# Letters seen in place of a quote and its punctuation.
MARKS = "ạẠịỊằẰỗỖồỒọỌặẶậẬếẾ"
# The run: stray i/_ Vision adds around it, any punctuation it did read,
# then the letters (with i, _, periods and ¿ mixed in), then more stray i/_.
# ¿ and ¡ only count inside a run: on their own they stand for letters
# ("competi- ¿ive").
_RUN = re.compile(
    rf"(?P<lead>i?)(?P<punct>(?:\.\.\.|…|[.,?!\-—_¿¡])*) ?"
    rf"(?P<core>[{MARKS}](?:[i_.¿¡]*[{MARKS}])*)(?P<trail>[i_]*)"
)

WH_WORDS = {"who", "whom", "whose", "who's", "what", "what's", "when",
            "where", "where's", "why", "how", "how's", "which"}
AUX_WORDS = {
    "do", "does", "did", "don't", "doesn't", "didn't",
    "is", "isn't", "are", "aren't", "was", "wasn't", "were", "weren't", "am",
    "can", "can't", "could", "couldn't", "would", "wouldn't", "should",
    "shouldn't", "will", "won't", "shall", "have", "haven't", "has",
    "hasn't",
}
QUESTION_WORDS = WH_WORDS | AUX_WORDS
# The subject after an inverted verb: "do you", "is it", "would they".
SUBJECTS = {"i", "you", "we", "they", "he", "she", "it", "that", "this",
            "there", "anyone", "anybody", "someone", "everyone", "the", "our",
            "your", "his", "her", "their", "we're", "you're"}
# Words that can come before a question without changing it: "So what...",
# "And how...", "Well, do you...".
LEAD_INS = {"so", "and", "but", "or", "well", "okay", "ok", "then", "now",
            "oh", "hey", "yeah", "also", "plus", "really"}
# A whole clause of these comes before a question too: "I mean, do you..."
_ASIDES = LEAD_INS | {"i", "mean", "you", "know", "look", "listen"}
_TAGS = re.compile(r",\s*(?:right|(?:is|are|was|were|do|does|did|have|has|would|"
                   r"will|can)n't\s+\w+)\s*$", re.I)


# Verbs of a speech tag: `you," Bobby added`, `that," she explained`.
SPEECH_VERBS = {
    "said", "says", "asked", "added", "explained", "replied", "answered",
    "admitted", "announced", "continued", "hesitated", "responded",
    "insisted", "joked", "shouted", "suggested", "declared", "interrupted",
    "agreed", "argued", "offered", "conceded", "confessed", "countered",
    "remarked", "whispered", "laughed", "smiled", "pushed", "wondered",
    "teased", "corrected", "reminded", "assured", "confirmed", "began",
    "repeated", "protested", "pressed", "persisted", "volunteered",
    "nodded", "shrugged", "sighed", "deadpanned", "quipped",
}
_PRONOUNS = {"he", "she", "they", "i", "we", "you"}


def _words(s: str) -> list[str]:
    return re.findall(r"[A-Za-z0-9']+", s)


def is_question(before: str) -> bool:
    """The sentence ending here reads as a question: it opens with a
    question word ("What do you...", "And how...", "Did he..."), a later
    clause does ("I mean, do you..."), it ends in a tag (", right"), or it
    goes on from a question ("...the company? And you guys").
    """
    sentences = re.split(r'(?<=[.?!])"?\s+|(?:^|\s)"(?=\S)', before)
    tail = sentences[-1]
    if _TAGS.search(tail):
        return True
    clauses = [_words(c) for c in re.split(r"[,;:—]|\s-\s", tail)]
    clauses = [c for c in clauses if c]
    if not clauses:
        return False
    opener = clauses[0][0].lower()
    # "So, is there...", "Jeff, do you...": the question starts after
    while len(clauses) > 1 and (all(w.lower() in _ASIDES for w in clauses[0]) or (
            len(clauses[0]) == 1 and clauses[0][0][:1].isupper()
            and clauses[0][0].lower() not in QUESTION_WORDS)):
        clauses = clauses[1:]
    first = [w.lower() for w in clauses[0]]
    while len(first) > 1 and first[0] in LEAD_INS:
        first = first[1:]
    if _asks(first, opening=True):
        return True
    last = [w.lower() for w in clauses[-1]]
    while len(last) > 1 and last[0] in LEAD_INS:
        last = last[1:]
    if len(clauses) > 1 and _asks(last, opening=False):
        return True
    # "Or just a good person" after a question
    prev = before[: len(before) - len(tail)].rstrip().rstrip('"')
    return opener in {"or", "and"} and prev.endswith("?")


# Verbs that open a question even without a pronoun after them ("Is jackass
# one word?"); "do" and "have" also open orders ("Do it now", "Have a seat").
_ASKING_VERBS = AUX_WORDS - {"do", "don't", "have", "am"}


def _asks(words: list[str], opening: bool) -> bool:
    """The clause `words` is put as a question: a verb before its subject
    ("did he", "would you") or a question word and a verb ("what do", "who
    is", "what about"). Not a question word starting a statement: "When I
    dropped him off...", "Which is why...", "who should go"."""
    if len(words) < 2:
        return False
    w0, w1 = words[0], words[1]
    if w0 in AUX_WORDS:
        return w1 in SUBJECTS or (opening and w0 in _ASKING_VERBS)
    if w0 == "which" and w1 in {"is", "was", "means"}:
        return False
    if w0 in WH_WORDS:
        if w0.endswith("'s"):
            return True
        # "What exactly is...", "What things would you..."
        if w1 in {"exactly", "else", "really", "then", "things", "one", "kind",
                  "sort", "part"} and len(words) > 2 and words[2] in AUX_WORDS:
            w1, words = words[2], words[1:]
        if w1 in AUX_WORDS:
            return opening or (len(words) > 2 and words[2] in SUBJECTS)
        return opening and (w0, w1) in {("how", "many"), ("how", "much"),
            ("how", "long"), ("how", "often"), ("how", "come"),
            ("what", "about"), ("what", "if"), ("what", "else"),
            ("what", "kind"), ("why", "not")}
    return False


def _speech_tag(after: str) -> bool:
    """`after` opens with a speech tag: "Bobby added", "she explained"."""
    words = _words(after)[:3]
    return any(w.lower() in SPEECH_VERBS for w in words[1:3]) or (
        len(words) >= 2 and words[0].lower() in _PRONOUNS
        and words[1].lower() in SPEECH_VERBS)


def _ends_narration(before: str) -> Optional[str]:
    """When `before` ends a narration sentence that leads into a quote
    ("Clare explained", "he said to Jeff"), the punctuation it takes."""
    if before.count('"') % 2 == 1:
        return None
    words = [w.lower() for w in _words(before)[-3:]]
    if not words:
        return None
    if words[-1] in {"said", "says", "added", "asked", "replied"} or (
            len(words) >= 2 and words[-2] == "to" and words[-1][:1].isalpha()
            and len(words) == 3 and words[0] == "said"):
        return ","
    if any(w in SPEECH_VERBS for w in words[-2:]):
        return "."
    return None


def _accented(word: str) -> bool:
    """Has a letter with an accent that Vision doesn't make of a quote."""
    return any(ord(c) > 127 and c.isalpha() and c not in MARKS for c in word)


def fix_line(text: str, before: str = "", after: str = "",
             is_word: Optional[Callable[[str], bool]] = None) -> str:
    """`text` with garbled quote marks put back.

    `before` is the paragraph's text up to this line and `after` the next
    line, used to tell a question from a statement, a speech tag from a new
    sentence, and an opening quote from a closing one. `is_word` (a
    dictionary lookup) decides whether a stray i next to a run belongs to the
    word beside it.
    """
    if not text:
        return text
    pos = 0
    while True:
        m = _RUN.search(text, pos)
        if not m:
            break
        head, tail = text[:m.start()], text[m.end():]
        lead, punct, trail = m["lead"], m["punct"], m["trail"]
        # A stop or dash printed just before the garble is its punctuation
        # ("night.iạiLet's" for `night. "Let's`, "he-iẠạ" for `he—"`), and
        # the i after it belongs to the quote, not to a word.
        stop = re.search(r"(?:\.\.\.|…|[.,?!;:\-—])$", head) if not punct else None
        if stop:
            head, punct, lead = head[:stop.start()], stop.group(0), ""
        word_before = re.search(r"[A-Za-z']*$", head).group(0)
        word_after = re.match(r"[A-Za-z']*", tail).group(0)
        # a lone lowercase mark inside a word ("Phạm"), with nothing around
        # it that says garble
        if (word_before and word_after and not lead and not punct and not trail
                and len(m["core"]) == 1 and m["core"].islower() and tail[:1].islower()):
            pos = m.end()
            continue
        # one in a word beside other accented letters: a Vietnamese name
        # ("Hồ Chí Minh"), not a quote mark
        next_word = re.match(r"\s*(\S*)", tail).group(1)
        if (word_before and not lead and not punct and not trail and len(m["core"]) == 1
                and m["core"].islower() and (_accented(word_before) or _accented(next_word))):
            pos = m.end()
            continue
        # a stray i ends the word before unless the word needs it ("Hawaii")
        if lead and is_word and word_before and is_word(word_before + "i") and not is_word(word_before):
            head += "i"
        # the run can swallow a final y ("companịằ" for company")
        if (is_word and not punct and len(word_before) > 2 and set(m["core"]) & set("ịằ")
                and not is_word(word_before) and is_word(word_before + "y")):
            head += "y"
        # trailing i/_ glued to the next word ("ishe" for `" she`) goes,
        # unless the next word needs it ("it")
        if trail and tail[:1].islower():
            joined = trail.replace("_", "") + re.match(r"[a-z']*", tail).group(0)
            if is_word is None or (is_word(joined) and not
                                   is_word(joined[len(trail):])):
                tail = trail.replace("_", "") + tail
        punct = punct.replace("_", "-").replace("¿", "").replace("¡", "")
        if punct and set(punct) <= {"-"}:
            punct = "-"
        rest = tail.lstrip()
        so_far = (before + " " + head).strip()
        if not head.strip():
            fix = '"'
        elif not rest:
            fix = _closing(punct, so_far, after) + tail
            tail = ""
        else:
            fix = _middle(punct, so_far, rest)
            tail = rest
        text = head.rstrip() + fix + tail if head.strip() else fix + tail.lstrip()
        pos = len(text) - len(tail)
    return _fix_other_marks(text, before, after, is_word)


def _closing(punct: str, so_far: str, after: str) -> str:
    """A closing quote at the end of a line, with its punctuation."""
    if punct:
        return punct + '"'
    if is_question(so_far):
        return '?"'
    nxt = after.lstrip()
    # `that," she said` across the line break
    if nxt[:1].islower() and _speech_tag(nxt):
        return ',"'
    return '."'


def _middle(punct: str, so_far: str, rest: str) -> str:
    """Punctuation and a quote between two words on a line."""
    p = punct.rstrip("-—")
    narration = _ends_narration(so_far)
    if narration and not p.strip("."):
        # `Clare explained. "We said`: a quote opens
        return (p or narration) + ' "'
    tag = _speech_tag(rest)
    if not p:
        if is_question(so_far):
            p = "?"
        elif rest[:1].islower() or tag:
            p = ","
        else:
            p = "."
    # closing when a speech tag follows or a quote is open
    if tag or so_far.count('"') % 2 == 1:
        return p + '" '
    return p + ' "'


# Words that open a line of dialogue, for an opening quote read as "i"
# ("iWell," "iNo,"). A list, so "iPad" and "iPhone" stay.
_OPENERS = ("No|Well|What|Why|How|Who|Yes|Yeah|So|Okay|But|And|It|That|This|"
            "We|You|He|She|They|Do|Did|Is|Are|Can|Hey|Oh|Look|Listen|Wait")
_I_QUOTE = re.compile(rf'(?:^|(?<=[.?!,])\s?)i(?=(?:{_OPENERS})\b)')


def _in_quote(before: str) -> bool:
    """A quote opened shortly before and hasn't closed: an odd number of
    quote marks, the last one opening (`said, "We`), not long ago. Long
    nonfiction paragraphs carry stray unpaired quotes from OCR errors."""
    if before.count('"') % 2 == 0:
        return False
    i = before.rfind('"')
    opens = (i == 0 or before[i - 1] in " \t(—-") and before[i + 1:i + 2].isalnum()
    return opens and len(before) - i <= 300


# A closing quote read as a lone i stuck to the word: `him."` as "himi".
_LONE_I = re.compile(r"\b([A-Za-z']{2,})i(?=(\s+[A-Z\"])|\s*$)")


def _fix_other_marks(text: str, before: str, after: str = "",
                     is_word: Optional[Callable[[str], bool]] = None) -> str:
    if is_word:
        # only inside a quote, and only where the word needs the i gone:
        # a word cut off at the spine ("putti" for putting) stays
        def lone_i(m: re.Match) -> str:
            word = m.group(1)
            so_far = (before + " " + text[:m.start()]).strip()
            # a name ending in i ("Ali", "Toni") isn't a word with a quote on it
            if (word[:1].isupper() or not _in_quote(so_far) or not is_word(word)
                    or is_word(word + "i")):
                return m.group(0)
            if m.group(2):
                return word + _middle("", so_far + " " + word, text[m.end():].lstrip()).rstrip()
            return word + _closing("", so_far + " " + word, after)
        text = _LONE_I.sub(lone_i, text)
    # an opening quote read as "i": `iWell, I`, `second.iWell`
    text = _I_QUOTE.sub(lambda m: (" " if m.group(0) != "i" or m.start() else "") + '"', text)
    # French-style quote marks
    text = re.sub(r"^(\s*)«", r'\1"', text)
    text = re.sub(r'(?<=\s)«(?=[A-Za-z])', '"', text)
    text = re.sub(r"»(\s*)$", r'"\1', text)
    text = re.sub(r'(?<=[.,?!\-—_A-Za-z])»(?=\s)', '"', text)
    text = re.sub(r'(?<=[A-Za-z])_"$', '-"', text)

    # an opening quote read as * at the start of a line that closes one
    # later (`*Unfortunately, yes," Bobby answered`); "*Note:" stays
    if (re.match(r"\s*\*[A-Z]", text) and not _in_quote(before)
            and re.search(r'[.,?!]"', text)):
        text = re.sub(r"^(\s*)\*", r'\1"', text, count=1)
    # The rest only inside a quote: in nonfiction the same `.?`, `.*` and
    # `.®` are footnote numbers after a sentence.
    def closing(pattern: str, repl: str, text: str) -> str:
        def sub(m: re.Match) -> str:
            if _in_quote(before + " " + text[:m.start()]):
                return m.expand(repl)
            return m.group(0)
        return re.sub(pattern, sub, text)

    # the quote after end punctuation read as i or ii ("screwed.ii This")
    text = re.sub(r'(?<=[a-z])([.?!,])ii?(?=\s|$)', r'\1"', text)
    # `.”` read as `.?` (`...?` is real)
    text = closing(r"(?<=[A-Za-z])\.\?(?=\s|$)", '."', text)
    # a quote after end punctuation read as ® or *, and `"word®`
    text = closing(r'(?<=[.?!,])[®*](?=\s|$)', '"', text)
    text = re.sub(r'((?:^|\s)"[A-Za-z][^"®]{0,40})®', r'\1"', text)
    # any ® left after end punctuation is a lost quote or a footnote mark,
    # never a trademark; a speech app would read it out
    text = re.sub(r'(?<=[.?!])®(?=\s|$)', '', text)
    return text


# A line that ends a sentence: a stop, maybe inside a closing quote or
# bracket, or a quote broken off with a dash, or closed after a word whose
# stop Vision lost ('sitting in it"'), which still ends what was said.
_SENTENCE_END = re.compile(r"(?:[.?!][\"”’')\]*®]*|[-—–][\"”]|[A-Za-z][\"”])\s*$")


def fix_lines(lines: list[str], is_word: Optional[Callable[[str], bool]] = None,
              skip: Callable[[str], bool] = lambda s: False) -> list[str]:
    """fix_line() over the book's lines, with "" at paragraph breaks.

    Lines for which `skip` is true (page delimiters, headings) pass through
    untouched. A heading starts a new paragraph, and so does a blank line
    after a finished sentence: clean.py ignores a break mid-sentence, so the
    paragraph, and any quote open in it, goes on. A page delimiter doesn't,
    since a paragraph runs on over the page turn.
    """
    out = []
    para: list[str] = []
    for i, line in enumerate(lines):
        if not line.strip():
            out.append(line)
            if para and _SENTENCE_END.search(para[-1]):
                para = []
            continue
        if skip(line):
            out.append(line)
            if not line.startswith("====="):
                para = []
            continue
        after = next((l for l in lines[i + 1:i + 4] if l.strip() and not skip(l)), "")
        fixed = fix_line(line, " ".join(para), after, is_word)
        out.append(fixed)
        para.append(fixed)
    return out
