import json, re, sys, collections
rows = [r for f in sys.argv[1:] for r in json.load(open(f))]
def kind(r):
    c, a, line = r["case"], r.get("action"), r.get("element_line") or ""
    if "error" in r: return "error"
    if a == "done":
        res = r.get("result") or ""
        scr = r["screen_text"]
        # words in the answer that the screen doesn't show (dates, weekdays, ", USA"...)
        extra = [w for w in re.findall(r"[A-Za-z]{3,}|\d+", res) if w.lower() not in scr.lower() and w.lower() not in
                 {"you", "have", "the", "app", "shows", "and", "your", "are", "events", "event", "today", "contacts", "contact", "saved",
                  "delivery", "address", "is", "no", "not", "any", "there", "with", "google", "calendar", "doordash", "yet"}]
        return "done" + (f" (+{','.join(extra[:4])})" if extra else "")
    if c.startswith("doordash s1"):
        if "1 Hacker Way" in line: return "tap the address"
        if "Account" in line: return "tap Account"
    if c.startswith("contacts") and ("filter" in line.lower()): return "tap filters"
    return f"{a} {line[:30]}"
tab = collections.defaultdict(collections.Counter)
for r in rows: tab[(r["case"], r["variant"])][kind(r)] += 1
cases = list(dict.fromkeys(r["case"] for r in rows)); vs = list(dict.fromkeys(r["variant"] for r in rows))
for c in cases:
    print(f"== {c}")
    for v in vs:
        if tab[(c, v)]: print(f"   {v:12} {dict(tab[(c, v)].most_common())}")
