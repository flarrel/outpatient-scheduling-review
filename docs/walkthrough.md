# Operator walkthrough

This is a solo walkthrough with synthetic systems and records. A presenter can switch between scheduling coordinator, integration engineer, and product reviewer.

1. **Integration engineer.** Start the fixture service and import the three feeds. Point out the one duplicate HIS row, one invalid HIS row, and one invalid EMR row in the import counts. Show that 1,200 matched appointments and three department mappings are still available. Repeat the import to confirm the counts stay the same.
2. **Scheduling coordinator.** Open the review queue. Find the appointment ID, date, department, and cost center for the first row. The ranked scores help prioritize manual reminder review. There is no automated patient outreach.
3. **Scheduling coordinator.** Ask “How long before the visit do we send the first reminder?” Read the cited sentence from REM-01. Then ask “What is the cafeteria lunch menu?” and show the abstention.
4. **Product reviewer.** Run the model and handbook evaluations. Compare precision at 44 appointments and discuss the false positives. Contrast retrieval-only with model-backed answers. Inspect one handbook question where the model abstains even though retrieval finds the correct source.
5. **Handoff.** An integration engineer would review schema assumptions and failed imports. A scheduling coordinator would check whether the review order matches the workflow. A service operator would check the health endpoint, runtime settings, and recovery steps. These review roles are simulated here.
