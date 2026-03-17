import requests
import json
import re
from requests.auth import HTTPBasicAuth
from datetime import datetime, date, timedelta

JIRA_URL = "https://dius-team.atlassian.net"
JIRA_EMAIL = "emma.jancekova@dius.ai"
JIRA_TOKEN = "ATATT3xFfGF0EHVn4ubEoCkbKclD5Dd9Rque3pGR8rAzkT2ogodeoKi1n1A_FKEfQ5O74SDiDJ1G6znmcGDrcSAH_l-0w1exaNgOGqsoQO5FFJVe33KZ6NaEtO4-lHG-jb-1DUYBFPUqpszn0_5qPo7vPBLo3uy81fC-KX4qKhx4STTUFFcXKfc=ADE75C90"
PROJECT_KEY = "HAPI"

auth = HTTPBasicAuth(JIRA_EMAIL, JIRA_TOKEN)
H = {"Accept": "application/json", "Content-Type": "application/json"}

USERS = {
    "klara": {"id": "712020:966280a2-82c9-40e9-b8ee-e03532a35e93", "name": "Klara"},
    "emma":  {"id": "712020:ba7ea612-9b67-4e16-891c-646240208317", "name": "Emma"},
    "diana": {"id": "712020:5f898611-d58b-4568-90db-1fc4b7895bb3", "name": "Diana"},
}
ISSUE_TYPES = {"uloha": "10373", "pouloha": "10374"}
context = {"last_key": None}

# ─── Jira funkcie ─────────────────────────────────────────────────────────────

def search(jql):
    r = requests.post(
        f"{JIRA_URL}/rest/api/3/search/jql", auth=auth, headers=H,
        json={"jql": jql, "maxResults": 20, "fields": ["summary","status","assignee","priority","duedate"]}
    )
    return r.json().get("issues", []) if r.ok else []

def format_issues(issues):
    if not issues:
        return "Nenasli sa ziadne tasky."
    lines = []
    for i in issues:
        f = i["fields"]
        a = (f.get("assignee") or {}).get("displayName", "Nikto")
        s = f.get("status", {}).get("name", "?")
        p = f.get("priority", {}).get("name", "?")
        due = f.get("duedate") or ""
        due_str = f"  [{due}]" if due else ""
        lines.append(f"  {i['key']}  [{p}]  {f['summary'][:55]}  → {a}  ({s}){due_str}")
    return "\n".join(lines)

def get_detail(key):
    r = requests.get(f"{JIRA_URL}/rest/api/3/issue/{key}", auth=auth, headers=H,
        params={"fields": "summary,status,assignee,priority,duedate,comment"})
    if not r.ok: return None
    f = r.json()["fields"]
    a = (f.get("assignee") or {}).get("displayName", "Nikto")
    comments = f.get("comment", {}).get("comments", [])
    last_comments = []
    for c in comments[-3:]:
        author = c.get("author", {}).get("displayName", "?")
        body = c.get("body", {})
        if isinstance(body, dict):
            text = " ".join(n.get("text","") for block in body.get("content",[]) for n in block.get("content",[]) if n.get("type")=="text")
        else:
            text = str(body)
        last_comments.append(f"    [{author}]: {text[:100]}")
    context["last_key"] = key
    return {"key": key, "summary": f.get("summary",""), "status": f.get("status",{}).get("name","?"),
            "assignee": a, "priority": f.get("priority",{}).get("name","?"),
            "due": f.get("duedate") or "", "comments": last_comments}

def create_issue(summary, priority="Medium", assignee_key=None, due_date=None, type_key="uloha"):
    fields = {
        "project": {"key": PROJECT_KEY}, "summary": summary[:80],
        "issuetype": {"id": ISSUE_TYPES.get(type_key, "10373")},
        "priority": {"name": priority}
    }
    if assignee_key and assignee_key in USERS:
        fields["assignee"] = {"accountId": USERS[assignee_key]["id"]}
    if due_date: fields["duedate"] = due_date
    r = requests.post(f"{JIRA_URL}/rest/api/3/issue", auth=auth, headers=H, json={"fields": fields})
    d = r.json()
    if r.ok: context["last_key"] = d["key"]
    return d.get("key") if r.ok else None

