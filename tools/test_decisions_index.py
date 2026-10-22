import decisions_index as di

SAMPLE = (
    "- D-1م | 09-28 | قرارٌ أول | أثره | مرجع\n"
    "نصٌّ حرٌّ ليس قراراً\n"
    "- D-2م | 09-29 10:00 | قرارٌ ثانٍ يلغي D-1 كلياً | أثر | مرجع\n"
    "## D-3م (2026-10-20، مباشرة): عنوان مقطعي\n"
)


def test_parse_entries_and_headings():
    ids = [r["id"] for r in di.parse(SAMPLE)]
    assert ids == ["D-1م", "D-2م", "D-3م"]


def test_status_heuristic():
    out = di.render(SAMPLE)
    lines = {l.split("|")[1].strip(): l for l in out.splitlines() if l.startswith("| D-")}
    assert "مُعدَّل بـD-2م" in lines["D-1م"]
    assert "ساري" in lines["D-2م"]


def test_idempotent_and_no_loss_of_ids():
    assert di.render(SAMPLE) == di.render(SAMPLE)
    real = di.SRC.read_bytes().decode("utf-8").replace("\r\n", "\n")
    assert len(di.parse(real)) >= 483
    assert di.render(real).count("\n| D-") == len(di.parse(real))


def test_pipe_in_text_does_not_break_table():
    r = di.render("- D-9م | 10-01 | عنوان | فيه | شريط | أثر | م\n")
    assert all(l.count("|") == 6 for l in r.splitlines() if l.startswith("| D-"))
