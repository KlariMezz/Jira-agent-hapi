from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import requests
from requests.auth import HTTPBasicAuth
from datetime import datetime
import os

app = Flask(__name__, static_folder='static')
CORS(app)

JIRA_URL = "https://dius-team.atlassian.net"
JIRA_EMAIL = "klara.mezzeyova@dius.ai"
JIRA_TOKEN = "ATATT3xFfGF0aVtQFNu6XTJf-92atZc_TXD3fHD5G6objA1Ud_Gko57eEP46wy4kkfUqfd-8gsen2fQDvIJqcVBQfFuKMc4AQdhOrjxhx3Lci_1HbqOGI9emijg_44ziHY_drtBfsO_xjXc3sH09set_i5RIvpq85OVv5DuazS9UktQm739Jzj4=C25E45FF"
PROJECT_KEY = "HAPI"

auth = HTTPBasicAuth(JIRA_EMAIL, JIRA_TOKEN)
HEADERS = {"Accept": "application/json", "Content-Type": "application/json"}

USERS = {
    "klara": ("712020:966280a2-82c9-40e9-b8ee-e03532a35e93", "Klara"),
    "emma": ("712020:ba7ea612-9b67-4e16-891c-646240208317", "Emma"),
    "diana": ("712020:5f898611-d58b-4568-90db-1fc4b7895bb3", "Diana")
}

@app.route("/")
def index():
    return send_from_directory("static", "index.html")

@app.route("/create", methods=["POST"])
def create_ticket():
    data = request.json
    summary = data.get("summary", "")
    description = data.get("description", summary)
    priority = data.get("priority", "Medium")
    issue_type = data.get("issueType", "\u00daloha")
    assignee_key = data.get("assignee", "")
    due_date = data.get("dueDate", "")

    if not summary:
        return jsonify({"error": "Summary je povinné"}), 400

    fields = {
        "project": {"key": PROJECT_KEY},
        "summary": summary[:80],
        "description": description,
        "issuetype": {"name": issue_type},
        "priority": {"name": priority}
    }

    if assignee_key and assignee_key in USERS:
        fields["assignee"] = {"accountId": USERS[assignee_key][0]}

    if due_date:
        try:
            fields["duedate"] = datetime.strptime(due_date, "%Y-%m-%d").strftime("%Y-%m-%d")
        except:
            pass

    r = requests.post(
        f"{JIRA_URL}/rest/api/2/issue",
        auth=auth, headers=HEADERS,
        json={"fields": fields}
    )
    d = r.json()

    if r.ok:
        return jsonify({
            "key": d["key"],
            "url": f"{JIRA_URL}/browse/{d['key']}"
        })
    else:
        return jsonify({"error": str(d)}), 400

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
