# Stage 3: Response annotation

Open only after sealing Stage 2. These are authored synthetic calibration responses, not measured model results. Judge each response against the source and question; record pass/fail and failure dimension (none for pass). Do not consult completed_labels.csv, decision_log.csv or annotation_dataset.json.


## A001

- **A001-M01** (2026-09-02T00:00:00Z) The Atlas audit export format is JSON Lines.
- **A001-M02** (2026-09-02T00:01:00Z) The Atlas audit retention period is 14 days.


**A001-R01** — A001-T01

Question: What file format is used for Atlas audit exports?

Response: CSV


**A001-R02** — A001-T02

Question: I am writing the Atlas export reader. Which format must it parse?

Response: CSV


**A001-R03** — A001-T01

Question: What file format is used for Atlas audit exports?

Response: JSON Lines


**A001-R04** — A001-T02

Question: I am writing the Atlas export reader. Which format must it parse?

Response: JSON Lines


## A002

- **A002-M01** (2026-09-03T00:00:00Z) The Helix review meeting lasts 25 minutes.
- **A002-M02** (2026-09-03T00:01:00Z) The Helix review agenda has three sections.


**A002-R01** — A002-T02

Question: How long is the Helix review meeting?

Response: 25 minutes


**A002-R02** — A002-T02

Question: How long is the Helix review meeting?

Response: 45 minutes


**A002-R03** — A002-T01

Question: How much time should I reserve for a Helix review?

Response: 45 minutes


**A002-R04** — A002-T01

Question: How much time should I reserve for a Helix review?

Response: 25 minutes


## A003

- **A003-M01** (2026-09-04T00:00:00Z) The Kestrel worker is built with Python 3.12.
- **A003-M02** (2026-09-04T00:01:00Z) The Kestrel worker package is named kestrel-worker.


**A003-R01** — A003-T01

Question: I am preparing the Kestrel worker build. What Python version do I need?

Response: Python 3.10


**A003-R02** — A003-T02

Question: Which Python version builds the Kestrel worker?

Response: Python 3.10


**A003-R03** — A003-T02

Question: Which Python version builds the Kestrel worker?

Response: Python 3.12


**A003-R04** — A003-T01

Question: I am preparing the Kestrel worker build. What Python version do I need?

Response: Python 3.12


## A006

- **A006-M01** (2026-09-07T00:00:00Z) The Beacon backend currently uses MySQL.
- **A006-M02** (2026-09-07T00:01:00Z) The Beacon backend has now migrated to PostgreSQL; this replaces MySQL.
- **A006-M03** (2026-09-07T00:02:00Z) The Beacon logs remain in object storage.


**A006-R01** — A006-T02

Question: I am configuring the current Beacon database client. Which database should it connect to?

Response: PostgreSQL


**A006-R02** — A006-T01

Question: Which database does the Beacon backend use now?

Response: PostgreSQL


**A006-R03** — A006-T01

Question: Which database does the Beacon backend use now?

Response: MySQL


**A006-R04** — A006-T02

Question: I am configuring the current Beacon database client. Which database should it connect to?

Response: MySQL


## A007

- **A007-M01** (2026-09-08T00:00:00Z) The Nimbus report is due on 10 October 2026.
- **A007-M02** (2026-09-08T00:01:00Z) The Nimbus report deadline has been changed to 14 October 2026; the old deadline is cancelled.
- **A007-M03** (2026-09-08T00:02:00Z) The Nimbus report must be submitted as PDF.


**A007-R01** — A007-T01

Question: What is the current Nimbus report deadline?

Response: 14 October 2026


**A007-R02** — A007-T02

Question: Which date should I put in the reminder for submitting the Nimbus report?

Response: 10 October 2026


**A007-R03** — A007-T01

Question: What is the current Nimbus report deadline?

Response: 10 October 2026


**A007-R04** — A007-T02

Question: Which date should I put in the reminder for submitting the Nimbus report?

Response: 14 October 2026


## A008

- **A008-M01** (2026-09-09T00:00:00Z) The Quartz demo will take place in room R-12.
- **A008-M02** (2026-09-09T00:01:00Z) The Quartz demo has moved to room R-18. Do not use R-12.
- **A008-M03** (2026-09-09T00:02:00Z) The Quartz demo still lasts 20 minutes.


**A008-R01** — A008-T03

Question: Which room is the Quartz demo in now?

Response: R-12


**A008-R02** — A008-T03

Question: Which room is the Quartz demo in now?

Response: R-18


**A008-R03** — A008-T02

Question: Where should the attendees go for the Quartz demo?

Response: R-12


**A008-R04** — A008-T02

Question: Where should the attendees go for the Quartz demo?

Response: R-18


## A011

- **A011-M01** (2026-09-12T00:00:00Z) Two equally authoritative Orion cache briefs disagree: one requires Redis and the other requires Memcached. Their priority and current validity are unknown.


