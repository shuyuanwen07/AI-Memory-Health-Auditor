# Stage 1: Memory and relationship annotation

Synthetic source only. Complete and seal this stage before opening Stage 2. Do not open completed_labels.csv, decision_log.csv or annotation_dataset.json or the other annotator's sheet. For each memory candidate decide include/exclude and cite exact source message IDs. Check the FULL source for omitted facts; record additional proposals separately. Label each ORDERED relationship pair; none is permitted.


## A001

- **A001-M01** (2026-09-02T00:00:00Z) The Atlas audit export format is JSON Lines.
- **A001-M02** (2026-09-02T00:01:00Z) The Atlas audit retention period is 14 days.


Candidates:
- **A001-G01** The Atlas audit export format is JSON Lines.
- **A001-G02** The user personally prefers JSON Lines.
- **A001-G03** The Atlas audit retention period is 14 days.

Ordered pairs (source → target):
- **A001-P01** A001-G03 → A001-G01
- **A001-P02** A001-G01 → A001-G03

## A002

- **A002-M01** (2026-09-03T00:00:00Z) The Helix review meeting lasts 25 minutes.
- **A002-M02** (2026-09-03T00:01:00Z) The Helix review agenda has three sections.


Candidates:
- **A002-G01** The Helix review agenda has three sections.
- **A002-G02** The user prefers short meetings.
- **A002-G03** The Helix review meeting lasts 25 minutes.

Ordered pairs (source → target):
- **A002-P01** A002-G01 → A002-G03
- **A002-P02** A002-G03 → A002-G01

## A003

- **A003-M01** (2026-09-04T00:00:00Z) The Kestrel worker is built with Python 3.12.
- **A003-M02** (2026-09-04T00:01:00Z) The Kestrel worker package is named kestrel-worker.


Candidates:
- **A003-G01** The Kestrel worker is built with Python 3.12.
- **A003-G02** All team projects use Python 3.12.
- **A003-G03** The Kestrel worker package is named kestrel-worker.

Ordered pairs (source → target):
- **A003-P01** A003-G03 → A003-G01
- **A003-P02** A003-G01 → A003-G03

## A006

- **A006-M01** (2026-09-07T00:00:00Z) The Beacon backend currently uses MySQL.
- **A006-M02** (2026-09-07T00:01:00Z) The Beacon backend has now migrated to PostgreSQL; this replaces MySQL.
- **A006-M03** (2026-09-07T00:02:00Z) The Beacon logs remain in object storage.


Candidates:
- **A006-G01** The Beacon logs are in object storage.
- **A006-G02** The Beacon logs migrated to PostgreSQL.
- **A006-G03** The Beacon backend previously used MySQL.
- **A006-G04** The Beacon backend now uses PostgreSQL.

Ordered pairs (source → target):
- **A006-P01** A006-G03 → A006-G04
- **A006-P02** A006-G04 → A006-G03

## A007

- **A007-M01** (2026-09-08T00:00:00Z) The Nimbus report is due on 10 October 2026.
- **A007-M02** (2026-09-08T00:01:00Z) The Nimbus report deadline has been changed to 14 October 2026; the old deadline is cancelled.
- **A007-M03** (2026-09-08T00:02:00Z) The Nimbus report must be submitted as PDF.


Candidates:
- **A007-G01** The previous Nimbus report deadline was 10 October 2026.
- **A007-G02** The Nimbus report submission format is PDF.
- **A007-G03** The current Nimbus report deadline is 14 October 2026.
- **A007-G04** Every Nimbus deadline moved by four days.

Ordered pairs (source → target):
- **A007-P01** A007-G01 → A007-G03
- **A007-P02** A007-G03 → A007-G01

## A008

- **A008-M01** (2026-09-09T00:00:00Z) The Quartz demo will take place in room R-12.
- **A008-M02** (2026-09-09T00:01:00Z) The Quartz demo has moved to room R-18. Do not use R-12.
- **A008-M03** (2026-09-09T00:02:00Z) The Quartz demo still lasts 20 minutes.


