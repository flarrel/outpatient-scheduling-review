"""Chronological evaluation and a review queue from pre-appointment features."""

from sklearn.compose import ColumnTransformer
from sklearn.dummy import DummyClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, confusion_matrix
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler


def features(rows):
    return [[row["lead_days"], row["prior_no_shows"], row["confirmed"], row["department"]] for row in rows]


def labels(rows):
    return [int(row["status"] == "noshow") for row in rows]


def fit(rows):
    preprocess = ColumnTransformer([
        ("numeric", StandardScaler(), [0, 1, 2]),
        ("department", OneHotEncoder(handle_unknown="ignore"), [3]),
    ])
    classifier = make_pipeline(preprocess, LogisticRegression(max_iter=500, random_state=581))
    return classifier.fit(features(rows), labels(rows))


def completed(connection):
    return connection.execute("""SELECT * FROM appointments WHERE status IN ('fulfilled', 'noshow')
                                 ORDER BY scheduled_date, id""").fetchall()


def rank(rows, scores):
    return sorted(zip(rows, scores), key=lambda pair: (-pair[1], pair[0]["scheduled_date"], pair[0]["id"]))


def metrics(rows, scores, capacity):
    actual = labels(rows)
    ordered = rank(rows, scores)
    selected = {row["id"] for row, _ in ordered[:capacity]}
    tn, fp, fn, tp = confusion_matrix(
        actual, [int(row["id"] in selected) for row in rows], labels=[0, 1],
    ).ravel()
    return {
        "average_precision": round(float(average_precision_score(actual, scores)), 4),
        "precision_at_capacity": round(int(tp) / capacity, 4),
        "true_positives": int(tp), "false_positives": int(fp),
        "false_negatives": int(fn), "true_negatives": int(tn),
    }


def evaluate(connection):
    rows = completed(connection)
    dates = sorted({row["scheduled_date"] for row in rows})
    cutoff = dates[int(len(dates) * 0.8)]
    train = [row for row in rows if row["scheduled_date"] < cutoff]
    test = [row for row in rows if row["scheduled_date"] >= cutoff]
    capacity = max(1, len(test) // 5)
    baseline = DummyClassifier(strategy="prior").fit(features(train), labels(train))
    classifier = fit(train)
    return {
        "test_start": cutoff, "training_rows": len(train), "test_rows": len(test),
        "test_positives": sum(labels(test)), "review_capacity": capacity,
        "historical_rate": metrics(test, baseline.predict_proba(features(test))[:, 1], capacity),
        "logistic_regression": metrics(test, classifier.predict_proba(features(test))[:, 1], capacity),
    }


def review_queue(connection):
    rows = connection.execute("""SELECT appointments.*, code FROM appointments
        JOIN departments ON department = name WHERE status = 'booked'""").fetchall()
    if not rows:
        return []
    model = fit(completed(connection))
    scores = model.predict_proba(features(rows))[:, 1]
    return [{**dict(row), "score": round(float(score), 3)} for row, score in rank(rows, scores)]