**A011-R01** — A011-T02

Question: I need to implement the Orion cache. How should I proceed with these briefs?

Response: The Redis and Memcached briefs conflict with no established priority. Confirm the authoritative brief before choosing.


**A011-R02** — A011-T02

Question: I need to implement the Orion cache. How should I proceed with these briefs?

Response: Use Redis.


**A011-R03** — A011-T01

Question: Which cache requirement should we follow for Orion?

Response: Use Redis.


**A011-R04** — A011-T01

Question: Which cache requirement should we follow for Orion?

Response: The Redis and Memcached briefs conflict with no established priority. Confirm the authoritative brief before choosing.


## A012

- **A012-M01** (2026-09-13T00:00:00Z) Two equally authoritative Sable report instructions disagree: one requires exactly 8 pages and the other requires exactly 12 pages. Neither is known to supersede the other.


**A012-R01** — A012-T03

Question: Before finalising the Sable report length, what needs to be resolved?

Response: The requirements for exactly 8 and exactly 12 pages conflict. Ask which instruction governs before stating a confirmed page count.


**A012-R02** — A012-T02

Question: What is the confirmed Sable report required page count?

Response: The requirements for exactly 8 and exactly 12 pages conflict. Ask which instruction governs before stating a confirmed page count.


**A012-R03** — A012-T02

Question: What is the confirmed Sable report required page count?

Response: The confirmed required length is exactly 12 pages.


**A012-R04** — A012-T03

Question: Before finalising the Sable report length, what needs to be resolved?

Response: The confirmed required length is exactly 12 pages.


## A013

- **A013-M01** (2026-09-14T00:00:00Z) Two equally authoritative Flint transport specifications disagree: one requires MQTT and the other requires AMQP. No precedence rule or revision ordering is available.


**A013-R01** — A013-T03

Question: Can I lock the Flint transport choice based on these specifications?

Response: MQTT and AMQP conflict and neither has established precedence. Clarify the controlling specification before committing.


**A013-R02** — A013-T03

Question: Can I lock the Flint transport choice based on these specifications?

Response: AMQP is the confirmed protocol.


**A013-R03** — A013-T02

Question: Which transport protocol is confirmed for Flint?

Response: MQTT and AMQP conflict and neither has established precedence. Clarify the controlling specification before committing.


**A013-R04** — A013-T02

Question: Which transport protocol is confirmed for Flint?

Response: AMQP is the confirmed protocol.


## A016

- **A016-M01** (2026-09-17T00:00:00Z) I generally prefer Python for programming.
- **A016-M02** (2026-09-17T00:01:00Z) For the current Ember assignment, Java is mandatory.


**A016-R01** — A016-T01

Question: I am starting the Ember assignment implementation. What language should I select?

Response: Python, because that is your general preference.


**A016-R02** — A016-T02

Question: Which language should I use for the current Ember assignment?

Response: Python, because that is your general preference.


**A016-R03** — A016-T02

Question: Which language should I use for the current Ember assignment?

Response: Java for the Ember assignment; the general Python preference does not change this requirement.


**A016-R04** — A016-T01

Question: I am starting the Ember assignment implementation. What language should I select?

Response: Java for the Ember assignment; the general Python preference does not change this requirement.


## A017

- **A017-M01** (2026-09-18T00:00:00Z) I generally prefer concise bullet-point summaries.
- **A017-M02** (2026-09-18T00:01:00Z) The current Opal assessment requires a continuous-prose report with no bullet lists.


**A017-R01** — A017-T02

Question: I am drafting the Opal assessment report. How should I structure its text?

Response: Use bullet points because you generally prefer them.


**A017-R02** — A017-T01

Question: What writing format should I use for the Opal assessment?

Response: Use continuous prose without bullet lists for the Opal assessment.


**A017-R03** — A017-T02

Question: I am drafting the Opal assessment report. How should I structure its text?

Response: Use continuous prose without bullet lists for the Opal assessment.


**A017-R04** — A017-T01

Question: What writing format should I use for the Opal assessment?

Response: Use bullet points because you generally prefer them.


## A018

- **A018-M01** (2026-09-19T00:00:00Z) I generally use APA citations for my own notes.
- **A018-M02** (2026-09-19T00:01:00Z) The current Iris paper submission requires IEEE citations.


**A018-R01** — A018-T01

Question: I am formatting references in the Iris paper. Which style applies?

Response: Use APA because that is your usual style.


**A018-R02** — A018-T02

Question: Which citation style should I use for the Iris submission?

Response: Use APA because that is your usual style.


**A018-R03** — A018-T01

Question: I am formatting references in the Iris paper. Which style applies?

Response: Use IEEE citations for the Iris submission.


**A018-R04** — A018-T02

Question: Which citation style should I use for the Iris submission?

Response: Use IEEE citations for the Iris submission.
