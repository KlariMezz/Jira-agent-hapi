#!/bin/bash

# Pouzitie: bash install_jira_agent.sh vas@email.com VAS_API_TOKEN

EMAIL="$1"
TOKEN="$2"

echo ""
echo "╔══════════════════════════════════════╗"
echo "║      Jira Agent HAPI — Instalacia    ║"
echo "╚══════════════════════════════════════╝"
echo ""

if [ -z "$EMAIL" ] || [ -z "$TOKEN" ]; then
    echo "Chyba: Zadaj email a token ako parametre."
    echo "Pouzitie: bash install_jira_agent.sh vas@email.com VAS_TOKEN"
    exit 1
fi

echo "Overujem ucet..."
RESPONSE=$(curl -s -u "$EMAIL:$TOKEN" "https://dius-team.atlassian.net/rest/api/3/myself")
ACCOUNT_ID=$(echo "$RESPONSE" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('accountId',''))" 2>/dev/null)
DISPLAY_NAME=$(echo "$RESPONSE" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('displayName',''))" 2>/dev/null)

if [ -z "$ACCOUNT_ID" ]; then
    echo "Chyba: Neplatny email alebo token."
    exit 1
fi

echo "Prihlaseny ako: $DISPLAY_NAME"
echo ""

AGENT_DIR="$HOME/JiraAgent"
mkdir -p "$AGENT_DIR"

python3 << PYEOF
import os

email = "$EMAIL"
token = "$TOKEN"
account_id = "$ACCOUNT_ID"
display_name = "$DISPLAY_NAME"
agent_dir = os.path.expanduser("$AGENT_DIR")

