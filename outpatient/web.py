"""Browser interface for reviewing the queue and checking handbook procedures."""

from html import escape
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from urllib.error import URLError
from urllib.parse import parse_qs, urlsplit

from outpatient.data import connect


STYLE = """
:root{color-scheme:light;--ink:#18352f;--paper:#f3f6f2;--line:#cddbd1;--accent:#245843}
*{box-sizing:border-box}body{margin:0;background:var(--paper);color:var(--ink);font:16px/1.55 system-ui,sans-serif}
main{max-width:1080px;margin:auto;padding:3rem 1.25rem}header{padding:0 0 1.5rem;border-bottom:1px solid var(--line)}
h1,h2{line-height:1.15;margin:0 0 .5rem}h1{font-size:clamp(2rem,6vw,3.35rem);letter-spacing:-.055em}
p{margin:.5rem 0 .9rem}.grid{display:grid;grid-template-columns:1.3fr 1fr;gap:1rem;margin-top:1rem}
section{min-width:0;background:#fff;border:1px solid var(--line);border-radius:.7rem;padding:1.25rem}
table{border-collapse:collapse;width:100%;font-variant-numeric:tabular-nums;font-size:.85rem}
th,td{padding:.45rem;text-align:left;border-bottom:1px solid var(--line);white-space:nowrap}
th:last-child,td:last-child{text-align:right}.scroll{overflow-x:auto}
label{display:block;font-weight:600}textarea{font:inherit;display:block;width:100%;margin:.4rem 0 .75rem;padding:.65rem;border:1px solid #71877a;border-radius:.4rem;min-height:5rem}
button{font:inherit;font-weight:600;cursor:pointer;color:#fff;background:var(--accent);border:0;border-radius:.4rem;padding:.55rem .9rem}
.answer{margin-top:1rem;padding:.8rem;border-left:3px solid var(--accent);background:var(--paper)}
@media(max-width:780px){.grid{grid-template-columns:1fr}main{padding:1.25rem}.scroll{max-width:100%}}
"""


def render(queue, question="", result=None):
    rows = "".join(
        f"<tr><td>{escape(row['id'])}</td><td>{escape(row['scheduled_date'])}</td>"
        f"<td>{escape(row['department'])}</td><td>{escape(row['code'])}</td><td>{row['score']:.0%}</td></tr>"
        for row in queue[:10]
    )
    rows = rows or "<tr><td colspan='5'>No booked appointments in this snapshot.</td></tr>"
    answer = ""
    if result:
        if result["answer"]:
            sources = ", ".join(result["citations"])
            answer = f'<div class="answer"><strong>{escape(sources)}</strong><p>{escape(result["answer"])}</p></div>'
        else:
            answer = f'<div class="answer"><strong>No answer</strong><p>{escape(result["reason"])}</p></div>'
    return f"""<!doctype html><html lang="en"><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Outpatient Scheduling Review</title><style>{STYLE}</style>
<main><header><h1>Outpatient Scheduling Review</h1>
<p>Synthetic outpatient scheduling data. Use the queue to prioritize manual reminder review.</p></header>
<div class="grid"><section><h2>Reminder queue</h2><p>Up to ten booked appointments ranked by estimated no-show risk.</p>
<div class="scroll"><table><thead><tr><th>Appointment</th><th>Date</th><th>Department</th><th>Cost center</th><th>Risk</th></tr></thead>
<tbody>{rows}</tbody></table></div></section>
<section><h2>Procedure handbook</h2><p>Ask a question about the simulated operating procedures.</p>
<form method="post" action="/ask"><label for="question">Question</label>
<textarea name="question" id="question" required maxlength="400"
placeholder="When should I send the first reminder?">{escape(question)}</textarea>
<button type="submit">Find an answer</button></form>{answer}</section></div></main></html>"""


def make_handler(database, model_url):
    from outpatient.model import review_queue
    from outpatient.rag import abstention, grounded_answer, retrieve

    class Handler(BaseHTTPRequestHandler):
        def reply(self, status, content, content_type):
            body = content.encode()
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def page(self, question="", result=None, status=200):
            with connect(database) as connection:
                queue = review_queue(connection)
            self.reply(status, render(queue, question, result), "text/html; charset=utf-8")

        def do_GET(self):
            path = urlsplit(self.path).path
            if path == "/health":
                self.reply(200, json.dumps({"status": "ok"}), "application/json")
            elif path == "/":
                self.page()
            else:
                self.send_error(404)

        def do_POST(self):
            if urlsplit(self.path).path != "/ask":
                self.send_error(404)
                return
            try:
                length = int(self.headers.get("Content-Length", ""))
                if not 1 <= length <= 4096:
                    raise ValueError
            except ValueError:
                self.send_error(400, "Invalid form size")
                return
            values = parse_qs(self.rfile.read(length).decode("utf-8", errors="replace"))
            question = values.get("question", [""])[0].strip()
            if not 1 <= len(question) <= 400:
                self.page(question[:400], abstention("Enter a question of 1–400 characters."), status=400)
                return
            try:
                result = grounded_answer(question, retrieve(question), model_url)
            except (URLError, TimeoutError, ValueError, KeyError, IndexError, TypeError):
                self.page(question, abstention("Local language model unavailable."), status=503)
                return
            self.page(question, result)

    return Handler


def serve(database, model_url, host, port):
    with ThreadingHTTPServer((host, port), make_handler(database, model_url)) as server:
        print(f"Outpatient Scheduling Review listening on {host}:{port}", flush=True)
        server.serve_forever()
