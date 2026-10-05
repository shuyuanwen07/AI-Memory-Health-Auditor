# Failure evidence: A019-T002

## Source

- A019-M01: “I generally prefer colourful charts in my working notes.”
- A019-M02: “The current Pebble print submission requires grayscale charts.”

## Generated question

For the current preference, a general preference conflicts with a current requirement. State the requirement that applies now first, then briefly explain why it overrides the preference.

## Actual response

Based on the retrieved record, I generally prefer colourful charts in my working notes

## Decisions

Automated evaluator: PASS. Final user-confirmed reference: FAIL, appropriate_use. The response repeats a general preference instead of stating/applying the current submission constraint. Relevant source evidence is A019-M01 and A019-M02. Reviewer 1 originally used conflict_resolution; the user confirmed appropriate_use in adjudication. Original labels remain preserved.

This is a false negative when failure is the positive class: the target failed and the Auditor did not detect the failure. The lexical evaluator's PASS does not establish contextual correctness. Code was not changed after observing this case.
