import { useEffect, useState } from 'react';
import { Progress, Tag } from 'antd';

type Counts = { matched_references: number; full: number; partial: number; none: number; unresolved: number; unmatched_prior_references: number };
type Summary = { format: string; complete_29_histories: Counts; including_partial_observed_output: Counts; review_provenance: string; source_sha256: string };

function valid(c: Counts | undefined): c is Counts {
  return !!c && [c.matched_references, c.full, c.partial, c.none, c.unresolved, c.unmatched_prior_references]
    .every(x => Number.isInteger(x) && x >= 0) && c.matched_references > 0 && c.full + c.partial + c.none + c.unresolved === c.matched_references;
}

export function Ac1FullnessResults() {
  const [summary, setSummary] = useState<Summary | null>(null);
  useEffect(() => {
    let active = true;
    fetch('/reports/ac1-reference-fullness-summary-v1.json', { cache: 'no-store' }).then(r => r.ok ? r.json() : null)
      .then((s: Summary | null) => { if (active && s?.format === 'ac1-fullness-public-summary-v1' && valid(s.complete_29_histories) && valid(s.including_partial_observed_output) && typeof s.review_provenance === 'string') setSummary(s); })
      .catch(() => undefined);
    return () => { active = false; };
  }, []);
  if (!summary) return null;
  const p = summary.complete_29_histories, s = summary.including_partial_observed_output;
  return <section aria-label="AC1 reference completeness review" style={{ marginTop: 20 }}>
    <h3>Reference completeness review <Tag>29 complete histories</Tag></h3>
    <p><b>{p.full}/{p.matched_references}</b> mapped reference facts fully covered</p>
    <Progress percent={p.full / p.matched_references * 100} showInfo={false} strokeColor="#23836f" />
    <p>Full {p.full} · Partial {p.partial} · None {p.none} · Unresolved {p.unresolved}</p>
    <p>Including observed partial history: {s.full} full · {s.partial} partial · {s.unresolved} unresolved / {s.matched_references} mapped</p>
    <small>{p.unmatched_prior_references} other references had no common mapping and were not independently adjudicated. H04 missing output remains unknown; the reference list is not exhaustive. {summary.review_provenance}</small>
    <details><summary>Evidence</summary><p>Fullness summary SHA-256: {summary.source_sha256}</p></details>
  </section>;
}
