# مراقبُ الدفعة الرابعة (#704 ثمّ #705 بعد نافذة النشر 14:00 بتوقيت الدوحة). قراءةٌ فقط، لا يدمج ولا يُدخل.
#   python watch_batch4.py --at 14:06                       # لقطةٌ عند الوقت ثمّ يخرج
#   python watch_batch4.py --at 14:04 --until-merged 704,705 --deadline 16:00   # ينتظر الاندماج
import argparse
import datetime
import json
import subprocess
import time

REPO = "sh-school/shschool_mvp"
QUERY = (
    'query{repository(owner:"sh-school",name:"shschool_mvp"){mergeQueue(branch:"main")'
    "{entries(first:20){nodes{position state pullRequest{number}}}}}}"
)


def doha_now():
    return datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=3)


def at_today(hhmm):
    h, m = hhmm.split(":")
    return doha_now().replace(hour=int(h), minute=int(m), second=0, microsecond=0)


def run(cmd):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", timeout=90)
        return r.stdout or ""
    except Exception:
        return ""


def queue():
    try:
        nodes = json.loads(run(["gh", "api", "graphql", "-f", f"query={QUERY}"]))["data"]["repository"]["mergeQueue"]["entries"]["nodes"]
        return {n["pullRequest"]["number"]: f'{n["position"]}:{n["state"]}' for n in nodes}
    except Exception:
        return None


def pr(n):
    try:
        return json.loads(run(["gh", "pr", "view", str(n), "--repo", REPO, "--json", "state,mergeStateStatus,mergedAt"]))
    except Exception:
        return {}


def main_head():
    return run(["gh", "api", f"repos/{REPO}/commits/main", "--jq", '.sha[0:8] + " " + (.commit.message|split("\\n")[0])[0:70]']).strip()


def snapshot(nums):
    q = queue()
    lines = [f"SNAPSHOT {doha_now():%H:%M} Doha  main={main_head()}", f"queue={q}"]
    for n in nums:
        p = pr(n)
        lines.append(f"#{n}: state={p.get('state')} merge={p.get('mergeStateStatus')} mergedAt={p.get('mergedAt')}")
    return "\n".join(lines)


ap = argparse.ArgumentParser()
ap.add_argument("--at", required=True)
ap.add_argument("--until-merged", default="")
ap.add_argument("--deadline", default="")
a = ap.parse_args()

nums = [int(x) for x in (a.until_merged or "704,705").split(",") if x]
start = at_today(a.at)
while doha_now() < start:
    time.sleep(20)

if not a.until_merged:
    print(snapshot(nums), flush=True)
else:
    deadline = at_today(a.deadline) if a.deadline else start + datetime.timedelta(hours=2)
    seen_in_queue = set()
    while True:
        q = queue() or {}
        seen_in_queue |= set(q)
        states = {n: pr(n).get("state") for n in nums}
        if all(s == "MERGED" for s in states.values()):
            print("ALL_MERGED\n" + snapshot(nums), flush=True)
            break
        dropped = [n for n in seen_in_queue if n in nums and n not in q and states.get(n) == "OPEN"]
        if dropped:
            print(f"DROPPED_FROM_QUEUE {dropped}\n" + snapshot(nums), flush=True)
            break
        if doha_now() >= deadline:
            print("DEADLINE\n" + snapshot(nums), flush=True)
            break
        time.sleep(45)
