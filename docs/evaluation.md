# Evaluation

## Synthetic scheduling data

The generator uses seed 581 to create 1,200 appointments across three departments. It assigns a higher no-show probability to appointments with a longer lead time, more prior no-shows, and no confirmation. The generator is designed to exercise the workflow under a known signal. The metrics characterize this synthetic scenario.

The local HTTP integration run accepted 1,200 matched appointment IDs and three department mappings. It skipped one duplicate HIS row and rejected one bad HIS date and one invalid EMR status. The tests also cover a disagreement between HIS and EMR dates, an unavailable fixture service, repeat imports, and preservation of the last snapshot after an empty import.

## Reminder queue

The chronological holdout starts on April 4, 2025. The model trained on 894 earlier completed appointments and was evaluated on 224 later completed appointments, including 38 no-shows. Cancelled appointments and the 30 still-booked appointments were excluded from training and evaluation. Features are department, reminder confirmation, booking lead time, and prior no-shows. These are defined as known before the reminder decision.

| Method | Average precision | Precision at 44 | True positives | False positives | False negatives | True negatives |
|---|---:|---:|---:|---:|---:|---:|
| Historical-rate baseline | 0.1696 | 9.1% | 4 | 40 | 34 | 146 |
| Logistic regression | 0.3997 | 40.9% | 18 | 26 | 20 | 160 |

The capacity was fixed at the top 20% of the holdout, rounded down. Identical baseline scores were ordered by appointment date and ID. The queue ranks currently booked appointments using a model fit on all available completed rows. A coordinator reviews the queue and decides what action to take.

## Handbook answers

The same 14 synthetic questions were evaluated in three modes on Apple Silicon with Qwen2.5-0.5B-Instruct Q4_K_M. Ten questions had an expected source and four were unsupported. Answerable cases were scored by expected terms and citation ID, and unsupported cases by abstention. Response times are warm single-request observations from one run. The final prompt was refined using development runs on this small set, so these are regression results.

| Method | Correct answerable | Correct abstentions | Correct citation ID | Typical response time |
|---|---:|---:|---:|---:|
| Retrieval only | 10/10 | 2/4 | 10/10 | 0.4 ms |
| Model only | 0/10 | 0/4 | 0/10 | 98.7 ms |
| Retrieval plus model | 8/10 | 4/4 | 8/10 | 46.5 ms |

Both retrieval modes included the expected source among the top three results on all ten answerable cases. Model-only output had no source available. The app uses the model to suggest a short span and displays the exact supporting sentence only when there is one matching sentence and it comes from the top retrieved passage. In this run the method traded two correct answers for two additional correct abstentions relative to retrieval alone.

The two missed answers concerned confirming a new appointment slot and releasing a cancelled slot. The model returned unusable or mismatched text even though retrieval surfaced the correct source. Exact quotation verifies provenance. The question-level check is still needed to test whether a passage answers the question.

## Verification

The native walkthrough used all three fixture APIs, the ranked queue, one cited reminder answer, and one abstention. Six automated tests passed. The Linux ARM64 application image ran in Docker and in a one-node kind Kubernetes cluster. Both reached the health endpoint and rendered the review queue. Model-backed answers were exercised in the native macOS setup. The walkthrough and interface contracts use synthetic scenarios. Production performance, live system compatibility, and operator usefulness would require separate evaluation.
