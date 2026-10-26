# Novice-user acceptance worksheet

**Status:** Prepared for a real walkthrough; no user session has been recorded.
**Purpose:** Check whether a person unfamiliar with Agents or research terminology can complete and understand one audit using the release build. This is a usability check, not a model-quality or research-validity label.

**Team handoff:** The team will supply a real session record later. Leave all observation fields blank until that session takes place. The current new-run default is OpenRouter GPT 6 Luna; record the service and model actually selected. Use only the supplied synthetic conversation, and explain that selecting OpenRouter sends it to that model service before the participant authorises processing.

## Session record

- Session ID / participant pseudonym:
- Date and time:
- Observer:
- Build version / commit:
- Browser and operating system:
- Screen size or viewport:
- Input dataset ID and source permission:
- Synthetic or de-identified data confirmed: Yes / No
- Participant unfamiliar with the Auditor's internal terminology: Yes / No
- Participant consent recorded: Yes / No
- Start time / finish time:
- Saved audit ID:
- UI, JSON and CSV export artifact locations or fingerprints:

Do not collect personal conversation histories for this walkthrough. Use the designated synthetic case. Do not record participant names in the worksheet.

## Observer instructions

1. Give the participant only the task wording below. Do not explain product terms or point to controls before they ask for help.
2. Ask them to say what they are looking for and what they think each result means. Do not confirm whether their interpretation is correct until the task is finished.
3. Record completion, time, navigation errors, terminology questions, misunderstandings, and every observer intervention. Distinguish an interface problem from a model or local-service failure.
4. If a required service is unavailable, record the exact stage and stop dependent tasks. Do not substitute a mock or rule-based result and call the selected-model flow complete.
5. Keep original observations. Do not rewrite the participant's words into a preferred outcome.

## Walkthrough tasks

For each task, mark **Completed unaided**, **Completed with help**, **Not completed**, or **Blocked by service**. Record time, help given, observed difficulty, and the participant's own explanation.

### 1. Import and authorise

> Use the supplied synthetic conversation to start an audit. Tell me what permission you are granting and what data the system will process.

- Outcome:
- Time:
- Help or error:
- Participant's explanation of permission and data use:

### 2. Review candidate memories

> Check the proposed memories against the original conversation. Accept, edit, or reject them as you think appropriate, then confirm the facts the audit should use.

- Outcome:
- Time:
- Did the participant find the complete source wording and later corrections?
- Did they understand that the AI review is advisory and does not confirm facts?
- Help or error:
- Participant's explanation of what “ground truth” means in this workflow:

### 3. Configure and run

> Choose the requested model service, model and run settings, review the generated questions, and start the audit if the questions are supported by the source.

- Outcome:
- Time:
- Did the participant identify the actual provider/model and test budget before running?
- Did they notice unsupported, answer-revealing, ambiguous, or repeated questions?
- Help or service failure:
- Stage and saved run ID if blocked:

### 4. Interpret and inspect evidence

> Explain the overall result and each measured dimension. Open one dimension's evidence and show which source, question, expected behavior, answer, and evaluation support the result. Explain any unmeasured dimension.

- Outcome:
- Time:
- Could the participant open the dimension evidence from the overview using keyboard and pointer?
- Did they distinguish “unmeasured” from a zero score?
- Did they distinguish target memory performance from auditor evaluation accuracy?
- Help or misunderstanding:
- Participant's interpretation, in their own words:

### 5. Reconcile exports

> Export the saved run as JSON and CSV. Find the same run and one answer in each export, then compare its result and evidence with the page.

- Outcome:
- Time:
- Did the participant identify the same run and answer in both exports?
- Differences, missing context, or confusing fields:
- Artifact fingerprints or paths:

## Post-session questions

- What did you think “Agent” meant before using the app? What does it mean now?
- Which result would you trust most, and what evidence supports that trust?
- Was anything shown as a score when you expected it to be unmeasured, or vice versa?
- What would you do next if a model failed or a memory looked wrong?
- Which step was hardest to understand or complete?
- What wording or screen would you change first?

## Observer summary

- Tasks completed unaided:
- Tasks completed with help:
- Tasks not completed or blocked:
- Most consequential misunderstanding:
- Evidence that dashboard and exports describe the same saved run:
- Proposed interface change, tied to an observed event:
- Follow-up owner and status:

Keep the completed worksheet and artifact fingerprints with the release-specific acceptance record. A completed worksheet documents one session only; it does not establish broad usability or replace independent research labels.
