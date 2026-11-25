"""The Windows helper: everything is tested on fake ProPresenter folders (there is no real ProPresenter here)."""

import json
import shutil
from pathlib import Path

import pytest

from lpbibles import windows_helper as wh
from lpbibles.model import BibleError, ParsedBible

LIST = ('InstalledBiblesNew=["6fb4fb55-78a4-43bc-ac6a-076818c7abfc|BB|BasisBijbel|1",'
        '"0aa4c0f1-2b7d-4c1a-8f3e-4d5b6c7e8f90|KJV|King James|1"];\n')


def bible(name="Test Bible", short="TB"):
    pb = ParsedBible(name=name, short=short, language="English", lang_code="eng")
    for b in range(1, 67):
        pb.add(b, 1, 1, f"Book {b}.")
    return pb


def propresenter(tmp_path, text=LIST):
    folder = tmp_path / "ProgramData" / "RenewedVision" / "ProPresenter" / "Bibles"
    folder.mkdir(parents=True)
    (folder / "BibleData.proPref").write_text(text, encoding="utf-8")
    return folder


def codes_free(folder):
    return [f["internalAbbreviation"] for f in wh.free_bibles(folder)]


def test_find_and_list_free_bibles(tmp_path):
    assert wh.find_bibles_folder(str(tmp_path / "ProgramData")) is None          # ProPresenter is not here
    folder = propresenter(tmp_path)
    assert wh.find_bibles_folder(str(tmp_path / "ProgramData")) == folder
    free = codes_free(folder)
    assert "BB" not in free and "RVA" in free                                      # an installed one is not offered
    assert len(wh.free_bibles(None)) >= len(free)                                  # without a list: all of them


def test_prepare_with_propresenter_here(tmp_path):
    folder = propresenter(tmp_path, LIST + "OtherSetting=1;\n")
    before = (folder / "BibleData.proPref").read_bytes()
    ready = tmp_path / "Ready"
    p = wh.prepare([bible("King James Version", "KJV"), bible("Dutch | Bible \"NB\"]", "NB")], ["RVA", "BKR"], ready, folder)
    assert (folder / "BibleData.proPref").read_bytes() == before                    # ProPresenter was not touched
    assert len(p.folders) == 2 and all((f / "USX_1" / "JHN.usx").exists() for f in p.folders)
    new = (ready / "BibleData.proPref").read_text(encoding="utf-8")
    assert "OtherSetting=1;" in new and "BasisBijbel" in new                          # the rest of the file stays
    entries = json.loads(new.split("InstalledBiblesNew=")[1].split(";")[0])
    assert len(entries) == 4 and entries[2].split("|")[1:] == ["RVA", "King James Version", "1"]
    assert entries[3].split("|")[1:] == ["BKR", "Dutch / Bible NB", "1"]              # | " ] cannot break the list
    # the Bible's own metadata carries the code of the free Bible it replaces
    assert "<abbreviation>RVA</abbreviation>" in (p.folders[0] / "rvmetadata.xml").read_text(encoding="utf-8")


def test_prepare_without_propresenter_makes_the_lines(tmp_path):
    p = wh.prepare([bible(), bible("Two", "TW")], ["RVA", "BKR"], tmp_path / "Ready", None)
    assert p.new_pref is None and p.lines_file.name == wh.LINES_FILE
    lines = p.lines_file.read_text(encoding="utf-8").strip().split(",\n")
    assert [json.loads(x).split("|")[1] for x in lines] == ["RVA", "BKR"]


@pytest.mark.parametrize("codes,message", [(["RVA", "RVA"], "different"), (["BB", "RVA"], "already installed"), (["NOPE", "RVA"], "already installed")])
def test_prepare_refuses_bad_choices(tmp_path, codes, message):
    folder = propresenter(tmp_path)
    with pytest.raises(BibleError, match=message):
        wh.prepare([bible(), bible("Two", "TW")], codes, tmp_path / "Ready", folder)
    assert not (tmp_path / "Ready").exists()                                         # nothing was made


def test_prepare_refuses_a_list_it_cannot_read(tmp_path):
    folder = propresenter(tmp_path, "this is not the file we know")
    with pytest.raises(BibleError):
        wh.prepare([bible()], ["RVA"], tmp_path / "Ready", folder)
    assert not (tmp_path / "Ready").exists()