def edit_issue(key, fields_to_update):
    r = requests.put(f"{JIRA_URL}/rest/api/3/issue/{key}", auth=auth, headers=H, json={"fields": fields_to_update})
    return r.ok

def add_comment(key, text):
    body = {"body": {"type": "doc", "version": 1, "content": [{"type": "paragraph", "content": [{"type": "text", "text": text}]}]}}
    r = requests.post(f"{JIRA_URL}/rest/api/3/issue/{key}/comment", auth=auth, headers=H, json=body)
    return r.ok

def get_transitions(key):
    r = requests.get(f"{JIRA_URL}/rest/api/3/issue/{key}/transitions", auth=auth, headers=H)
    return r.json().get("transitions", []) if r.ok else []

def transition_issue(key, tid):
    r = requests.post(f"{JIRA_URL}/rest/api/3/issue/{key}/transitions", auth=auth, headers=H, json={"transition": {"id": tid}})
    return r.ok

# ─── Pomocné funkcie ──────────────────────────────────────────────────────────

def parse_date(text):
    t = text.lower()
    today = date.today()
    day_map = {"pondelok": 0, "monday": 0, "utorok": 1, "tuesday": 1,
               "streda": 2, "wednesday": 2, "stvrtok": 3, "thursday": 3,
               "piatok": 4, "friday": 4}
    for word, weekday in day_map.items():
        if word in t:
            days = (weekday - today.weekday()) % 7 or 7
            return (today + timedelta(days=days)).strftime("%Y-%m-%d")
    if "zajtra" in t or "tomorrow" in t:
        return (today + timedelta(days=1)).strftime("%Y-%m-%d")
    m = re.search(r'(\d{1,2})[.\-/](\d{1,2})(?:[.\-/](\d{2,4}))?', text)
    if m:
        day, month = int(m.group(1)), int(m.group(2))
        year = int(m.group(3)) if m.group(3) else today.year
        if year < 100: year += 2000
        try: return date(year, month, day).strftime("%Y-%m-%d")
        except: pass
    return None

def find_key(text):
    m = re.search(r'HAPI[-\s]?(\d+)', text, re.IGNORECASE)
    if m: return f"HAPI-{m.group(1)}"
    if context["last_key"] and any(w in text.lower() for w in ["ho", "ten", "this", "it", "tuto", "tento", "posledny", "neho"]):
        return context["last_key"]
    return None

def find_assignee(text):
    t = text.lower()
    for name in USERS:
        if name in t: return name
    if any(w in t for w in ["mna", "mne", "moje", "mine", "mi", "ja", "seba"]): return "klara"
    return None

def find_priority(text):
    t = text.lower()
    if any(w in t for w in ["high", "vysoka", "urgent", "dolezite"]): return "High"
    if any(w in t for w in ["low", "nizka", "malo", "nizku"]): return "Low"
    if any(w in t for w in ["medium", "stredna", "normal", "strednu"]): return "Medium"
    return None

def extract_new_value(text, keywords):
    """Extrahuje novu hodnotu po klucovom slove. Napr. 'zmen nazov na Novy nazov' -> 'Novy nazov'"""
    t = text.lower()
    for kw in keywords:
        if kw in t:
            idx = t.find(kw) + len(kw)
            value = text[idx:].strip().lstrip(":").strip()
            # Odstran uvodzovky ak su
            value = value.strip('"\'')
            if value: return value
    return None

# ─── Interaktívne vytvorenie tasku ────────────────────────────────────────────

