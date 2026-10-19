"""تاريخُ العيّنات من monitor.db الأصليّة بقراءةٍ فقط — المرحلة 1 من W-20261017-022.

القاعدة: الأصلُ لا يُمَسّ. لا نفتح monitor.db نفسَها (الفتحُ على قاعدةٍ WAL حيّةٍ قد يلمس ملفَّ -shm)؛ بل ننسخ الملفّين db وwal
إلى مجلّدٍ مؤقّتٍ ونقرأ النسخة بـmode=ro. وبصمةُ sha256 للملفّات الأصليّة قبل القراءة وبعدها تثبت أنها لم تتغيّر بفعلنا
(إن كانت الأداةُ الأصليّةُ تكتب في أثناء ذلك تختلف البصمة لسببٍ ليس منّا، فيُعلَن «تغيّرت من الأصل لا من الأداة» ولا يُخفى).
"""

from __future__ import annotations

import hashlib
import shutil
import sqlite3
import tempfile
from pathlib import Path

SAMPLE_COLUMNS = ("ts", "commit_pct", "ram_pct", "avail_gb", "disk_free_gb", "claude", "shells")


def sha256_of(path: Path) -> str | None:
    if not path.is_file():
        return None
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def fingerprint(db: Path) -> dict[str, str | None]:
    """بصمةُ ملفّات القاعدة الأصليّة الثلاثة (غيابُ ملفٍّ يُسجَّل None)."""
    return {suffix or ".db": sha256_of(db.with_name(db.name + suffix)) for suffix in ("", "-wal", "-shm")}


def read_samples(db: Path, since_ts: int, until_ts: int) -> tuple[list[dict], dict]:
    """عيّناتٌ بين لحظتين من نسخةٍ مؤقّتة؛ يعيد (الصفوف، حالةَ البصمة قبل/بعد). لا يكتب في الأصل."""
    before = fingerprint(db)
    rows: list[dict] = []
    with tempfile.TemporaryDirectory() as tmp:
        copy = Path(tmp) / "snap.db"
        shutil.copyfile(db, copy)
        wal = db.with_name(db.name + "-wal")
        if wal.is_file():
            shutil.copyfile(wal, Path(tmp) / "snap.db-wal")
        con = sqlite3.connect(f"file:{copy.as_posix()}?mode=ro", uri=True)
        try:
            cur = con.execute(
                f"SELECT {', '.join(SAMPLE_COLUMNS)} FROM samples WHERE ts BETWEEN ? AND ? ORDER BY ts",  # noqa: S608
                (since_ts, until_ts),
            )
            rows = [dict(zip(SAMPLE_COLUMNS, r, strict=True)) for r in cur.fetchall()]
        finally:
            con.close()
    after = fingerprint(db)
    return rows, {"before": before, "after": after, "unchanged": before == after}


def summarize(rows: list[dict]) -> dict:
    """ملخّصُ فترة: عددُ العيّنات ومتوسّطُ/أقصى الالتزام والذاكرة وأدنى المتاح — أرقامٌ فقط."""
    if not rows:
        return {"n": 0}

    def col(name: str) -> list[float]:
        return [r[name] for r in rows if r[name] is not None]

    commit, ram, avail = col("commit_pct"), col("ram_pct"), col("avail_gb")
    return {
        "n": len(rows),
        "commit_avg": round(sum(commit) / len(commit), 1) if commit else None,
        "commit_max": max(commit) if commit else None,
        "ram_avg": round(sum(ram) / len(ram), 1) if ram else None,
        "ram_max": max(ram) if ram else None,
        "avail_min_gb": min(avail) if avail else None,
    }
