# Seven-minute research presentation

The presentation follows the six requested topics in order: introduction,
motivation, contributions, related work, methodology, and results/demonstration.
The closing slide pairs the research limitations with concrete next steps.

Open `Memory-Auditor-Presentation-7min-20261101.pptx`. The 12 slides contain the
four-speaker English script in their **speaker notes**. Each note separates
the spoken script, presenter cues, and references. Only read the spoken script.
There is no separate Word script.

| Speaker | Slides | Content | Planned time |
|---|---|---|---|
| Speaker 1 | 1–3 | Project, motivation, contributions | 1 minute 45 seconds |
| Speaker 2 | 4–6 | Related work, implementation, research design and bias controls | 1 minute 45 seconds |
| Speaker 3 | 7–9 | Question quality, Auditor judgments, four strategies and benchmark results | 1 minute 45 seconds |
| Speaker 4 | 10–12 | Repair evidence, saved-system demonstration, limitations and future work | 1 minute 45 seconds |

Total planned time is seven minutes, including short transitions. Actual time
depends on speaking pace and rehearsal. Preload the three links on slide 11
and use saved results during the demonstration; no model call is required.

## Research interpretation

- The 40 valid current questions include two actual regenerations after review.
  This is development evidence, not first-pass automatic perfection.
- Auditor detection and classification use their separate, explicit denominators.
  The detection-change interval includes zero, and zero observed false positives
  is a selected-sample observation.
- The four-strategy table includes a plain-English explanation of each policy.
  B and C use different models and datasets; the columns cannot establish a
  causal model comparison or a universal best policy.
- LongMemEval is the external benchmark. The displayed C result uses two
  selected, reused cases and three repeats, not an official full-benchmark score.
- The repair result uses the same 16 questions before and after changing the
  writer. The demonstration opens FS02's real saved comparison, whose automatic
  result has four paired questions, one improvement and no regressions.
- Human checks used AI assistance. Six relationship labels remain unresolved.
  Failed runs, missing outputs, disagreements and negative results remain in
  the experiment archives.

The authoring module imports the previous deck's layout/theme and preserves
that file. It builds native editable tables and charts from the recorded
evidence. `presentation-provenance.json` records source hashes, slide topics,
script word counts and planned timings. The original 13-slide deck remains at
`../astra-ac2-ten-completion-20261101/`.