def interactive_create(summary):
    print(f"\n  Vytváram task: \"{summary}\"")
    print("\n  Priorita:")
    print("    1 = High  |  2 = Medium  |  3 = Low")
    pc = input("  Vyber [1/2/3] (Enter = Medium): ").strip()
    priority = {"1": "High", "3": "Low"}.get(pc, "Medium")

    print("\n  Asignee:")
    print("    1 = Klara  |  2 = Emma  |  3 = Diana  |  4 = Nikto")
    ac = input("  Vyber [1/2/3/4] (Enter = Nikto): ").strip()
    assignee_key = {"1": "klara", "2": "emma", "3": "diana"}.get(ac)

    print("\n  Deadline (napr. 25.3.2026, piatok, zajtra)")
    due_input = input("  Zadaj datum (Enter = preskocit): ").strip()
    due_date = parse_date(due_input) if due_input else None

    print("\n  Typ:  1 = Uloha  |  2 = Pouloha")
    tc = input("  Vyber [1/2] (Enter = Uloha): ").strip()
    type_key = "pouloha" if tc == "2" else "uloha"

    assignee_name = USERS.get(assignee_key, {}).get("name", "Nikto") if assignee_key else "Nikto"
    print(f"\n  Nahlad:")
    print(f"    Summary:  {summary}")
    print(f"    Priorita: {priority}  |  Asignee: {assignee_name}  |  Deadline: {due_date or 'nenastaveny'}")
    confirm = input("\n  Vytvorit? [Y/n]: ").strip().lower()
    if confirm in ("n", "nie", "no"): return "Zrusene."

    key = create_issue(summary, priority, assignee_key, due_date, type_key)
    if key:
        return (f"Vytvoreny: {key}  →  {JIRA_URL}/browse/{key}\n"
                f"  Priorita: {priority}  |  Asignee: {assignee_name}  |  Deadline: {due_date or 'nenastaveny'}")
    return "Chyba pri vytvarani tasku."

# ─── Hlavný parser ─────────────────────────────────────────────────────────────

