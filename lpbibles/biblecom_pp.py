"""The ProPresenter files of a Bible.com Bible, made exactly as the original command-line tool made them.

`toxml`, `construct_metadataxmls` and the book-by-book USX building (`build_usx`, the same steps as the
original `process_bible_files`) are the original code, moved here so the command-line tool and the app share
one copy. tests/test_original_parity.py runs the untouched original script and this module on the same
chapter pages and checks that the files are byte for byte the same.
"""

from __future__ import annotations

import os
import re

import lxml.html
from lxml import etree as ElementTree
from lxml.etree import Element, SubElement, tostring

from .biblecom_html import parse_chapter
from .model import xml_safe
from .paths import resource_path


def toxml(elem):
    """Return a XML string for the Element."""
    return tostring(elem, encoding='utf-8')


def build_usx(chapters: dict) -> dict:
    """book code -> (USX bytes, USX element), from {book code: {chapter number: chapter page HTML}}.

    Same as the original `process_bible_files`: chapters of a book in numeric order, one <usx> per book,
    every book kept (also books outside the usual 66).
    """
    out = {}
    for book_code, pages in chapters.items():
        # Create the root element
        usx = Element('usx', version='2.0')
        SubElement(usx, 'book', code=book_code).text = book_code

        for number in sorted(pages):
            tree = lxml.html.fromstring(pages[number])
            found = tree.xpath("//*[contains(@class, 'chapter')]")
            if not found:       # (the original stops with an error here; a page without a chapter is skipped)
                continue
            parse_chapter(usx, found[0])

        out[book_code] = (toxml(usx), usx)
    return out


def chapter_key(name: str):
    """('GEN', 1) from a chapter identifier such as "GEN.1" or "GEN.1.NBV21"; None when it is not one."""
    if not re.match(r"[A-Z0-9]{3}\.\d+", name):
        return None
    return name[:3], int(name.split(".")[1])


def construct_metadataxmls(output_file_loc, book_metadata):
    metadata = resource_path("metadata.xml")
    xml_tree = ElementTree.parse(metadata)

    identification_el = xml_tree.xpath("//identification")[0]
    SubElement(identification_el, "name").text = book_metadata["title"]
    SubElement(identification_el, "nameLocal").text = book_metadata["local_title"]
    SubElement(identification_el, "abbreviation").text = book_metadata["abbreviation"]
    SubElement(identification_el, "abbreviationLocal").text = book_metadata["local_abbreviation"]

    language_el = xml_tree.xpath("//language")[0]
    SubElement(language_el, "iso").text = book_metadata["language"]['iso_639_3']
    SubElement(language_el, "name").text = book_metadata["language"]['name']
    SubElement(language_el, "scriptDirection").text = book_metadata["language"]['text_direction']

    book_names_el = xml_tree.xpath("//bookNames")[0]
    books_el = xml_tree.xpath("//bookList/books")[0]
    unique_short_list = []

    for book in book_metadata["books"]:
        book_code = book['usfm']
        canon = book['canon']
        short = book['human']
        long = book['human_long']
        abbr = book['abbreviation']
        book_el = SubElement(book_names_el, "book", code=book_code)
        SubElement(book_el, 'long').text = long
        SubElement(book_el, 'short').text = short if short not in unique_short_list else long
        SubElement(book_el, 'abbr').text = abbr

        SubElement(books_el, "book", code=book_code)

        unique_short_list.append(short)

    metadataxml_output = os.path.join(output_file_loc, "metadata.xml")
    with open(metadataxml_output, 'wb') as handle:
        handle.write(toxml(xml_tree))

    root = Element("RVBibleMetdata")
    SubElement(root, "name").text = book_metadata["local_title"]
    SubElement(root, "abbreviation").text = book_metadata["abbreviation"]
    SubElement(root, "displayAbbreviation").text = book_metadata["local_abbreviation"]
    SubElement(root, "version").text = "1"
    SubElement(root, "revision").text = "0"
    SubElement(root, "licenseType").text = "0"
    SubElement(root, "license")

    rvmetadataxml_output = os.path.join(output_file_loc, "rvmetadata.xml")
    with open(rvmetadataxml_output, 'wb') as handle:
        handle.write(toxml(root))


def slim_metadata(meta: dict) -> dict:
    """Only what `construct_metadataxmls` reads (the full Bible.com answer is large).
    Control characters are removed, because XML cannot hold them (nothing changes for normal text)."""
    x = xml_safe
    lang = meta.get("language") or {}
    return {
        "title": x(meta.get("title", "")), "local_title": x(meta.get("local_title", "")),
        "abbreviation": x(meta.get("abbreviation", "")), "local_abbreviation": x(meta.get("local_abbreviation", "")),
        "language": {"iso_639_3": x(lang.get("iso_639_3", "")), "name": x(lang.get("name", "")),
                     "text_direction": x(lang.get("text_direction", "ltr"))},
        "books": [{"usfm": x(b.get("usfm", "")), "canon": x(b.get("canon", "")), "human": x(b.get("human", "")),
                   "human_long": x(b.get("human_long", "")), "abbreviation": x(b.get("abbreviation", ""))}
                  for b in (meta.get("books") or [])],
    }
