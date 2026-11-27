from contextlib import closing, contextmanager
from http.server import ThreadingHTTPServer
from pathlib import Path
import sqlite3
import tempfile
from threading import Thread
import unittest
from unittest.mock import patch
from urllib.error import URLError
from urllib.parse import urlencode
from urllib.request import urlopen

from outpatient.data import appointment_summary, connect, import_sources, read_sources, synthetic_sources
from outpatient.mock import fixture_handler
from outpatient.model import evaluate, review_queue
from outpatient.rag import grounded_answer, retrieve
from outpatient.web import make_handler


@contextmanager
def localhost(handler):
    with ThreadingHTTPServer(("127.0.0.1", 0), handler) as server:
        worker = Thread(target=server.serve_forever, daemon=True)
        worker.start()
        try:
            yield f"http://127.0.0.1:{server.server_port}"
        finally:
            server.shutdown()
            worker.join()


class IngestionTest(unittest.TestCase):
    def test_http_sources_idempotent_import_and_rollback(self):
        payloads = synthetic_sources()
        with localhost(fixture_handler(payloads)) as address:
            received = read_sources(Path("."), address)
        with self.assertRaises(URLError):
            read_sources(Path("."), address)
        with closing(sqlite3.connect(":memory:")) as database:
            database.row_factory = sqlite3.Row
            counts = import_sources(database, received)
            self.assertEqual(counts, {
                "emr_accepted": 1200, "emr_rejected": 1, "erp_accepted": 3,
                "his_accepted": 1200, "his_duplicates": 1, "his_rejected": 1,
            })
            self.assertEqual(import_sources(database, received), counts)
            summary = appointment_summary(database)
            self.assertEqual(sum(row["total"] for row in summary), 1200)
            self.assertEqual(sum(row["total"] for row in summary if row["status"] == "booked"), 30)
            with self.assertRaises(ValueError):
                import_sources(database, {**received, "emr": {"entry": []}})
            self.assertEqual(appointment_summary(database), summary)

    def test_conflicting_emr_appointment_date_is_rejected(self):
        payloads = synthetic_sources()
        appointment = payloads["emr"]["entry"][0]["resource"]
        appointment["start"] = "2025-01-02T09:00:00+07:00"
        appointment["end"] = "2025-01-02T09:30:00+07:00"
        with closing(sqlite3.connect(":memory:")) as database:
            counts = import_sources(database, payloads)
        self.assertEqual(counts["his_accepted"], 1199)

    def test_chronological_evaluation_and_review_queue(self):
        with closing(sqlite3.connect(":memory:")) as database:
            database.row_factory = sqlite3.Row
            import_sources(database, synthetic_sources())
            results = evaluate(database)
            queue = review_queue(database)
        self.assertEqual(results["test_start"], "2025-04-04")
        self.assertEqual(results["test_rows"], 224)
        self.assertEqual(results["review_capacity"], 44)
        self.assertGreater(results["logistic_regression"]["precision_at_capacity"],
                           results["historical_rate"]["precision_at_capacity"])
        self.assertEqual(len(queue), 30)
        self.assertTrue(all(row["status"] == "booked" for row in queue))
        self.assertEqual(sorted(row["score"] for row in queue)[::-1], [row["score"] for row in queue])


class HandbookTest(unittest.TestCase):
    def test_model_quote_is_linked_to_its_source(self):
        question = "When do we send the first reminder?"
        passages = retrieve(question)
        self.assertEqual(passages[0].identifier, "REM-01")
        responses = (
            ("48 hours", ["REM-01"]),
            ("10 hours", []),
            ("UNKNOWN", []),
        )
        for response, citations in responses:
            with self.subTest(response=response), patch("outpatient.rag.completion", return_value=response):
                result = grounded_answer(question, passages, "http://unused")
                self.assertEqual(result["citations"], citations)

    def test_no_retrieval_abstains_without_calling_model(self):
        with patch("outpatient.rag.completion") as completion:
            result = grounded_answer("What is the cafeteria lunch menu?", [], None)
        self.assertIsNone(result["answer"])
        completion.assert_not_called()

    def test_browser_queue_and_unanswerable_form(self):
        with tempfile.TemporaryDirectory(dir=Path("../artifacts").resolve()) as target:
            database = Path(target) / "appointments.sqlite3"
            with closing(connect(database)) as connection:
                import_sources(connection, synthetic_sources())
            with localhost(make_handler(database, None)) as address:
                with urlopen(address + "/health") as response:
                    self.assertEqual(response.status, 200)
                with urlopen(address) as response:
                    page = response.read().decode()
                    self.assertIn("Reminder queue", page)
                    self.assertIn("sim-", page)
                form = urlencode({"question": "What is the cafeteria lunch menu?"}).encode()
                with urlopen(address + "/ask", data=form) as response:
                    self.assertIn("No answer", response.read().decode())


if __name__ == "__main__":
    unittest.main()