def parse_and_handle(text):
    t = text.lower()
    key = find_key(text)

    # ── ZOZNAM ──
    if any(w in t for w in ["ukaz", "zobraz", "zoznam", "vsetky", "show", "list", "moje tasky", "co mam", "ake tasky", "ktore tasky"]):
        f = "all"
        if any(w in t for w in ["moje", "mine", "mna", "co mam", "priradene mne", "priradeny mne"]): f = "klara"
        else:
            for name in USERS:
                if name in t: f = name; break
        if any(w in t for w in ["hotov", "done", "dokoncen", "completed"]): f = "done"
        elif any(w in t for w in ["in progress", "v rieseni", "nedokoncen", "rozpracovan", "riesene"]): f = "in_progress"
        elif any(w in t for w in ["todo", "to do", "nezacate", "nove", "cakajuce"]): f = "todo"
        jql_map = {
            "klara": f'project={PROJECT_KEY} AND assignee="{USERS["klara"]["id"]}" ORDER BY created DESC',
            "emma":  f'project={PROJECT_KEY} AND assignee="{USERS["emma"]["id"]}" ORDER BY created DESC',
            "diana": f'project={PROJECT_KEY} AND assignee="{USERS["diana"]["id"]}" ORDER BY created DESC',
            "done":  f'project={PROJECT_KEY} AND status=Done ORDER BY updated DESC',
            "in_progress": f'project={PROJECT_KEY} AND status="In Progress" ORDER BY updated DESC',
            "todo":  f'project={PROJECT_KEY} AND status="To Do" ORDER BY created DESC',
            "all":   f'project={PROJECT_KEY} ORDER BY created DESC',
        }
        return format_issues(search(jql_map.get(f, jql_map["all"])))

    # ── VYTVORENIE ──
    if any(w in t for w in ["vytvor", "pridaj task", "novy task", "create", "pridaj ulohu", "nova uloha", "zaloz task"]):
        summary = text
        for prefix in ["vytvor task", "vytvor ulohu", "pridaj task", "pridaj ulohu", "zaloz task", "vytvor", "pridaj", "create task", "create"]:
            if prefix in t:
                idx = t.find(prefix) + len(prefix)
                summary = text[idx:].strip().lstrip(":").strip()
                break
        # Odstran frazy ako "tak s nazvom", "s nazvom"
        import unicodedata
        def strip_ac(s):
            return ''.join(c for c in unicodedata.normalize('NFD', s) if unicodedata.category(c) != 'Mn')
        sp = strip_ac(summary.lower())
        for noise in ["tak s nazvom", "s nazvom", "s tymto nazvom", "s nazvom tasku", "nazvom", "s popisom"]:
            if noise in sp:
                idx = sp.find(noise) + len(noise)
                summary = summary[idx:].strip().lstrip(":").strip()
                sp = strip_ac(summary.lower())
                break
        if not summary: return "Aky task chces vytvorit? Napr. 'vytvor task opravit login'"
        return interactive_create(summary)

    # ── KOMENTAR ──
    if any(w in t for w in ["komentar", "comment", "pridaj poznamku", "napisat poznamku"]):
        target_key = key or context["last_key"]
        comment_text = text
        for prefix in ["pridaj komentar k " + (target_key or ""), "komentar k " + (target_key or ""),
                        "komentar:", "comment:", "pridaj komentar", "pridaj poznamku"]:
            if prefix.lower() in t:
                idx = t.find(prefix.lower()) + len(prefix)
                comment_text = text[idx:].strip().lstrip(":").strip()
                break
        if not target_key: return "Ku ktoremu tasku? Napr. 'pridaj komentar k HAPI-5: text'"
        if not comment_text or comment_text.lower() == text.lower():
            comment_text = input("  Zadaj text komentara: ").strip()
        ok = add_comment(target_key, comment_text)
        return f"Komentar pridany k {target_key}." if ok else "Chyba pri pridavani komentara."

    # ── ZMENA STATUSU ──
    if any(w in t for w in ["oznac", "presun", "zmen status", "nastav status"]) or \
       (any(w in t for w in ["hotov", "done", "dokoncen"]) and key) or \
       any(w in t for w in ["in progress", "v rieseni", "rozpracuj"]):
        target_key = key or context["last_key"]
        if not target_key: return "Ktory task? Napr. 'oznac HAPI-5 ako hotove'"
        status = "done"
        if any(w in t for w in ["in progress", "v rieseni", "riesim", "rozpracuj", "zacni"]): status = "in_progress"
        elif any(w in t for w in ["otvoren", "reopen", "to do", "znova", "vrat"]): status = "todo"
        transitions = get_transitions(target_key)
        keywords = {"done": ["done","hotovo","dokoncene","closed","resolved"],
                    "in_progress": ["in progress","v rieseni"], "todo": ["to do","open","backlog"]}
        names = keywords.get(status, [status])
        matched = next((tr for tr in transitions if tr["name"].lower() in names), None)
        if not matched and transitions: matched = transitions[0]
        if matched:
            ok = transition_issue(target_key, matched["id"])
            return f"{target_key} → {matched['name']}" if ok else "Chyba pri zmene statusu."
        return f"Dostupne prechody: {[tr['name'] for tr in transitions]}"

    # ── EDITÁCIA ──
    edit_keywords = ["zmen", "uprav", "edit", "nastav", "aktualizuj", "zmenaj", "prepis", "oprav nazov",
                     "zmen nazov", "zmen znenie", "zmen popis", "zmen prioritu", "zmen asignee",
                     "zmen deadline", "priraden", "nastav deadline", "predl deadline"]
    if any(w in t for w in edit_keywords):
        target_key = key or context["last_key"]
        if not target_key: return "Ktory task? Napr. 'zmen HAPI-5 prioritu na High'"
        fields_to_update = {}

        # Zmena summary/znenia/nazvu
        new_summary = extract_new_value(text, ["zmen znenie na", "zmen nazov na", "zmen popis na",
                                                "prepis na", "oprav nazov na", "nastav nazov na",
                                                "zmen summary na", "rename na"])
        if new_summary:
            fields_to_update["summary"] = new_summary

        # Zmena priority
        new_priority = find_priority(text)
        if new_priority and any(w in t for w in ["priorit", "high", "low", "medium", "urgent"]):
            fields_to_update["priority"] = {"name": new_priority}

        # Zmena asignee
        new_assignee = find_assignee(text)
        if new_assignee and any(w in t for w in ["asignee", "priraden", "assign", "priradi", "prirad"]):
            fields_to_update["assignee"] = {"accountId": USERS[new_assignee]["id"]}

        # Zmena deadline
        new_date = parse_date(text)
        if new_date and any(w in t for w in ["deadline", "datum", "do", "termín", "termin"]):
            fields_to_update["duedate"] = new_date

        if not fields_to_update:
            # Skus aspon zmenu priority alebo asignee bez explicitneho slova
            p = find_priority(text)
            if p: fields_to_update["priority"] = {"name": p}
            a = find_assignee(text)
            if a: fields_to_update["assignee"] = {"accountId": USERS[a]["id"]}
            d = parse_date(text)
            if d: fields_to_update["duedate"] = d

        if not fields_to_update:
            return f"Nerozumel som co chces zmenit na {target_key}. Skus napr:\n  'zmen znenie na Novy nazov tasku'\n  'zmen prioritu na High'\n  'zmen asignee na Emma'"

        ok = edit_issue(target_key, fields_to_update)
        if ok:
            changes = []
            if "summary" in fields_to_update: changes.append(f"znenie → \"{fields_to_update['summary']}\"")
            if "priority" in fields_to_update: changes.append(f"priorita → {fields_to_update['priority']['name']}")
            if "assignee" in fields_to_update:
                for name, u in USERS.items():
                    if u["id"] == fields_to_update["assignee"]["accountId"]:
                        changes.append(f"asignee → {u['name']}"); break
            if "duedate" in fields_to_update: changes.append(f"deadline → {fields_to_update['duedate']}")
            return f"{target_key} upraveny: {', '.join(changes)}"
        return f"Chyba pri uprave {target_key}."

    # ── DETAIL ──
    if key:
        d = get_detail(key)
        if not d: return f"Task {key} sa nenasiel."
        lines = [f"\n  {d['key']}: {d['summary']}", f"  Status:   {d['status']}",
                 f"  Priorita: {d['priority']}", f"  Asignee:  {d['assignee']}",
                 f"  Deadline: {d['due'] or 'nenastaveny'}"]
        if d["comments"]: lines.append("  Komentare:"); lines.extend(d["comments"])
        return "\n".join(lines)

    return ("Nerozumel som. Skus napriklad:\n"
            "  'ukaz moje tasky'\n"
            "  'vytvor task opravit login'\n"
            "  'co je HAPI-5'\n"
            "  'zmen znenie HAPI-12 na Novy nazov tasku'\n"
            "  'zmen prioritu HAPI-5 na High'\n"
            "  'zmen asignee HAPI-5 na Emma'\n"
            "  'oznac HAPI-5 ako hotove'\n"
            "  'pridaj komentar k HAPI-5: text'")

# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    print("\n=== Jira Agent HAPI ===")
    print("Rozpravaj sa prirodzene. Napriklad:")
    print("  ukaz moje tasky")
    print("  vytvor task opravit login")
    print("  co je HAPI-5")
    print("  zmen znenie HAPI-12 na Novy nazov tasku")
    print("  zmen prioritu HAPI-5 na High")
    print("  zmen asignee HAPI-5 na Emma")
    print("  oznac HAPI-5 ako hotove")
    print("  pridaj komentar k HAPI-5: toto je hotove")
    print("  q = koniec\n")

    while True:
        try:
            user_input = input("Ty: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nDovidenia!"); break
        if not user_input: continue
        if user_input.lower() in ("q", "quit", "koniec", "exit"):
            print("Dovidenia!"); break
        response = parse_and_handle(user_input)
        print(f"\nAgent:\n{response}\n")

if __name__ == "__main__":
    main()
