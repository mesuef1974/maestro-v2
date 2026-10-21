"""مصنِّف شروط التوقف للدمج الآلي (W-20261020-020): كلُّ مجموعةٍ توقف بالرمز الصحيح، والوثائقيُّ الخالص يمرّ، والفشلُ آمن."""

from __future__ import annotations

import pytest
from merge_stop_classifier import (
    PERMISSION_GROUP,
    classify,
    main,
    matches,
    render,
)

SENSITIVE = {
    "version": 2,
    "mandatory_review_when_diff_touches": {
        PERMISSION_GROUP: [
            "core/permissions*.py",
            "core/capabilities.py",
            "core/auth_identity.py",
        ],
        "encryption_and_personal_data": ["core/models/crypto.py", "breach/**"],
        "external_surface_and_api": ["api/**", "parents/**"],
        "production_config_and_deploy": ["shschool/settings/**", "Dockerfile"],
        "security_tables_migrations": ["**/migrations/*.py"],
    },
    "mandatory_review_when_diff_content_matches": {
        "redirects": [r"redirect\(request\.(GET|POST)", r"[?&]next="],
        "new_external_input_endpoints": {
            "files": ["**/urls*.py", "core/urls/*.py"],
            "patterns": [r"^\+\s*(re_)?path\("],
        },
    },
}


def _diff(path: str, *added: str) -> str:
    body = "\n".join(f"+{line}" for line in added)
    return f"diff --git a/{path} b/{path}\n--- a/{path}\n+++ b/{path}\n@@ -1 +1 @@\n{body}\n"


def _value(files, labels=(), diff="", behind=0, sensitive=SENSITIVE):
    return classify(list(files), list(labels), sensitive, diff_text=diff, behind=behind)


def test_pure_docs_pr_is_merge_ok():
    assert _value(["docs/guide.md", "docs/more.md"]).value == "MERGE_OK"


def test_pure_tests_pr_is_merge_ok():
    assert (
        _value(
            ["tests/test_x.py"], diff=_diff("tests/test_x.py", "def test_x(): pass")
        ).value
        == "MERGE_OK"
    )


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("core/models/crypto.py", "STOP_SECURITY"),
        ("api/views_x.py", "STOP_SECURITY"),
        ("shschool/settings/production.py", "STOP_SECURITY"),
        ("requirements.txt", "STOP_SECURITY"),
        ("requirements-dev.txt", "STOP_SECURITY"),
        ("scripts/check_personal_data.py", "STOP_SECURITY"),
        ("clinic/migrations/0013_x.py", "STOP_MIGRATION"),
        ("core/management/commands/fix_rows.py", "STOP_MIGRATION"),
        ("core/permissions_x.py", "STOP_PERMISSION"),
        ("core/capabilities/registry.py", "STOP_PERMISSION"),
        ("core/capability_grants.py", "STOP_PERMISSION"),
        ("db/rls/policies.sql", "STOP_PERMISSION"),
        ("CLAUDE.md", "STOP_GOVERNING"),
        (".claude/rules/deploy-window.md", "STOP_GOVERNING"),
        ("docs/governance/flow.md", "STOP_GOVERNING"),
        (".github/workflows/quality-gate.yml", "STOP_GOVERNING"),
        ("scripts/deploy_window.py", "STOP_GOVERNING"),
        ("scripts/ci_docs_only.py", "STOP_GOVERNING"),
        ("security/sensitive_paths.json", "STOP_GOVERNING"),
        ("tabs.json", "STOP_GOVERNING"),
        ("role_cards/0601.md", "STOP_GOVERNING"),
        ("decisions.md", "STOP_GOVERNING"),
    ],
)
def test_each_excluded_path_stops_with_the_right_code(path, expected):
    verdict = _value(["docs/a.md", path])
    assert verdict.value == expected or expected in {c for c, _ in verdict.reasons}
    assert verdict.value != "MERGE_OK"
    assert any(path in why for _, why in verdict.reasons)


def test_value_is_the_highest_priority_but_all_reasons_are_shown():
    verdict = _value(
        ["clinic/migrations/0013_x.py", "CLAUDE.md", "core/permissions_x.py"]
    )
    codes = {c for c, _ in verdict.reasons}
    assert {
        "STOP_SECURITY",
        "STOP_MIGRATION",
        "STOP_PERMISSION",
        "STOP_GOVERNING",
    } <= codes
    assert (
        verdict.value == "STOP_SECURITY"
    )  # الهجرة تقع أيضاً في قائمة الأمن (security_tables_migrations)


def test_runpython_in_added_lines_stops_as_migration():
    diff = _diff("core/services/backfill.py", "    migrations.RunPython(fwd, rev)")
    verdict = _value(["core/services/backfill.py"], diff=diff)
    assert verdict.value == "STOP_MIGRATION"