code = '''import requests
import json
import re
import unicodedata
from requests.auth import HTTPBasicAuth
from datetime import datetime, date, timedelta

JIRA_URL = "https://dius-team.atlassian.net"
JIRA_EMAIL = "''' + email + '''"
JIRA_TOKEN = "''' + token + '''"
MY_ACCOUNT_ID = "''' + account_id + '''"
MY_NAME = "''' + display_name + '''"
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

def search(jql):
    r = requests.post(f"{JIRA_URL}/rest/api/3/search/jql", auth=auth, headers=H,
        json={"jql": jql, "maxResults": 20, "fields": ["summary","status","assignee","priority","duedate"]})
    return r.json().get("issues", []) if r.ok else []

def format_issues(issues):
    if not issues: return "Nenasli sa ziadne tasky."
    lines = []
    for i in issues:
        f = i["fields"]
        a = (f.get("assignee") or {}).get("displayName", "Nikto")
        s = f.get("status", {}).get("name", "?")
        p = f.get("priority", {}).get("name", "?")
        due = f.get("duedate") or ""
        due_str = f"  [{due}]" if due else ""
        lines.append(f"  {i[\'key\']}  [{p}]  {f[\'summary\'][:55]}  -> {a}  ({s}){due_str}")
    return "\\n".join(lines)

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
    fields = {"project": {"key": PROJECT_KEY}, "summary": summary[:80],
              "issuetype": {"id": ISSUE_TYPES.get(type_key, "10373")}, "priority": {"name": priority}}
    if assignee_key == "me": fields["assignee"] = {"accountId": MY_ACCOUNT_ID}
    elif assignee_key in USERS: fields["assignee"] = {"accountId": USERS[assignee_key]["id"]}
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

def strip_ac(s):
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")

def parse_date(text):
    t = text.lower()
    today = date.today()
    day_map = {"pondelok": 0, "monday": 0, "utorok": 1, "tuesday": 1, "streda": 2, "wednesday": 2, "stvrtok": 3, "thursday": 3, "piatok": 4, "friday": 4}
    for word, weekday in day_map.items():
        if word in t:
            days = (weekday - today.weekday()) % 7 or 7
            return (today + timedelta(days=days)).strftime("%Y-%m-%d")
    if "zajtra" in t or "tomorrow" in t: return (today + timedelta(days=1)).strftime("%Y-%m-%d")
    m = re.search(r"(\\d{1,2})[.\\-/](\\d{1,2})(?:[.\\-/](\\d{2,4}))?", text)
    if m:
        day, month = int(m.group(1)), int(m.group(2))
        year = int(m.group(3)) if m.group(3) else today.year
        if year < 100: year += 2000
        try: return date(year, month, day).strftime("%Y-%m-%d")
        except: pass
    return None

def find_key(text):
    m = re.search(r"HAPI[-\\s]?(\\d+)", text, re.IGNORECASE)
    if m: return f"HAPI-{m.group(1)}"
    if context["last_key"] and any(w in text.lower() for w in ["ho", "ten", "this", "it", "tuto", "tento", "posledny"]):
        return context["last_key"]
    return None

def find_assignee(text):
    t = text.lower()
    for name in USERS:
        if name in t: return name
    if any(w in t for w in ["mna", "mne", "moje", "mine", "mi", "ja", "seba"]): return "me"
    return None

def find_priority(text):
    t = text.lower()
    if any(w in t for w in ["high", "vysoka", "urgent", "dolezite"]): return "High"
    if any(w in t for w in ["low", "nizka", "malo"]): return "Low"
    if any(w in t for w in ["medium", "stredna", "normal"]): return "Medium"
    return None

def extract_new_value(text, keywords):
    t = text.lower()
    for kw in keywords:
        if kw in t:
            idx = t.find(kw) + len(kw)
            return text[idx:].strip().lstrip(":").strip().strip()\\'\\'"
    return None

def interactive_create(summary):
    print(f"\\n  Vytváram task: \\"{summary}\\"")
    print("\\n  Priorita:  1 = High  |  2 = Medium  |  3 = Low")
    pc = input("  Vyber [1/2/3] (Enter = Medium): ").strip()
    priority = {"1": "High", "3": "Low"}.get(pc, "Medium")
    print(f"\\n  Asignee:  1 = Klara  |  2 = Emma  |  3 = Diana  |  4 = Ja ({MY_NAME})  |  5 = Nikto")
    ac = input("  Vyber [1/2/3/4/5] (Enter = Nikto): ").strip()
    assignee_key = {"1": "klara", "2": "emma", "3": "diana", "4": "me"}.get(ac)
    print("\\n  Deadline (napr. 25.3.2026, piatok, zajtra)")
    due_input = input("  Zadaj datum (Enter = preskocit): ").strip()
    due_date = parse_date(due_input) if due_input else None
    print("\\n  Typ:  1 = Uloha  |  2 = Pouloha")
    tc = input("  Vyber [1/2] (Enter = Uloha): ").strip()
    type_key = "pouloha" if tc == "2" else "uloha"
    assignee_name = MY_NAME if assignee_key == "me" else (USERS.get(assignee_key, {}).get("name", "Nikto") if assignee_key else "Nikto")
    print(f"\\n  Nahlad: {summary}  |  {priority}  |  {assignee_name}  |  {due_date or 'bez deadline'}")
    if input("  Vytvorit? [Y/n]: ").strip().lower() in ("n","nie","no"): return "Zrusene."
    key = create_issue(summary, priority, assignee_key, due_date, type_key)
    return f"Vytvoreny: {key}  ->  {JIRA_URL}/browse/{key}" if key else "Chyba pri vytvarani."

def parse_and_handle(text):
    t = text.lower()
    key = find_key(text)

    if any(w in t for w in ["ukaz","zobraz","zoznam","vsetky","show","list","moje tasky","co mam","ake tasky"]):
        f = "all"
        if any(w in t for w in ["moje","mine","mna","co mam"]): f = "me"
        else:
            for name in ["klara","emma","diana"]:
                if name in t: f = name; break
        if any(w in t for w in ["hotov","done","dokoncen"]): f = "done"
        elif any(w in t for w in ["in progress","v rieseni","nedokoncen"]): f = "in_progress"
        elif any(w in t for w in ["todo","to do","nezacate"]): f = "todo"
        jql_map = {
            "me":    f\'project={PROJECT_KEY} AND assignee="{MY_ACCOUNT_ID}" ORDER BY created DESC\',
            "klara": \'project=HAPI AND assignee="712020:966280a2-82c9-40e9-b8ee-e03532a35e93" ORDER BY created DESC\',
            "emma":  \'project=HAPI AND assignee="712020:ba7ea612-9b67-4e16-891c-646240208317" ORDER BY created DESC\',
            "diana": \'project=HAPI AND assignee="712020:5f898611-d58b-4568-90db-1fc4b7895bb3" ORDER BY created DESC\',
            "done":  "project=HAPI AND status=Done ORDER BY updated DESC",
            "in_progress": "project=HAPI AND status=\\"In Progress\\" ORDER BY updated DESC",
            "todo":  "project=HAPI AND status=\\"To Do\\" ORDER BY created DESC",
            "all":   "project=HAPI ORDER BY created DESC",
        }
        return format_issues(search(jql_map.get(f, jql_map["all"])))

    if any(w in t for w in ["vytvor","pridaj task","novy task","create","zaloz task"]):
        summary = text
        for prefix in ["vytvor task","vytvor ulohu","pridaj task","zaloz task","vytvor","pridaj","create"]:
            if prefix in t:
                idx = t.find(prefix) + len(prefix)
                summary = text[idx:].strip().lstrip(":").strip()
                break
        sp = strip_ac(summary.lower())
        for noise in ["tak s nazvom","s nazvom","nazvom","s popisom"]:
            if noise in sp:
                idx = sp.find(noise) + len(noise)
                summary = summary[idx:].strip().lstrip(":").strip()
                break
        return interactive_create(summary) if summary else "Aky task chces vytvorit?"

    if any(w in t for w in ["komentar","comment","pridaj poznamku"]):
        target_key = key or context["last_key"]
        if not target_key: return "Ku ktoremu tasku?"
        comment_text = text
        for prefix in ["pridaj komentar","komentar:","comment:"]:
            if prefix in t:
                idx = t.find(prefix) + len(prefix)
                comment_text = text[idx:].strip().lstrip(":").strip()
                break
        ok = add_comment(target_key, comment_text)
        return f"Komentar pridany k {target_key}." if ok else "Chyba."

    if any(w in t for w in ["oznac","hotov","done","dokoncen","in progress","v rieseni"]) and (key or context["last_key"]):
        target_key = key or context["last_key"]
        status = "done"
        if any(w in t for w in ["in progress","v rieseni","rozpracuj"]): status = "in_progress"
        elif any(w in t for w in ["otvoren","reopen","to do"]): status = "todo"
        transitions = get_transitions(target_key)
        keywords = {"done": ["done","hotovo","dokoncene","closed","resolved"], "in_progress": ["in progress","v rieseni"], "todo": ["to do","open"]}
        matched = next((tr for tr in transitions if tr["name"].lower() in keywords.get(status,[])), None)
        if not matched and transitions: matched = transitions[0]
        if matched:
            ok = transition_issue(target_key, matched["id"])
            return f"{target_key} -> {matched[\'name\']}" if ok else "Chyba."
        return f"Dostupne: {[tr[\'name\'] for tr in transitions]}"

    if any(w in t for w in ["zmen","uprav","edit","nastav","aktualizuj","prepis"]):
        target_key = key or context["last_key"]
        if not target_key: return "Ktory task?"
        fields_to_update = {}
        new_summary = extract_new_value(text, ["zmen znenie na","zmen nazov na","prepis na","nastav nazov na"])
        if new_summary: fields_to_update["summary"] = new_summary
        p = find_priority(text)
        if p and any(w in t for w in ["priorit","high","low","medium"]): fields_to_update["priority"] = {"name": p}
        a = find_assignee(text)
        if a and any(w in t for w in ["asignee","priraden","assign","prirad"]):
            fields_to_update["assignee"] = {"accountId": MY_ACCOUNT_ID if a == "me" else USERS[a]["id"]}
        d = parse_date(text)
        if d and any(w in t for w in ["deadline","datum","termin"]): fields_to_update["duedate"] = d
        if not fields_to_update:
            if p: fields_to_update["priority"] = {"name": p}
            if a: fields_to_update["assignee"] = {"accountId": MY_ACCOUNT_ID if a == "me" else USERS[a]["id"]}
            if d: fields_to_update["duedate"] = d
        if not fields_to_update: return "Co chces zmenit? Napr: zmen znenie HAPI-5 na Novy nazov"
        ok = edit_issue(target_key, fields_to_update)
        return f"{target_key} upraveny." if ok else "Chyba pri uprave."

    if key:
        d = get_detail(key)
        if not d: return f"Task {key} sa nenasiel."
        lines = [f"\\n  {d[\'key\']}: {d[\'summary\']}", f"  Status:   {d[\'status\']}",
                 f"  Priorita: {d[\'priority\']}", f"  Asignee:  {d[\'assignee\']}",
                 f"  Deadline: {d[\'due\'] or \'nenastaveny\'}"]
        if d["comments"]: lines.append("  Komentare:"); lines.extend(d["comments"])
        return "\\n".join(lines)

    return "Nerozumel som. Skus: ukaz moje tasky | vytvor task | co je HAPI-5 | oznac HAPI-5 ako hotove"

def main():
    print(f"\\n=== Jira Agent HAPI ===  (prihlaseny: {MY_NAME})")
    print("Rozpravaj sa prirodzene.  q = koniec\\n")
    while True:
        try: user_input = input("Ty: ").strip()
        except (EOFError, KeyboardInterrupt): print("\\nDovidenia!"); break
        if not user_input: continue
        if user_input.lower() in ("q","quit","koniec","exit"): print("Dovidenia!"); break
        print(f"\\nAgent:\\n{parse_and_handle(user_input)}\\n")

if __name__ == "__main__":
    main()
'''

with open(os.path.join(agent_dir, "jira_agent.py"), "w") as f:
    f.write(code)
print("Agent ulozeny.")
PYEOF

pip3 install requests -q 2>/dev/null

ALIAS_LINE="alias jira='python3 $AGENT_DIR/jira_agent.py'"
if ! grep -q "alias jira=" ~/.zshrc 2>/dev/null; then
    echo "$ALIAS_LINE" >> ~/.zshrc
fi
source ~/.zshrc 2>/dev/null

echo "Hotovo! Prihlaseny ako: $DISPLAY_NAME"
echo "Spusti agenta: jira"
