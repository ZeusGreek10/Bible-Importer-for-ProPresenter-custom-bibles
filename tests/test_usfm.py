import io
import zipfile

from lpbibles import usfm
from lpbibles.model import BibleError, ParsedBible
import pytest

SAMPLE = r"""\id JHN 43-JHN-web.sfm World English Bible (WEB)
\ide UTF-8
\h John
\toc1 The Good News According to John
\mt1 John
\c 1
\p
\v 1 \w In|strong="G1722"\w* \w the|strong="G1722"\w* beginning \w was|strong="G1510"\w* the Word\f + \fr 1:1 \ft Or “Logos”.\f*.
\v 2 The same was in the beginning with God.
\s1 A heading that must not be in a verse
\q1
\v 3 All things were made through him,
\q2 without him nothing was made.
\c 2
\p
\v 1-2 A range of verses \x - \xo 2:1 \xt Mark 1:1\x* here.
\v 3 hasn’\w t|strong="G3588"\w* it
"""


def test_verses_headings_notes_and_attributes():
    pb = ParsedBible()
    usfm.parse_book(SAMPLE, pb)
    assert pb.verses[43][1][1] == "In the beginning was the Word."
    assert pb.verses[43][1][2] == "The same was in the beginning with God."
    # poetry lines continue the verse, the heading does not
    assert pb.verses[43][1][3] == "All things were made through him, without him nothing was made."
    # a range is stored at its first verse; footnote and cross reference are gone
    assert pb.verses[43][2][1] == "A range of verses here."
    assert pb.verses[43][2][3] == "hasn’t it"
    assert 2 not in pb.verses[43][2]


def test_book_outside_the_canon_is_skipped():
    pb = ParsedBible()
    usfm.parse_book("\\id TOB Tobit\n\\c 1\n\\p\n\\v 1 Hidden\n", pb)
    assert pb.verse_count == 0


def test_zip_and_bad_zip():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("43-JHNweb.usfm", SAMPLE)
        z.writestr("readme.txt", "x")
    pb = usfm.parse_zip(buf.getvalue())
    assert pb.verses[43][1][1].startswith("In the beginning")
    with pytest.raises(BibleError):
        usfm.parse_zip(b"not a zip")


def test_validate_needs_enough_books():
    pb = ParsedBible()
    usfm.parse_book(SAMPLE, pb)
    with pytest.raises(BibleError):
        pb.validate()
