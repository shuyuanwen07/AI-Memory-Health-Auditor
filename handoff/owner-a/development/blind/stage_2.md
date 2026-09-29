# Stage 2: Test validity annotation

Open only after sealing Stage 1. Candidate expected behaviours below are proposals, not accepted reference answers. Check them against the source. Accept only grounded, observable, non-answer-leaking questions.


## A001

- **A001-M01** (2026-09-02T00:00:00Z) The Atlas audit export format is JSON Lines.
- **A001-M02** (2026-09-02T00:01:00Z) The Atlas audit retention period is 14 days.


**A001-T01** What file format is used for Atlas audit exports?

Proposed expected behaviour: State JSON Lines; do not substitute CSV.


**A001-T02** I am writing the Atlas export reader. Which format must it parse?

Proposed expected behaviour: State JSON Lines; do not substitute CSV.


**A001-T03** Is JSON Lines the Atlas export format?

Proposed expected behaviour: State JSON Lines.


## A002

- **A002-M01** (2026-09-03T00:00:00Z) The Helix review meeting lasts 25 minutes.
- **A002-M02** (2026-09-03T00:01:00Z) The Helix review agenda has three sections.


**A002-T01** How much time should I reserve for a Helix review?

Proposed expected behaviour: State 25 minutes; do not substitute 45 minutes.


**A002-T02** How long is the Helix review meeting?

Proposed expected behaviour: State 25 minutes; do not substitute 45 minutes.


**A002-T03** How long is the Helix planning workshop?

Proposed expected behaviour: No specific factual answer is supported; acknowledge the missing evidence.


## A003

- **A003-M01** (2026-09-04T00:00:00Z) The Kestrel worker is built with Python 3.12.
- **A003-M02** (2026-09-04T00:01:00Z) The Kestrel worker package is named kestrel-worker.


**A003-T01** I am preparing the Kestrel worker build. What Python version do I need?

Proposed expected behaviour: State Python 3.12; do not substitute Python 3.10.


**A003-T02** Which Python version builds the Kestrel worker?

Proposed expected behaviour: State Python 3.12; do not substitute Python 3.10.


**A003-T03** What Python version builds every team project?

Proposed expected behaviour: No specific factual answer is supported; acknowledge the missing evidence.


## A006

- **A006-M01** (2026-09-07T00:00:00Z) The Beacon backend currently uses MySQL.
- **A006-M02** (2026-09-07T00:01:00Z) The Beacon backend has now migrated to PostgreSQL; this replaces MySQL.
- **A006-M03** (2026-09-07T00:02:00Z) The Beacon logs remain in object storage.


**A006-T01** Which database does the Beacon backend use now?

Proposed expected behaviour: Use PostgreSQL as current; MySQL is superseded.


**A006-T02** I am configuring the current Beacon database client. Which database should it connect to?

Proposed expected behaviour: Use PostgreSQL as current; MySQL is superseded.


**A006-T03** What database will Beacon migrate to next year?

Proposed expected behaviour: No specific factual answer is supported; acknowledge the missing evidence.


## A007

- **A007-M01** (2026-09-08T00:00:00Z) The Nimbus report is due on 10 October 2026.
- **A007-M02** (2026-09-08T00:01:00Z) The Nimbus report deadline has been changed to 14 October 2026; the old deadline is cancelled.
- **A007-M03** (2026-09-08T00:02:00Z) The Nimbus report must be submitted as PDF.


**A007-T01** What is the current Nimbus report deadline?

Proposed expected behaviour: Use 14 October 2026 as current; 10 October 2026 is superseded.


**A007-T02** Which date should I put in the reminder for submitting the Nimbus report?

Proposed expected behaviour: Use 14 October 2026 as current; 10 October 2026 is superseded.


**A007-T03** When is the Nimbus presentation due?

Proposed expected behaviour: No specific factual answer is supported; acknowledge the missing evidence.


## A008

- **A008-M01** (2026-09-09T00:00:00Z) The Quartz demo will take place in room R-12.
- **A008-M02** (2026-09-09T00:01:00Z) The Quartz demo has moved to room R-18. Do not use R-12.
- **A008-M03** (2026-09-09T00:02:00Z) The Quartz demo still lasts 20 minutes.


**A008-T01** Where is the Quartz weekly planning meeting?

Proposed expected behaviour: No specific factual answer is supported; acknowledge the missing evidence.


**A008-T02** Where should the attendees go for the Quartz demo?

