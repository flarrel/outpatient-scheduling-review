"""Synthetic scheduling records and the SQLite import boundary."""

from collections import Counter
from datetime import date, datetime, timedelta
import json
import math
import random
import sqlite3
from urllib.request import urlopen


DEPARTMENTS = {"cardiology": "CC-100", "physiotherapy": "CC-200", "general": "CC-300"}
SOURCES = {"his": "/his/appointments", "emr": "/fhir/Appointment", "erp": "/erp/dimensions"}
STATUSES = {"booked", "fulfilled", "noshow", "cancelled"}


def synthetic_sources(seed=581, size=1200):
    """Return three synthetic exports, with a few deliberately invalid rows."""
    rng = random.Random(seed)
    facilities = list(DEPARTMENTS)
    his = []
    emr = []
    for index in range(size):
        day = date(2025, 1, 1) + timedelta(days=index // 10)
        department = rng.choice(facilities)
        lead_days = rng.randrange(1, 46)
        prior_no_shows = rng.choices([0, 1, 2, 3], [65, 25, 8, 2])[0]
        confirmed = rng.random() < 0.72
        log_odds = -2.0 + 0.038 * lead_days + 0.5 * prior_no_shows - 0.8 * confirmed
        risk = 1 / (1 + math.exp(-log_odds))
        if index >= size - 30:
            status = "booked"
        elif rng.random() < 0.04:
            status = "cancelled"
        else:
            status = "noshow" if rng.random() < risk else "fulfilled"
        record = {
            "id": f"sim-{index:04d}",
            "scheduled_date": day.isoformat(),
            "department": department,
            "lead_days": lead_days,
            "prior_no_shows": prior_no_shows,
            "confirmed": confirmed,
        }
        his.append(record)
        emr.append({"resource": {
            "resourceType": "Appointment",
            "id": record["id"],
            "status": status,
            "start": f"{day.isoformat()}T09:00:00+07:00",
            "end": f"{day.isoformat()}T09:30:00+07:00",
            "participant": [{"actor": {"reference": f"Patient/demo-{index:04d}"}, "status": "accepted"}],
        }})
    his.extend([dict(his[0]), {**his[1], "id": "bad-date", "scheduled_date": "invalid"}])
    emr.append({"resource": {"resourceType": "Appointment", "id": "bad-status", "status": "invalid"}})
    erp = [{"code": value, "displayName": key} for key, value in DEPARTMENTS.items()]
    return {"his": {"appointments": his}, "emr": {"resourceType": "Bundle", "type": "searchset", "entry": emr}, "erp": {"value": erp}}


def write_sources(directory):
    directory.mkdir(parents=True, exist_ok=True)
    for source, payload in synthetic_sources().items():
        (directory / f"{source}.json").write_text(json.dumps(payload, indent=2) + "\n")


def read_sources(directory, url=None):
    if url:
        payloads = {}
        for source, endpoint in SOURCES.items():
            with urlopen(url.rstrip("/") + endpoint, timeout=3) as response:
                payloads[source] = json.load(response)
        return payloads
    return {source: json.loads((directory / f"{source}.json").read_text()) for source in SOURCES}


def connect(path):
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    return connection


def appointment_row(record):
    identifier = record["id"].strip()
    if not identifier or type(record["confirmed"]) is not bool:
        raise ValueError("invalid appointment fields")
    for name in ("lead_days", "prior_no_shows"):
        if type(record[name]) is not int or record[name] < 0:
            raise ValueError(name)
    return (
        identifier, date.fromisoformat(record["scheduled_date"]).isoformat(),
        record["department"].strip().casefold(), record["lead_days"],
        record["prior_no_shows"], int(record["confirmed"]),
    )


def import_sources(connection, payloads):
    """Validate rows before atomically replacing the current source snapshot."""
    counts = Counter()
    departments = {}
    appointments = {}
    outcomes = {}
    for item in payloads["erp"]["value"]:
        try:
            name, code = item["displayName"].strip().casefold(), item["code"].strip()
            if not name or not code:
                raise ValueError("empty department field")
            if name in departments:
                counts["erp_duplicates"] += 1
                continue
            departments[name] = code
        except (AttributeError, KeyError, TypeError, ValueError):
            counts["erp_rejected"] += 1

    for item in payloads["emr"]["entry"]:
        try:
            resource = item["resource"]
            identifier, status = resource["id"].strip(), resource["status"]
            if resource["resourceType"] != "Appointment" or not identifier or status not in STATUSES:
                raise ValueError("invalid appointment resource")
            if identifier in outcomes:
                counts["emr_duplicates"] += 1
                continue
            start = datetime.fromisoformat(resource["start"])
            end = datetime.fromisoformat(resource["end"])
            if start.utcoffset() is None or end.utcoffset() is None or end <= start:
                raise ValueError("invalid appointment time range")
            outcomes[identifier] = (status, start.date().isoformat())
        except (AttributeError, KeyError, TypeError, ValueError):
            counts["emr_rejected"] += 1

    for item in payloads["his"]["appointments"]:
        try:
            row = appointment_row(item)
            identifier, scheduled_date, department, *_ = row
            if identifier in appointments:
                counts["his_duplicates"] += 1
                continue
            if department not in departments or identifier not in outcomes:
                raise ValueError("missing department or EMR match")
            status, emr_date = outcomes[identifier]
            if scheduled_date != emr_date:
                raise ValueError("conflicting appointment date")
            appointments[identifier] = row + (status,)
        except (AttributeError, KeyError, TypeError, ValueError):
            counts["his_rejected"] += 1

    if not appointments:
        raise ValueError("source snapshot has no matched appointments")

    with connection:
        connection.execute("CREATE TABLE IF NOT EXISTS departments (name TEXT PRIMARY KEY, code TEXT NOT NULL)")
        connection.execute("""CREATE TABLE IF NOT EXISTS appointments (
            id TEXT PRIMARY KEY, scheduled_date TEXT NOT NULL, department TEXT NOT NULL,
            lead_days INTEGER NOT NULL, prior_no_shows INTEGER NOT NULL,
            confirmed INTEGER NOT NULL, status TEXT NOT NULL
        )""")
        connection.execute("DELETE FROM appointments")
        connection.execute("DELETE FROM departments")
        connection.executemany("INSERT INTO departments VALUES (?, ?)", sorted(departments.items()))
        connection.executemany("INSERT INTO appointments VALUES (?, ?, ?, ?, ?, ?, ?)", appointments.values())

    counts.update(erp_accepted=len(departments), emr_accepted=len(outcomes), his_accepted=len(appointments))
    return dict(sorted(counts.items()))


def appointment_summary(connection):
    query = """SELECT department, code, status, COUNT(*) AS total
               FROM appointments JOIN departments ON department = name
               GROUP BY department, code, status ORDER BY department, status"""
    return [dict(row) for row in connection.execute(query)]
