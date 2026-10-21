import json
from pathlib import Path

base = Path(__file__).resolve().parent.parent / "handover_notes"
here = Path(__file__).resolve().parent
d = {
    "rating": (base / "rating_platform_flow_2026-10-21.md").read_text(encoding="utf-8"),
    "plan": (base / "plan_recommendations_2026-10-21.md").read_text(encoding="utf-8"),
    "platform": (base / "swot_platform_2026-10-21.md").read_text(encoding="utf-8"),
    "flow": (base / "swot_flow_2026-10-21.md").read_text(encoding="utf-8"),
}
data = (
    json.dumps(d, ensure_ascii=False)
    .replace("</", "<\\/")
    .replace("\u2028", "\\u2028")
    .replace("\u2029", "\\u2029")
)
t = (here / "template.html").read_text(encoding="utf-8").replace("/*__DATA__*/", data)
(here / "swot_report.html").write_text(t, encoding="utf-8")
print(len(t.encode("utf-8")))
