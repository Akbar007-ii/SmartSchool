"""Колдонуучу жазган тексттерди текшерүү: уят сөздөр, кокус тамгалар жана тыюу салынган белгилер.

Frontend'де да ушундай текшерүү бар (smart-school: src/lib/textChecks.ts) —
сөздөрдүн тизмесин эки жерде тең өзгөртүү керек.
shortcut: тизме көп кездешкен орой сөздөрдү жана айланып өтүүлөрдү кармайт, бирок баарын эмес —
модерацияны алмаштырбайт.
"""
import re
from typing import Optional

from fastapi import HTTPException

# Фильтрди айланып өтүү үчүн колдонулган окшош латын тамгалары жана сандар: «xуй», «п1зда».
LOOKALIKES = {
    "a": "а", "b": "в", "c": "с", "e": "е", "h": "н", "i": "и", "k": "к", "m": "м", "o": "о",
    "p": "р", "t": "т", "u": "у", "x": "х", "y": "у", "0": "о", "1": "и", "3": "з", "4": "ч",
    "6": "б", "@": "а", "ё": "е",
}

# Сөздүн каалаган жеринде болбошу керек болгон уңгулар (ru, ky).
BLOCKED_ROOTS = (
    "хуй", "хуе", "хуя", "хуи", "пизд", "залуп", "гандон", "шлюх", "пидор", "пидар", "педик", "дроч",
    "ебан", "ебал", "ебат", "ебуч", "еблан", "уеб", "заеб", "выеб", "наеб", "проеб", "мудак", "мудил",
    "говн", "дерьм", "сран", "срат", "жопа", "жопы", "жопу", "секс", "порн", "курв", "блят", "бляд",
    "сучк", "сучар", "кутак", "котак", "жалап", "сигиш", "сигип",
)
# Сөздүн башы гана: башка сөздөрдүн ичинде кадимки сөздөрдө кездешет («небо», «Херсон»).
BLOCKED_WORD_STARTS = ("еб", "бля", "сука", "суки", "сик", "дебил", "идиот", "пидр", "чмо")
BLOCKED_WORDS = {"хер", "лох", "амың", "амыңды", "дурак", "дура", "тупой"}

BLOCKED_LATIN_ROOTS = ("fuck", "fck", "shit", "bitch", "cunt", "porn", "pussy", "whore", "nigg", "dick", "penis")
BLOCKED_LATIN_WORDS = {"ass", "sex", "xxx", "cock", "fag", "slut", "boobs"}

SUBJECT_CHARACTERS = re.compile(r"[^\W_]+|[\s().,-]")
NAME_CHARACTERS = re.compile(r"[^\W\d_]+|[\s'ʼ’.-]")
NOT_LETTERS = re.compile(r"[\W\d_]+")
REPEATED_LETTER = re.compile(r"([^\W\d_])\1\1")

INVALID_CHARS = "Тамгаларды, сандарды, боштукту жана дефисти колдонуңуз"
NAME_CHARS = "Аты-жөнүндө тамгалар, боштук, дефис жана апостроф гана болот"
CLASS_LETTER = "Тамга гана, мисалы А же Б"
GIBBERISH = "Кокустан терилген тамгаларга окшош. Текшериңиз"
INAPPROPRIATE = "Мында жол берилбеген сөздөр бар. Текстти оңдоңуз"
SUBJECT_INAPPROPRIATE = "Мындай аталышка болбойт. Сабакты тизмеден тандаңыз"


def _only(pattern: re.Pattern, text: str) -> bool:
    """Тексттин бардык белгилери pattern'ге туура келеби."""
    return "".join(pattern.findall(text)) == text


def has_inappropriate_words(text: str, join_words: bool = True) -> bool:
    """join_words — сөздөрдү бириктирип да текшерүү («х у й»). Узун текстте өчүк:
    башка сөздөрдүн уландысы кокустан уят уңгуну түзүп калбашы үчүн."""
    lower_text = text.lower()
    cyrillic = "".join(LOOKALIKES.get(letter, letter) for letter in lower_text)
    cyrillic_words = [word for word in NOT_LETTERS.split(cyrillic) if word]
    latin_words = [word for word in re.split(r"[^a-z]+", lower_text) if word]
    cyrillic_parts = ["".join(cyrillic_words)] if join_words else cyrillic_words
    latin_parts = ["".join(latin_words)] if join_words else latin_words

    return (
        any(root in part for part in cyrillic_parts for root in BLOCKED_ROOTS)
        or any(word in BLOCKED_WORDS or word.startswith(BLOCKED_WORD_STARTS) for word in cyrillic_words)
        or any(root in part for part in latin_parts for root in BLOCKED_LATIN_ROOTS)
        or any(word in BLOCKED_LATIN_WORDS for word in latin_words)
    )


def _letter_count(text: str) -> int:
    return sum(1 for char in text if char.isalpha())


def validate_subject_name(name: str) -> str:
    """Туура аталышты кайтарат, болбосо ValueError (ката текстин колдонуучу көрөт)."""
    name = name.strip()
    if not _only(SUBJECT_CHARACTERS, name) or _letter_count(name) < 2:
        raise ValueError(INVALID_CHARS)
    if REPEATED_LETTER.search(name.lower()):
        raise ValueError(GIBBERISH)
    if has_inappropriate_words(name):
        raise ValueError(SUBJECT_INAPPROPRIATE)
    return name


def validate_person_name(name: str) -> str:
    """Аты-жөнү: тамгалар, боштук, дефис, апостроф («Асанов Бакыт уулу», «O'Neil»)."""
    name = " ".join(name.split())
    if not _only(NAME_CHARACTERS, name) or _letter_count(name) < 2:
        raise ValueError(NAME_CHARS)
    if REPEATED_LETTER.search(name.lower()):
        raise ValueError(GIBBERISH)
    if has_inappropriate_words(name):
        raise ValueError(INAPPROPRIATE)
    return name


def validate_class_letter(letter: str) -> str:
    """Класстын тамгасы: 1–3 тамга («А», «Б», «АБ»)."""
    letter = letter.strip()
    if not re.fullmatch(r"[^\W\d_]{1,3}", letter):
        raise ValueError(CLASS_LETTER)
    if has_inappropriate_words(letter):
        raise ValueError(INAPPROPRIATE)
    return letter


def validate_free_text(text: Optional[str]) -> Optional[str]:
    """Эркин текст (жарыялар, комментарийлер): уят сөздөр гана текшерилет."""
    if text is not None and has_inappropriate_words(text, join_words=False):
        raise ValueError(INAPPROPRIATE)
    return text


def check_form_texts(**fields: Optional[str]) -> None:
    """Form(...) менен келген эркин тексттер үчүн: ката болсо Pydantic'тикиндей 422 жооп,
    frontend аны талаанын астында көрсөтөт."""
    errors = [
        {"loc": ["body", name], "msg": INAPPROPRIATE, "type": "value_error"}
        for name, value in fields.items()
        if value is not None and has_inappropriate_words(value, join_words=False)
    ]
    if errors:
        raise HTTPException(status_code=422, detail=errors)