def make_ready(tmp_path, n=1):
    folder = propresenter(tmp_path)
    codes = ["RVA", "BKR", "ALBB"][:n]
    p = wh.prepare([bible(f"Bible {i}", f"B{i}") for i in range(n)], codes, tmp_path / "Ready", folder)
    return folder, p


def test_install_puts_everything_in_place_and_keeps_the_old_list(tmp_path):
    folder, p = make_ready(tmp_path, 2)
    old = (folder / "BibleData.proPref").read_bytes()
    done = wh.install(p, running=lambda: False)
    assert (folder / "BibleData.proPref.old").read_bytes() == old                     # the old list is kept
    assert all((folder / i / "rvmetadata.xml").exists() for i in done.ids)
    text = (folder / "BibleData.proPref").read_text(encoding="utf-8")
    assert "BasisBijbel" in text and all(i in text for i in done.ids)
    assert p.folders[0].exists()                                                       # the ready folder is left alone
    assert not [x for x in folder.iterdir() if x.name.endswith(".part")]               # no temporary files


def test_install_refuses_while_propresenter_is_open(tmp_path):
    folder, p = make_ready(tmp_path)
    before = sorted(x.name for x in folder.iterdir())
    with pytest.raises(BibleError, match="open"):
        wh.install(p, running=lambda: True)
    assert sorted(x.name for x in folder.iterdir()) == before


def test_install_refuses_when_the_list_changed_since(tmp_path):
    folder, p = make_ready(tmp_path)
    (folder / "BibleData.proPref").write_text(LIST.replace("BasisBijbel", "Changed"), encoding="utf-8")
    with pytest.raises(BibleError, match="changed"):
        wh.install(p, running=lambda: False)
    assert "Changed" in (folder / "BibleData.proPref").read_text(encoding="utf-8")
    assert not (folder / "BibleData.proPref.old").exists()


def test_install_rolls_back_when_something_fails(tmp_path, monkeypatch):
    folder, p = make_ready(tmp_path, 2)
    before = sorted(x.name for x in folder.iterdir())
    old = (folder / "BibleData.proPref").read_bytes()
    real = shutil.copytree
    calls = []

    def flaky(src, dst, *a, **k):
        if Path(dst).parent == folder:               # a whole Bible folder (not one of its inner folders)
            calls.append(dst)
            if len(calls) == 2:
                raise PermissionError("denied")
        return real(src, dst, *a, **k)
    monkeypatch.setattr(shutil, "copytree", flaky)
    with pytest.raises(BibleError, match="administrator"):
        wh.install(p, running=lambda: False)
    assert sorted(x.name for x in folder.iterdir()) == before                          # first folder removed, no backup left
    assert (folder / "BibleData.proPref").read_bytes() == old


def test_a_raw_copy_error_is_never_shown_as_it_is(tmp_path, monkeypatch):
    folder, p = make_ready(tmp_path)
    monkeypatch.setattr(shutil, "copytree", lambda *a, **k: (_ for _ in ()).throw(shutil.Error([("a", "b", "disk problem")])))
    with pytest.raises(BibleError) as e:
        wh.install(p, running=lambda: False)
    assert "Nothing was changed" in str(e.value) and "('a'" not in str(e.value)
    assert not (folder / "BibleData.proPref.old").exists()


def test_a_second_install_keeps_the_first_backup(tmp_path):
    folder, p = make_ready(tmp_path)
    first = wh.install(p, running=lambda: False)
    p2 = wh.prepare([bible("Another", "AN")], ["ALBB"], tmp_path / "Ready2", folder)
    second = wh.install(p2, running=lambda: False)
    assert first.backup.name == "BibleData.proPref.old" and second.backup.name == "BibleData.proPref.old-2"


def test_undo_removes_only_our_bibles(tmp_path):
    folder, p = make_ready(tmp_path, 2)
    done = wh.install(p, running=lambda: False)
    # ProPresenter (or the person) adds another Bible afterwards
    text = (folder / "BibleData.proPref").read_text(encoding="utf-8")
    (folder / "BibleData.proPref").write_text(wh.add_entries(text, ["11111111-2222-3333-4444-555555555555|XYZ|Later|1"]), encoding="utf-8")
    with pytest.raises(BibleError, match="open"):
        wh.undo(done, running=lambda: True)
    wh.undo(done, running=lambda: False)
    text = (folder / "BibleData.proPref").read_text(encoding="utf-8")
    assert "Later" in text and "BasisBijbel" in text and not any(i in text for i in done.ids)
    assert not any((folder / i).exists() for i in done.ids)


