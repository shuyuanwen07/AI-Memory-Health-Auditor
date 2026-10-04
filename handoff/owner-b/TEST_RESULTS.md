# Owner B Test Results



## 1. Development extraction check



The deterministic memory extractor was evaluated against the 12 Owner A development scenarios.



| Measure | Result |

|---|---:|

| Gold memories | 27 |

| Extracted memories | 27 |

| Matched memories | 27 |

| Memory recall | 100.0% |

| Memory precision | 100.0% |

| Gold relationships | 12 |

| Matched relationships | 12 |

| Relationship recall | 100.0% |



These results apply only to the supplied 12-scenario development annotation set and the matching procedure used by the engineering check.



They do not establish general memory-extraction accuracy.



## 2. Owner B regression suite



Test file:



`backend/tests/test\_rule\_based\_pipeline.py`



The suite contains seven focused regression tests covering:



1. Basic pipeline pass/fail behaviour.

2. Chronological message ordering and relationship detection.

3. Traceable and dimension-balanced test generation.

4. Natural transitions and exclusion of assistant-authored text.

5. Answer-leak prevention and small-budget dimension balancing.

6. Bidirectional conflict deduplication.

7. Specific topic detection for supported memory patterns.



Result:



`7 passed`



## 3. Full backend regression suite



Command:



`python3 -m pytest backend\\tests -v`



Result:



`136 passed, 1 skipped, 1 warning`



The skipped test was:



`backend\\tests\\test\_postgresql\_api\_smoke.py::test\_postgresql\_migrated\_api\_path`



Reason: PostgreSQL integration is enabled only when the required test/environment condition is present.



The warning was a Starlette/AnyIO deprecation warning from the test client and was not treated as a project failure.



## 4. Generator validation



The final deterministic generator version is:



`rule-based-v4`



The generator:



- keeps evaluator-facing expected behaviour separate from target-facing prompts;

- avoids placing canonical memory values directly into target prompts;

- maintains supporting-memory traceability;

- balances dimensions under limited test budgets;

- deduplicates symmetric conflict pairs;

- provides topic-specific prompts for supported patterns.



## 5. Formal-evaluation boundary



No human-labelled evaluation was performed.



The development validation therefore does not provide:



- human inter-annotator agreement;

- evaluator validity against manual labels;

- formal target-agent health results;

- official LongMemEval, LoCoMo, or BEAM benchmark scores.



External benchmark-compatible work must follow `mha-formal-v1` and be reported as local compatibility results where applicable.



## 6. Freeze status



Owner B implementation and regression checks are considered frozen for handoff.



Further changes to the generator, prompts, policies, suite membership, or labels after this point should create a new engineering/protocol revision rather than silently modifying this frozen baseline.