Proposed expected behaviour: Use R-18 as current; R-12 is superseded.


**A008-T03** Which room is the Quartz demo in now?

Proposed expected behaviour: Use R-18 as current; R-12 is superseded.


## A011

- **A011-M01** (2026-09-12T00:00:00Z) Two equally authoritative Orion cache briefs disagree: one requires Redis and the other requires Memcached. Their priority and current validity are unknown.


**A011-T01** Which cache requirement should we follow for Orion?

Proposed expected behaviour: The Redis and Memcached briefs conflict with no established priority. Confirm the authoritative brief before choosing.


**A011-T02** I need to implement the Orion cache. How should I proceed with these briefs?

Proposed expected behaviour: The Redis and Memcached briefs conflict with no established priority. Confirm the authoritative brief before choosing.


**A011-T03** Which Orion brief was approved most recently?

Proposed expected behaviour: No specific factual answer is supported; acknowledge the missing evidence.


## A012

- **A012-M01** (2026-09-13T00:00:00Z) Two equally authoritative Sable report instructions disagree: one requires exactly 8 pages and the other requires exactly 12 pages. Neither is known to supersede the other.


**A012-T01** When was the 12-page instruction approved?

Proposed expected behaviour: No specific factual answer is supported; acknowledge the missing evidence.


**A012-T02** What is the confirmed Sable report required page count?

Proposed expected behaviour: The requirements for exactly 8 and exactly 12 pages conflict. Ask which instruction governs before stating a confirmed page count.


**A012-T03** Before finalising the Sable report length, what needs to be resolved?

Proposed expected behaviour: The requirements for exactly 8 and exactly 12 pages conflict. Ask which instruction governs before stating a confirmed page count.


## A013

- **A013-M01** (2026-09-14T00:00:00Z) Two equally authoritative Flint transport specifications disagree: one requires MQTT and the other requires AMQP. No precedence rule or revision ordering is available.


**A013-T01** Which Flint transport specification is newer?

Proposed expected behaviour: No specific factual answer is supported; acknowledge the missing evidence.


**A013-T02** Which transport protocol is confirmed for Flint?

Proposed expected behaviour: MQTT and AMQP conflict and neither has established precedence. Clarify the controlling specification before committing.


**A013-T03** Can I lock the Flint transport choice based on these specifications?

Proposed expected behaviour: MQTT and AMQP conflict and neither has established precedence. Clarify the controlling specification before committing.


## A016

- **A016-M01** (2026-09-17T00:00:00Z) I generally prefer Python for programming.
- **A016-M02** (2026-09-17T00:01:00Z) For the current Ember assignment, Java is mandatory.


**A016-T01** I am starting the Ember assignment implementation. What language should I select?

Proposed expected behaviour: Java for the Ember assignment; the general Python preference does not change this requirement.


**A016-T02** Which language should I use for the current Ember assignment?

Proposed expected behaviour: Java for the Ember assignment; the general Python preference does not change this requirement.


**A016-T03** Which language is mandatory for all future assignments?

Proposed expected behaviour: No specific factual answer is supported; acknowledge the missing evidence.


## A017

- **A017-M01** (2026-09-18T00:00:00Z) I generally prefer concise bullet-point summaries.
- **A017-M02** (2026-09-18T00:01:00Z) The current Opal assessment requires a continuous-prose report with no bullet lists.


**A017-T01** What writing format should I use for the Opal assessment?

Proposed expected behaviour: Use continuous prose without bullet lists for the Opal assessment.


**A017-T02** I am drafting the Opal assessment report. How should I structure its text?

Proposed expected behaviour: Use continuous prose without bullet lists for the Opal assessment.


**A017-T03** Does the user dislike bullet points?

Proposed expected behaviour: No specific factual answer is supported; acknowledge the missing evidence.


## A018

- **A018-M01** (2026-09-19T00:00:00Z) I generally use APA citations for my own notes.
- **A018-M02** (2026-09-19T00:01:00Z) The current Iris paper submission requires IEEE citations.


**A018-T01** I am formatting references in the Iris paper. Which style applies?

Proposed expected behaviour: Use IEEE citations for the Iris submission.


**A018-T02** Which citation style should I use for the Iris submission?

Proposed expected behaviour: Use IEEE citations for the Iris submission.


**A018-T03** Which citation style is mandatory for every course?

Proposed expected behaviour: No specific factual answer is supported; acknowledge the missing evidence.