def test_permission_problem_is_explained_plainly(tmp_path, monkeypatch):
    folder, p = make_ready(tmp_path)
    monkeypatch.setattr(wh, "_backup", lambda pref: (_ for _ in ()).throw(PermissionError("denied")))
    with pytest.raises(BibleError, match="administrator"):
        wh.install(p, running=lambda: False)


def test_the_check_for_a_running_propresenter_is_safe_off_windows():
    assert wh.is_propresenter_running() is False


# ---- found in the review of the Windows code ----------------------------------------------------------

def test_list_with_a_bracket_in_a_name_or_a_bom_or_a_leading_line_is_read(tmp_path):
    for text in ('InstalledBiblesNew=["6fb4fb55-78a4-43bc-ac6a-076818c7abfc|BB|Bible [NT] \\"x\\"|1"];\n',
                 "﻿" + LIST, "// settings\n" + LIST):
        folder = tmp_path / str(abs(hash(text)))
        folder.mkdir()
        (folder / "BibleData.proPref").write_bytes(text.encode("utf-8"))
        assert "RVA" in codes_free(folder)
        p = wh.prepare([bible()], ["RVA"], folder / "Ready", folder)
        new = p.new_pref.read_bytes().decode("utf-8")
        assert new.startswith(text.split("InstalledBiblesNew=")[0]) and new.count("|RVA|") == 1
        assert text.split("];")[0].split("InstalledBiblesNew=[")[1] in new      # the old entry is written as it was


def test_the_list_keeps_its_spacing_and_line_endings(tmp_path):
    for sep in (",", ", "):
        text = f'InstalledBiblesNew=["6fb4fb55-78a4-43bc-ac6a-076818c7abfc|BB|A|1"{sep}"0aa4c0f1-2b7d-4c1a-8f3e-4d5b6c7e8f90|KJV|B|1"];\r\nOther=1;\r\n'
        folder = propresenter(tmp_path / ("s" + str(len(sep))), text)
        p = wh.prepare([bible()], ["RVA"], tmp_path / ("R" + str(len(sep))), folder)
        new = p.new_pref.read_bytes()
        assert b"\r\r" not in new and new.endswith(b"Other=1;\r\n") and new.count(b"\r\n") == 2
        assert f'|1"{sep}"'.encode() in new
        done = wh.install(p, running=lambda: False)
        wh.undo(done, running=lambda: False)
        assert (folder / "BibleData.proPref").read_bytes() == text.encode()           # exactly as it was


def test_a_list_that_is_not_text_is_a_plain_message(tmp_path):
    folder = propresenter(tmp_path)
    (folder / "BibleData.proPref").write_bytes(b"\xff\xfe\x00bad")
    with pytest.raises(BibleError):
        wh.prepare([bible()], ["RVA"], tmp_path / "R", folder)
    assert not (tmp_path / "R").exists()


def test_a_bible_that_cannot_be_made_is_named(tmp_path):
    bad = ParsedBible(name="Short Bible", short="SB")
    bad.add(1, 1, 1, "x")
    with pytest.raises(BibleError) as e:
        wh.prepare([bad], ["RVA"], tmp_path / "R", None)
    assert "Short Bible" in str(e.value) and not (tmp_path / "R").exists()


def test_asking_windows_if_propresenter_is_open_never_crashes(monkeypatch):
    import subprocess
    monkeypatch.setattr(wh.sys, "platform", "win32")
    def boom(*a, **k):
        raise UnicodeDecodeError("cp1252", b"\x81", 0, 1, "x")
    monkeypatch.setattr(subprocess, "run", boom)
    assert wh.is_propresenter_running() is False
    class R:
        stdout = b'"Idle","0"\r\n"ProPresenter.exe","123"\r\n'
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: R())
    assert wh.is_propresenter_running() is True
    R.stdout = b'"BibleImporter.exe","9"\r\n'
    assert wh.is_propresenter_running() is False


def test_a_locked_temp_file_does_not_fail_a_good_copy(tmp_path, monkeypatch):
    from lpbibles import export_pp
    src = tmp_path / "a.rvbible"
    src.write_bytes(b"x")
    real = Path.unlink
    def locked(self, *a, **k):
        if self.name.endswith(".part"):
            raise PermissionError("held by a virus scanner")
        return real(self, *a, **k)
    monkeypatch.setattr(Path, "unlink", locked)
    assert export_pp.copy_without_overwriting(src, tmp_path / "out").read_bytes() == b"x"
