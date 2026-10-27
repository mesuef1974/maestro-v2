"""اختبارات قياس الرموز (W-20261013-029): عدٌّ معلوم، لا كتابة على المقيس، رفضُ --api."""
import hashlib
import subprocess
import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).parent))
import token_measure as tm  # noqa: E402

TOOL = Path(__file__).parent / "token_measure.py"


def test_counts_a_known_text_with_a_real_tokenizer(tmp_path):
    f = tmp_path / "a.md"
    f.write_text("hello world", encoding="utf-8")
    assert tm.count("hello world") == 2
    out = subprocess.run([sys.executable, str(TOOL), "--file", str(f), "--json"], capture_output=True, text=True, encoding="utf-8")
    assert out.returncode == 0 and '"tokens": 2' in out.stdout


def test_measuring_never_writes_to_the_measured_files(tmp_path):
    f = tmp_path / "b.md"
    f.write_text("مرحبا بالعالم\n", encoding="utf-8")
    before = (hashlib.sha256(f.read_bytes()).hexdigest(), f.stat().st_mtime_ns)
    subprocess.run([sys.executable, str(TOOL), "--file", str(f)], capture_output=True)
    assert (hashlib.sha256(f.read_bytes()).hexdigest(), f.stat().st_mtime_ns) == before


def test_the_external_api_flag_is_refused():
    out = subprocess.run([sys.executable, str(TOOL), "--api"], capture_output=True, text=True, encoding="utf-8")
    assert out.returncode != 0 and "إذنُ المالك" in (out.stderr + out.stdout)


def test_missing_file_counts_zero_without_error(tmp_path):
    assert tm.count(tm.read(tmp_path / "nope.md")) == 0


def test_roles_json_has_the_same_shape_for_before_after():
    res = tm.measure_roles()
    assert res, "لا أدوار"
    one = next(iter(res.values()))
    assert set(one) == {"components", "total_tokens", "total_estimate"}
    assert one["total_tokens"] == sum(c["tokens"] for c in one["components"].values())
