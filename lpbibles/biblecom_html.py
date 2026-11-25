"""Reads the chapter pages of Bible.com.

The functions here come from the original command-line tool (bible_import.py), unchanged in
behaviour, so the command-line tool and the app share one copy. They turn the HTML of a chapter
into USX elements; `usx_verses` then reads the verses out of them.
"""

import itertools
import re
import string

import lxml.html
from lxml.etree import Element, SubElement

from .model import ParsedBible
from .books import book_number


# adaptation of the app Java code youversion.bible.reader.api.impl.ChapterContentData.decode
def decode_yves_bytes(input_bytes):
    i2 = len(input_bytes)
    bArr = bytearray(input_bytes)
    for i3 in range(0, i2, 2):
        i4 = i3 + 1
        if i2 > i4:
            temp_i4 = ((bArr[i3] & 255) >> 5) | ((bArr[i3] & 255) << 3)
            bArr[i3] = ((bArr[i4] & 255) >> 5) | ((bArr[i4] & 255) << 3) & 0xFF
            bArr[i4] = temp_i4 & 0xFF
        else:
            bArr[i3] = (((bArr[i3] & 255) >> 5) | ((bArr[i3] & 255) << 3)) & 0xFF

    # Convert the modified bytearray back to bytes for decoding
    str_output = bytes(bArr).decode("UTF-8", errors="ignore")
    return str_output

def parse_chapter(parent, chapter):
    chapter_num = chapter.attrib["data-usfm"].split(".")[-1]

    try:
        chapter_num = str(int(chapter_num))
    except:
        pass

    if chapter_num.isnumeric():
        SubElement(parent, 'chapter', number=chapter_num, style='c')

        for el in chapter:
            heading = el.xpath(".//*[contains(@class,'heading')]")
            if len(heading) > 0:
                parse_header(parent, heading)
            else:
                parse_paragraph(parent, el, "p")
    else:
        print(f"[SKIPPING CHAPTER] Bible chapter has invalid chapter number: {chapter_num}")

def parse_verse_numbers(verse_label: str, verse):
    verse_input = verse_label.strip()

    def extract_verse_from_label(inp: str):
        matches = re.match(r"(?P<verse_int>\d+)(?P<verse_alpha>[a-z])?", inp.strip())
        return (int(matches["verse_int"]), matches["verse_alpha"]) if matches else None
    
    def extract_verse_from_span(span):
        try:
            # matches based on class names like 'v1 v2 v3' etc.
            return [int(x[1:]) for x in span.classes if re.match(r"v\d+", x)] if span is not None and "verse" in span.classes else None
        except:
            return None

    # in the exceptional translations where verses are returned in ranges
    if "-" in verse_input:
        range_numbers = verse_input.split("-", 1)

        lower = extract_verse_from_label(range_numbers[0])
        upper = extract_verse_from_label(range_numbers[-1])

        # ensures that ranges require an upper and lower bound
        if isinstance(lower, tuple) and isinstance(upper, tuple):
            ranges = range(lower[0], upper[0])
            return [range_numbers[0], *ranges[1:], range_numbers[-1]]
    # single verse
    elif extract_verse_from_label(verse_input):
        return [verse_input]

    # if label based matching fails, try it using the span classes
    # fixes bug #15 - Related to the fact that UKR Bible 1755 in ECC5.19 the label is displayed as - (dash) https://www.bible.com/bible/1755/ECC.5
    return extract_verse_from_span(verse)

def parse_paragraph(parent, paragraph, style):
    verses = paragraph.xpath(".//*[contains(@class,'verse')]")
    for verse in verses:
        verse_number_el = verse.xpath('.//span[@class="label"]')
        if len(verse_number_el) == 0:
            continue

        verse_number_label = verse_number_el[0].text
        verse_number_parent = verse_number_el[0].getparent()
        verse_numbers = parse_verse_numbers(verse_number_label, verse_number_parent)

        if not verse_numbers:
            continue

        paragraph_el = SubElement(parent, 'para', style=style)
        verse_el = SubElement(paragraph_el, 'verse', number=verse_number_label, style='v')

        # retrieve all verse text components - strip alphanumeric suffix
        verse_number_classes = ' '. join(["v" + str(x).rstrip(string.ascii_lowercase) for x in verse_numbers])
        verse_texts = verse.xpath('//*[@class="verse ' + verse_number_classes + '"]//span[@class="content"]')
        # group by div-tag, these will be text blocks for a single line
        groups = itertools.groupby(verse_texts, lambda x: next(an for an in x.iterancestors() if an.tag == 'div'))
        # trim all texts and omit whitespace texts, then join them by a line separator
        verse_text = '\n'.join([''.join([x.text_content() for x in group_values]).strip() for parent, group_values in groups])
        # verse contents post-processing
        verse_el.tail = cleanup_verse_contents(verse_text.strip())

def parse_header(parent, headers):
    header_el = SubElement(parent, 'para', style="s1")

    verses = list(itertools.chain(*[header.xpath(".//text()") for header in headers]))
    header_el.text = ''.join(verses).strip()

def cleanup_verse_contents(text):
    # Remove multiple whitespaces, don't consider new lines
    a = re.sub(r"([^\S\n])+", r"\1", text)
    # Remove spaces in between specific punctuation sequences
    a = re.sub(r"([\"'“”‘’«»‹›„‚”’])[^\S\n]+([\"'“”‘’«»‹›„‚”’.,!:;])", r"\1\2", a)
    a = re.sub(r"([.,!:;])[^\S\n]+([.,!:;])", r"\1\2", a)

    # Fixes issue #4 - Bible.com mistakenly contains paragraph characters
    # Specifically at this verse: https://www.bible.com/bible/2692/ISA.27.2.NASB2020
    # consider deletion if source is updated
    a = a.replace('¶', '')
    return a


def chapter_to_usx(html: str):
    """The USX element of one chapter page, or None when the page has no chapter in it."""
    tree = lxml.html.fromstring(html)
    found = tree.xpath("//*[contains(@class, 'chapter')]")
    if not found:
        return None
    usx = Element("usx", version="2.0")
    parse_chapter(usx, found[0])
    return usx


def usx_verses(usx, book: int, out: ParsedBible) -> int:
    """Adds the verses of a chapter's USX elements to `out`. Returns how many verse elements were read."""
    chapter = 0
    count = 0
    for el in usx:
        if el.tag == "chapter":
            try:
                chapter = int(el.get("number"))
            except (TypeError, ValueError):
                chapter = 0
        elif el.tag == "para" and chapter:
            for v in el.iter("verse"):
                m = re.match(r"\s*(\d+)", v.get("number") or "")
                if not m:
                    continue
                # A range label ("3-4") is stored at its first verse; "3a" and "3b" are joined.
                out.add(book, chapter, int(m.group(1)), v.tail or "")
                count += 1
    return count


def add_chapter(html: str, book_code: str, out: ParsedBible) -> bool:
    """Reads one chapter page into `out`. False when the chapter was skipped."""
    book = book_number(book_code)
    if not book:
        return False
    try:
        usx = chapter_to_usx(html)
        return usx is not None and usx_verses(usx, book, out) > 0
    except (KeyError, IndexError, ValueError, TypeError, StopIteration):
        return False
