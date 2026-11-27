"""Fixed synthetic questions for comparison of the three response modes."""

QUESTIONS = (
    ("How long before the visit do we send the first reminder?", "REM-01", ("48 hours",)),
    ("When do we retry if a reminder call has no answer?", "REM-02", ("next business day",)),
    ("What should we do with a wrong telephone number?", "REM-03", ("unverified", "Registration")),
    ("Do I cancel the original booking before confirming the new slot?", "RES-01", ("Confirm the new slot before",)),
    ("When does a cancelled slot get released?", "CAN-01", ("after confirmation",)),
    ("How many of the highest-scored booked appointments should be reviewed first?", "REV-01", ("ten",)),
    ("Who handles a missing department cost center mapping?", "ERP-01", ("Finance Systems",)),
    ("Who is alerted when the scheduling feed is unavailable?", "SYS-01", ("scheduling systems desk",)),
    ("Who reconciles a disagreement between the scheduling record and appointment feed?", "EMR-01", ("Health Information Management",)),
    ("Where do wheelchair requests go?", "ACC-01", ("Patient Access",)),
    ("What is the cafeteria lunch menu?", None, ()),
    ("What is the parking fee for a scheduled visit?", None, ()),
    ("Is a refund issued after cancellation?", None, ()),
    ("Which taxi companies serve the hospital?", None, ()),
)
