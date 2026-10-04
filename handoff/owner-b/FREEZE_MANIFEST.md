# Owner B Engineering Freeze Manifest



## Freeze identity



- Owner: B

- Freeze type: Engineering / synthetic development baseline

- Formal protocol: `mha-formal-v1`

- Owner A distribution: `owner-a-english-v1`

- Owner A dataset version: `2.0.0-ai-reviewed`

- Owner A development fingerprint:

&#x20; `6ac3dc23b4af33e9bcc0813ad9ce096d86826756d4a7688ed85790f44252fb5`



## Frozen generator



- Component: `backend/app/test\_generator/rule\_based.py`

- Class: `RuleBasedTestGenerator`

- Generator version: `rule-based-v4`



## Engineering target configuration



- Provider: `rule\_based`

- Model: `rule-based-target-ai`

- Target configuration: `WEAK`

- Temperature: `0`

- Prompt template version: `rule-based-v1`



The deterministic local target is used for engineering and reproducibility checks only.



## Frozen regression suite



- File:

&#x20; `backend/tests/test\_rule\_based\_pipeline.py`

- Focused tests: 7

- Result: 7 passed



## Full regression result



- Command:

&#x20; `python3 -m pytest backend\\tests -v`

- Passed: 136

- Skipped: 1

- Failed: 0

- Warning: 1



## Development validation



- Development scenarios: 12

- Gold memories: 27

- Memory matches: 27/27

- Memory precision: 100.0%

- Memory recall: 100.0%

- Gold relationships: 12

- Relationship matches: 12/12

- Relationship recall: 100.0%



## Data restrictions



- Human labels: 0

- Held-out scenarios: not used for development

- Rejected Owner A tests: retained for test-validity analysis; not executed as target questions

- Formal evaluation readiness in Owner A package: false



## Reproducibility note



The local rule-based engineering path is deterministic under saved inputs and configuration.



This freeze must not be interpreted as a formal cloud-model experiment or provider-variance result.



## Change policy



Any change to the frozen generator, target-facing prompts, generator version, test suite, labels, policies, or development sample membership should be recorded as a new revision.



The frozen baseline should remain intact for comparison and handoff.

