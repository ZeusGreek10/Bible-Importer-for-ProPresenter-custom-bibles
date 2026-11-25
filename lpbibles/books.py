"""The 66 books of the standard canon: USFM code, English name, short name."""

BOOKS = [
    ("GEN", "Genesis", "Gen"), ("EXO", "Exodus", "Exod"), ("LEV", "Leviticus", "Lev"),
    ("NUM", "Numbers", "Num"), ("DEU", "Deuteronomy", "Deut"), ("JOS", "Joshua", "Josh"),
    ("JDG", "Judges", "Judg"), ("RUT", "Ruth", "Ruth"), ("1SA", "1 Samuel", "1 Sam"),
    ("2SA", "2 Samuel", "2 Sam"), ("1KI", "1 Kings", "1 Kgs"), ("2KI", "2 Kings", "2 Kgs"),
    ("1CH", "1 Chronicles", "1 Chr"), ("2CH", "2 Chronicles", "2 Chr"), ("EZR", "Ezra", "Ezra"),
    ("NEH", "Nehemiah", "Neh"), ("EST", "Esther", "Esth"), ("JOB", "Job", "Job"),
    ("PSA", "Psalms", "Ps"), ("PRO", "Proverbs", "Prov"), ("ECC", "Ecclesiastes", "Eccl"),
    ("SNG", "Song of Songs", "Song"), ("ISA", "Isaiah", "Isa"), ("JER", "Jeremiah", "Jer"),
    ("LAM", "Lamentations", "Lam"), ("EZK", "Ezekiel", "Ezek"), ("DAN", "Daniel", "Dan"),
    ("HOS", "Hosea", "Hos"), ("JOL", "Joel", "Joel"), ("AMO", "Amos", "Amos"),
    ("OBA", "Obadiah", "Obad"), ("JON", "Jonah", "Jonah"), ("MIC", "Micah", "Mic"),
    ("NAM", "Nahum", "Nah"), ("HAB", "Habakkuk", "Hab"), ("ZEP", "Zephaniah", "Zeph"),
    ("HAG", "Haggai", "Hag"), ("ZEC", "Zechariah", "Zech"), ("MAL", "Malachi", "Mal"),
    ("MAT", "Matthew", "Matt"), ("MRK", "Mark", "Mark"), ("LUK", "Luke", "Luke"),
    ("JHN", "John", "John"), ("ACT", "Acts", "Acts"), ("ROM", "Romans", "Rom"),
    ("1CO", "1 Corinthians", "1 Cor"), ("2CO", "2 Corinthians", "2 Cor"), ("GAL", "Galatians", "Gal"),
    ("EPH", "Ephesians", "Eph"), ("PHP", "Philippians", "Phil"), ("COL", "Colossians", "Col"),
    ("1TH", "1 Thessalonians", "1 Thess"), ("2TH", "2 Thessalonians", "2 Thess"),
    ("1TI", "1 Timothy", "1 Tim"), ("2TI", "2 Timothy", "2 Tim"), ("TIT", "Titus", "Titus"),
    ("PHM", "Philemon", "Phlm"), ("HEB", "Hebrews", "Heb"), ("JAS", "James", "Jas"),
    ("1PE", "1 Peter", "1 Pet"), ("2PE", "2 Peter", "2 Pet"), ("1JN", "1 John", "1 John"),
    ("2JN", "2 John", "2 John"), ("3JN", "3 John", "3 John"), ("JUD", "Jude", "Jude"),
    ("REV", "Revelation", "Rev"),
]

CODE_TO_NUM = {code: i + 1 for i, (code, _, _) in enumerate(BOOKS)}

# Other spellings of a book code seen in the wild (YouVersion, older USFM files).
_ALIASES = {"EZE": "EZK", "JOE": "JOL", "NAH": "NAM", "ZEP": "ZEP", "PHI": "PHP", "SON": "SNG",
            "SOS": "SNG", "CAN": "SNG", "PSS": "PSA", "JAM": "JAS", "JUDE": "JUD", "MRC": "MRK",
            "MAR": "MRK", "JOH": "JHN", "JN": "JHN", "REV": "REV", "OBD": "OBA", "HAGG": "HAG"}


def book_number(code: str) -> int:
    """Book number 1..66 for a USFM code, or 0 for a book outside the standard 66."""
    code = (code or "").strip().upper()
    code = _ALIASES.get(code, code)
    return CODE_TO_NUM.get(code, 0)


def code_of(number: int) -> str:
    return BOOKS[number - 1][0]


def english_name(number: int) -> str:
    return BOOKS[number - 1][1]