Candidates:
- **A008-G01** All Quartz meetings moved to R-18.
- **A008-G02** The current Quartz demo room is R-18.
- **A008-G03** The Quartz demo lasts 20 minutes.
- **A008-G04** The previous Quartz demo room was R-12.

Ordered pairs (source → target):
- **A008-P01** A008-G02 → A008-G04
- **A008-P02** A008-G04 → A008-G02

## A011

- **A011-M01** (2026-09-12T00:00:00Z) Two equally authoritative Orion cache briefs disagree: one requires Redis and the other requires Memcached. Their priority and current validity are unknown.


Candidates:
- **A011-G01** One Orion cache brief requires Redis.
- **A011-G02** The Orion cache definitely requires Redis.
- **A011-G03** Another Orion cache brief requires Memcached.

Ordered pairs (source → target):
- **A011-P01** A011-G01 → A011-G03
- **A011-P02** A011-G03 → A011-G01

## A012

- **A012-M01** (2026-09-13T00:00:00Z) Two equally authoritative Sable report instructions disagree: one requires exactly 8 pages and the other requires exactly 12 pages. Neither is known to supersede the other.


Candidates:
- **A012-G01** The confirmed Sable report required page count is 12 pages.
- **A012-G02** One Sable report instruction requires exactly 8 pages.
- **A012-G03** Another Sable report instruction requires exactly 12 pages.

Ordered pairs (source → target):
- **A012-P01** A012-G02 → A012-G03
- **A012-P02** A012-G03 → A012-G02

## A013

- **A013-M01** (2026-09-14T00:00:00Z) Two equally authoritative Flint transport specifications disagree: one requires MQTT and the other requires AMQP. No precedence rule or revision ordering is available.


Candidates:
- **A013-G01** One Flint transport specification requires MQTT.
- **A013-G02** AMQP supersedes MQTT for Flint.
- **A013-G03** Another Flint transport specification requires AMQP.

Ordered pairs (source → target):
- **A013-P01** A013-G03 → A013-G01
- **A013-P02** A013-G01 → A013-G03

## A016

- **A016-M01** (2026-09-17T00:00:00Z) I generally prefer Python for programming.
- **A016-M02** (2026-09-17T00:01:00Z) For the current Ember assignment, Java is mandatory.


Candidates:
- **A016-G01** The user generally prefers Python for programming.
- **A016-G02** The current Ember assignment requires Java.
- **A016-G03** The user has stopped preferring Python.

Ordered pairs (source → target):
- **A016-P01** A016-G01 → A016-G02
- **A016-P02** A016-G02 → A016-G01

## A017

- **A017-M01** (2026-09-18T00:00:00Z) I generally prefer concise bullet-point summaries.
- **A017-M02** (2026-09-18T00:01:00Z) The current Opal assessment requires a continuous-prose report with no bullet lists.


Candidates:
- **A017-G01** The user generally prefers concise bullet-point summaries.
- **A017-G02** The current Opal assessment requires continuous prose without bullet lists.
- **A017-G03** The user now dislikes bullet-point summaries.

Ordered pairs (source → target):
- **A017-P01** A017-G01 → A017-G02
- **A017-P02** A017-G02 → A017-G01

## A018

- **A018-M01** (2026-09-19T00:00:00Z) I generally use APA citations for my own notes.
- **A018-M02** (2026-09-19T00:01:00Z) The current Iris paper submission requires IEEE citations.


Candidates:
- **A018-G01** All personal notes must now use IEEE.
- **A018-G02** The current Iris paper submission requires IEEE citations.
- **A018-G03** The user generally uses APA citations for personal notes.

Ordered pairs (source → target):
- **A018-P01** A018-G02 → A018-G03
- **A018-P02** A018-G03 → A018-G02
