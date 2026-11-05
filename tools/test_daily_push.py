import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import daily_push as dp  # noqa: E402


def test_secrets_and_personal_data_are_caught():
    # قيمٌ مصطنعةٌ مقسومة: السكربتُ يفحص ملفَّ اختباره أيضاً حين يخرج
    for line, name in [
        ("t = 'ghp_" + "a" * 36 + "'", "رمز GitHub"),
        ("sk-ant-" + "a" * 30, "مفتاح Anthropic"),
        ("-----BEGIN RSA PRIV" + "ATE KEY", "مفتاح خاصّ"),
        ("postgres://u:real" + "pass@db/x", "رابط بكلمة مرور"),
        ('pass' + 'word = "hunter2hunter2"', "كلمة مرور صريحة"),
        ("الرقم 2876340" + "0123", "رقم شخصيّ قطريّ"),
        ("+97" + "4 55123456", "هاتف قطريّ"),
        ("someone@edu" + "cation.qa", "بريد إلكترونيّ"),
    ]:
        assert name in dp.scan_line(line), line


def test_clean_lines_pass():
    for line in ["Co-Authored-By: Claude <noreply@anthropic.com>", "user@example.com رقم 123456789", "ts = 1730000000000",
                 'password = os.environ["X"]', "postgres://u:{pw}@db/x"]:
        assert dp.scan_line(line) == [], line


def test_only_added_lines_count_and_the_report_hides_the_value():
    secret = "ghp_" + "b" * 36
    patch = "+++ b/a.py\n-" + secret + "\n+x = 1\n+++ b/c.py\n+" + secret + "\n"
    found = dp.scan_patch(patch)
    assert found == ["رمز GitHub: c.py"] and secret not in found[0]


def test_binary_file_stops_the_push():
    assert dp.scan_patch("Binary files /dev/null and b/a.png differ\n")


def test_forbidden_file_names():
    for name in ["tools/.preview_accounts.env", ".env", "a/b.pem", "ledger/events.jsonl", "local_preview_pw.txt"]:
        assert dp.BAD_FILE.search(name), name
    assert not dp.BAD_FILE.search("tools/runner.py")


class Git:
    def __init__(self, **out):
        self.out, self.calls = out, []

    def __call__(self, *args):
        self.calls.append(args)
        text = self.out.get(args[0], "")
        return dp.subprocess.CompletedProcess(args, 0, text, "")


def _run(monkeypatch, argv=(), **out):
    fake = Git(**out)
    stops = []
    monkeypatch.setattr(dp, "git", fake)
    monkeypatch.setattr(dp, "stop", lambda msg, code: stops.append(msg) or code)
    return dp.main(list(argv)), fake, stops


def test_main_branch_is_never_pushed(monkeypatch):
    code, fake, stops = _run(monkeypatch, branch="main\n", **{"rev-list": "a\n"})
    assert code == 2 and stops and not any(c[0] == "push" for c in fake.calls)


def test_a_hit_stops_before_push(monkeypatch):
    code, fake, _ = _run(monkeypatch, branch="b\n", log="+++ b/a.py\n+someone@edu" + "cation.qa\n", **{"rev-list": "a\n"})
    assert code == 1 and not any(c[0] == "push" for c in fake.calls)


def test_clean_push_has_no_force_and_keeps_the_same_branch(monkeypatch):
    code, fake, _ = _run(monkeypatch, branch="b\n", **{"rev-list": "a\n"})
    assert code == 0 and ("push", "origin", "HEAD:refs/heads/b") in fake.calls


def test_dry_never_pushes(monkeypatch):
    code, fake, _ = _run(monkeypatch, ["--dry"], branch="b\n", **{"rev-list": "a\n"})
    assert code == 0 and not any(c[0] == "push" for c in fake.calls)