def test_content_pattern_redirect_from_next_stops():
    diff = _diff("core/views_x.py", "    return redirect(request.GET['next'])")
    assert _value(["core/views_x.py"], diff=diff).value == "STOP_SECURITY"


def test_new_path_in_urls_stops_but_other_files_with_path_text_do_not():
    diff = _diff("core/urls/x.py", "    path('x/', view),")
    assert _value(["core/urls/x.py"], diff=diff).value == "STOP_SECURITY"
    docs_diff = _diff("docs/a.md", "    path('x/', view),")
    assert _value(["docs/a.md"], diff=docs_diff).value == "MERGE_OK"


def test_unreadable_sensitive_list_is_security_stop():
    verdict = _value(["docs/a.md"], sensitive=None)
    assert verdict.value == "STOP_SECURITY"


def test_malformed_sensitive_list_is_security_stop():
    verdict = _value(["docs/a.md"], sensitive={"version": 2})
    assert verdict.value == "STOP_SECURITY"


def test_empty_diff_is_a_stop_not_ok():
    assert _value([]).value == "STOP_GENERAL"


def test_pr_cannot_loosen_the_list_it_is_classified_by():
    """القائمة تُقرأ من الأساس: طلبٌ يخفّف القائمة نفسَها يتوقف بـSTOP_GOVERNING ولا ينجو بتخفيفها."""
    loosened = {
        **SENSITIVE,
        "mandatory_review_when_diff_touches": {"x": ["nothing/**"]},
    }
    verdict = _value(
        ["security/sensitive_paths.json", "api/views.py"], sensitive=loosened
    )
    assert verdict.value == "STOP_GOVERNING"


def test_urgent_label_stops():
    verdict = _value(["docs/a.md"], labels=["نشر-عاجل"])
    assert verdict.value == "STOP_GENERAL"


def test_unreviewed_security_label_stops():
    verdict = _value(["docs/a.md"], labels=["لم تُراجَع أمنياً"])
    assert verdict.value == "STOP_SECURITY"


def test_service_worker_without_cache_bump_stops_but_with_bump_passes():
    path = "static/js/sw.js"
    assert _value([path], diff=_diff(path, "const x = 1;")).value == "STOP_GENERAL"
    assert (
        _value(
            [path], diff=_diff(path, "const CACHE_NAME = 'schoolos-global-v3';")
        ).value
        == "MERGE_OK"
    )


def test_behind_threshold():
    assert _value(["docs/a.md"], behind=20).value == "MERGE_OK"
    assert _value(["docs/a.md"], behind=21).value == "STOP_GENERAL"


def test_reasons_are_deduplicated_and_rendered():
    verdict = _value(["CLAUDE.md"])
    assert len(verdict.reasons) == len(set(verdict.reasons))
    text = render(verdict)
    assert text.splitlines()[0] == "STOP_GOVERNING"
    assert "CLAUDE.md" in text


def test_glob_double_star_matches_zero_or_more_directories():
    assert matches("a/migrations/0001.py", ["**/migrations/*.py"])
    assert matches("migrations/0001.py", ["**/migrations/*.py"])
    assert matches("breach/x/y.py", ["breach/**"])
    assert not matches("a/migrations/sub/0001.py", ["**/migrations/*.py"])
    assert not matches("docs/migrations.md", ["**/migrations/*.py"])


def test_main_fails_safe_when_gh_is_unavailable(monkeypatch, capsys):
    import merge_stop_classifier as m

    def boom(*_a, **_k):
        raise FileNotFoundError("gh")

    monkeypatch.setattr(m, "fetch_inputs", boom)
    assert main(["1"]) == 1
    out = capsys.readouterr().out
    assert out.splitlines()[0] == "STOP_GENERAL"


def test_release_follow_calls_the_classifier_as_shadow_only():
    """الظل لا يغيّر السلوك: السطر يطبع الحكم ولا يخرج ولا يتفرّع على قيمته."""
    import pathlib

    text = (pathlib.Path(__file__).resolve().parent / "release_follow.sh").read_text(
        encoding="utf-8"
    )
    assert "merge_stop_classifier.py" in text
    line = next(ln for ln in text.splitlines() if ln.startswith('say "[ظلّ]'))
    assert "exit" not in line
    assert text.count("merge_stop_classifier.py") == 1


def test_urls_py_is_not_mistaken_for_an_rls_file():
    """«urls» تحوي «rls» حرفاً: مطابقةُ *rls* حسبت clinic/urls.py صلاحيةً (وقع مع #1204 فصُحّح)."""
    assert not any(
        c == "STOP_PERMISSION" for c, _ in _value(["clinic/urls.py"]).reasons
    )
    assert _value(["db/rls.py"]).value == "STOP_PERMISSION"
    assert _value(["core/policies_rls.py"]).value == "STOP_PERMISSION"


def test_railway_deploy_config_stops_as_security():
    assert _value([".railway/railway.ts"]).value == "STOP_SECURITY"
