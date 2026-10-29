import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Alert, Button, Card, Progress, Select, Skeleton, Tag } from 'antd';
import { FourStrategyComparisonSection } from '../components/FourStrategyComparison';
import { CompactExperimentResults } from '../components/CompactExperimentResults';
import { FourStrategyHumanResults } from '../components/FourStrategyHumanResults';
import { Ac3GroundingSummary } from '../components/Ac3GroundingSummary';
import { Ac3HeldoutResults } from '../components/Ac3HeldoutResults';
import { Ac3DevelopmentComparison } from '../components/Ac3DevelopmentComparison';
import { Ac1RetrospectiveSummary } from '../components/Ac1RetrospectiveSummary';
import { Ac1ExtractionProgress } from '../components/Ac1ExtractionProgress';
import { Ac3LedgerProgress } from '../components/Ac3LedgerProgress';
import { Ac2GenerationSummary } from '../components/Ac2GenerationSummary';
import { Ac1ReviewedResults } from '../components/Ac1ReviewedResults';
import { Ac2ReviewedResults } from '../components/Ac2ReviewedResults';
import { Ac2AiFollowupSummary } from '../components/Ac2AiFollowupSummary';
import { Ac3StabilitySummary } from '../components/Ac3StabilitySummary';
import { api } from '../services/api';
import { auditDisplayNames, friendlyText, memoryStrategyLabel, modelDisplayName } from '../services/display';
import type { AuditResult, AuditRun, Dimension } from '../types/domain';
import { Bar, BarChart, CartesianGrid, Cell, Legend, Line, LineChart, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import './FinalResultsDashboard.css';

const REPORT_PATH = '/reports/proposal-final-results-v1.json';
const DIMENSIONS: Array<{ id: Dimension; label: string }> = [
  { id: 'accuracy', label: 'Accuracy' },
  { id: 'freshness', label: 'Freshness' },
  { id: 'conflict_resolution', label: 'Conflict resolution' },
  { id: 'appropriate_use', label: 'Appropriate use' },
];
const REPAIR_ROLES = new Set(['diagnostic_intervention', 'adaptive_follow_up', 'repair_comparison']);
const OUTCOME_COLOURS = ['#23836f', '#c24b4b', '#d39b32'];
const STRATEGY_COLOURS = ['#486a9b', '#2d8b78', '#c08335', '#785aa6'];

export function completedAuditOptionLabel(
  run: Pick<AuditRun, 'reproducibility' | 'memory_strategy' | 'model' | 'completed_at' | 'created_at'>,
  displayName: string,
): string {
  const role = run.reproducibility?.study_role ?? 'single completed audit';
  const repair = REPAIR_ROLES.has(role);
  const completedLabel = (run.completed_at ?? run.created_at).slice(0, 16).replace('T', ' ');
  return `${displayName} · ${role.replaceAll('_', ' ')}${repair ? ' · diagnosis / repair / retest' : ''} · ${memoryStrategyLabel(run.memory_strategy)} · ${modelDisplayName(run.model)} · ${completedLabel}`;
}

export function defaultCompletedAuditId(completed: AuditRun[], currentId: string, selectionIsExplicit: boolean): string {
  if (selectionIsExplicit && completed.some(run => run.run_id === currentId)) return currentId;
  return completed[0]?.run_id ?? '';
}

type Accuracy = { correct: number; total: number; accuracy_percent: number | null };
type Repetition = { repetition: number; correct: number; total: number; accuracy_percent: number | null };
type Strategy = {
  id: string; label: string; correct: number; total: number; accuracy_percent: number | null;
  per_repetition: Repetition[]; categories?: Array<{ category: string; correct: number; total: number; accuracy_percent: number | null }>;
};
type MethodReview = {
  label: string; answers: number; resolved: number; passes: number; failures: number; uncertain: number;
  confusion: { tp: number; fp: number; fn: number; tn: number };
};
type DashboardReport = {
  format: 'proposal-final-results-dashboard-v1'; generated_at: string; source_bundle: string; source_revision: string;
  generator: { path: string; sha256: string; version: string };
  source_hashes: Array<{ path: string; sha256: string }>;
  proposal_a: {
    answers: number; histories: number; methods: number; questions_per_method_per_history: number; conditions: number;
    execution_verified: boolean; retrospective_review: {
      resolved: number; total: number; passes: number; failures: number; uncertain: number;
      confusion_vs_adopted_references: { tp: number; fp: number; fn: number; tn: number; decided_total: number };
      per_method: MethodReview[]; review_process: string; review_authorship: string; formal_status: string;
    };
    formal_failure_discovery_rate: number | null; formal_failure_detection_recall: number | null;
    unresolved_items: number; independent_blind_gold: boolean; automatic_initial_counts: { pass: number; fail: number };
    limitations: string[];
  };
  proposal_b: {
    canonical_answers: number; histories: number; repetitions: number; answers_per_policy: number;
    answers_per_history_policy_repeat: number; score_definition: string; policies: Array<{
      id: string; label: string; canonical_answers: number; macro_accuracy_percent: number; population_sd_pp: number;
      passes: number; failures: number; uncertain: number;
      dimensions: Array<{ category: string; correct: number; decided: number; scheduled: number; uncertain: number; accuracy_percent: number | null }>;
      per_repetition: Array<{ repetition: number; macro_accuracy_percent: number; passes: number; failures: number; uncertain: number; dimension_scores: Array<{ category: string; correct: number; decided: number; accuracy_percent: number | null }> }>;
    }>;
    paired_history_macro_deltas_pp: number[]; paired_mean_delta_pp: number; history_bootstrap_interval_pp: [number, number];
    exact_two_sided_sign_p: number; independent_human_results_received: boolean; protocol_sha256: string; limitations: string[];
  };
  proposal_c: {
    archived_compatibility: {
      cases: number; available_cases: number; repetitions: number; target_answers: number; usable_grades: number; policies: Strategy[];
      b_c_ordering_agreement: { agreed_repetitions: number; total_repetitions: number; scope: string };
      upstream_binding: Record<string, unknown>; limitations: string[];
    };
    expanded_v5_v6: {
      source_revision: string; source_sha256: string; v5: { case_count: number; repetitions: number; policies: Strategy[]; categories: unknown[]; interpretation: string };
      v6: { case_count: number; repetitions: number; policies: Strategy[]; categories: Array<{ category: string; case_count: number; per_policy: Strategy[] }>; interpretation: string };
      v6_within_collection_repeat_wins: number; v6_decision_rule: string;
      v6_human_review: { status: string; review_items: number; independent_histories: number };
      v6_operational_diagnostics: { estimated_cost_usd: number; note: string; [key: string]: unknown };
      combined_secondary_summary: string; cross_metric_agreement_claim: false; limitations: string[];
    };
  };
};

type LoadState = 'loading' | 'ready' | 'error' | 'empty';
type AuditState = 'loading' | 'ready' | 'error' | 'empty';

const isRecord = (value: unknown): value is Record<string, unknown> => typeof value === 'object' && value !== null && !Array.isArray(value);
const isText = (value: unknown): value is string => typeof value === 'string' && value.trim().length > 0;
const isCount = (value: unknown): value is number => typeof value === 'number' && Number.isInteger(value) && value >= 0;
const isNumber = (value: unknown): value is number => typeof value === 'number' && Number.isFinite(value);

function isDashboardReport(value: unknown): value is DashboardReport {
  if (!isRecord(value) || value.format !== 'proposal-final-results-dashboard-v1' || !isText(value.generated_at)
      || !isText(value.source_bundle) || !isText(value.source_revision) || !isRecord(value.generator)
      || !isText(value.generator.path) || !/^[a-f0-9]{64}$/i.test(String(value.generator.sha256))
      || !Array.isArray(value.source_hashes) || value.source_hashes.length < 8
      || !value.source_hashes.every(item => isRecord(item) && isText(item.path) && typeof item.sha256 === 'string' && /^[a-f0-9]{64}$/i.test(item.sha256))) return false;
  const a = value.proposal_a, b = value.proposal_b, c = value.proposal_c;
  if (!isRecord(a) || !isRecord(a.retrospective_review) || !isCount(a.answers) || !isCount(a.histories)
      || !isCount(a.methods) || !isCount(a.retrospective_review.resolved) || !isCount(a.retrospective_review.total)
      || !isCount(a.retrospective_review.failures) || !isCount(a.retrospective_review.passes) || !isCount(a.retrospective_review.uncertain)
      || !Array.isArray(a.limitations) || !isRecord(b) || !Array.isArray(b.policies) || b.policies.length !== 2
      || !isNumber(b.paired_mean_delta_pp) || !Array.isArray(b.limitations) || !isRecord(c) || !isRecord(c.archived_compatibility)
      || !Array.isArray(c.archived_compatibility.policies) || c.archived_compatibility.policies.length !== 2
      || !isRecord(c.expanded_v5_v6) || !Array.isArray(c.expanded_v5_v6.limitations)) return false;
  if (a.answers !== 36 || a.retrospective_review.total !== 36 || a.retrospective_review.resolved + a.retrospective_review.uncertain !== 36) return false;
  return true;
}

function percent(value: number | null | undefined, places = 1): string {
  return value === null || value === undefined || !Number.isFinite(value) ? 'Not measured' : `${value.toFixed(places)}%`;
}

function formatAccuracy(item: { correct: number; total: number; accuracy_percent: number | null }, places = 1): string {
  return `${item.correct}/${item.total}${item.accuracy_percent === null ? '' : ` · ${item.accuracy_percent.toFixed(places)}%`}`;
}

function StackedReviewBar({ review }: { review: DashboardReport['proposal_a']['retrospective_review'] }) {
  const { failures, passes, uncertain, total } = review;
  return <figure style={{ margin: '0.8rem 0' }}>
    <div role="img" aria-label={`${failures} failures, ${passes} passes, ${uncertain} uncertain of ${total} answers`} style={{ display: 'flex', height: 18, width: '100%', borderRadius: 9, overflow: 'hidden', background: '#e8edf2' }}>
      <span style={{ width: `${failures / total * 100}%`, background: '#c24b4b' }} />
      <span style={{ width: `${passes / total * 100}%`, background: '#23836f' }} />
      <span style={{ width: `${uncertain / total * 100}%`, background: '#d39b32' }} />
    </div>
    <figcaption><small>Target answers: {failures} failed (red) · {passes} passed (green) · {uncertain} uncertain (amber)</small></figcaption>
  </figure>;
}

function StrategyBars({ strategies, ariaLabel }: { strategies: Array<{ label: string; correct: number; total: number; accuracy_percent: number | null; display_text?: string; population_sd_pp?: number; per_repetition?: Repetition[] }>; ariaLabel: string }) {
  return <figure className="strategy-bars" aria-label={ariaLabel} style={{ margin: '0.9rem 0' }}>
    {strategies.map(strategy => <div className="strategy-bar-row" key={strategy.label} style={{ display: 'grid', gridTemplateColumns: 'minmax(0,1fr) auto', alignItems: 'center', gap: '4px 10px', margin: '0.75rem 0' }}>
      <span className="strategy-bar-label">{strategy.label}</span>
      <strong className="strategy-bar-value">{strategy.display_text ?? formatAccuracy(strategy, 2)}</strong>
      <div role="img" aria-label={`${strategy.label}: ${strategy.display_text ?? formatAccuracy(strategy)}`} style={{ gridColumn: '1 / -1', height: 12, borderRadius: 8, overflow: 'hidden', background: '#e8edf2' }}>
        {strategy.accuracy_percent !== null && <span style={{ display: 'block', width: `${Math.max(0, Math.min(100, strategy.accuracy_percent))}%`, height: '100%', borderRadius: 8, background: '#167d93' }} />}
      </div>
      {strategy.per_repetition && strategy.population_sd_pp !== undefined && <small style={{ gridColumn: '1 / -1', overflowWrap: 'anywhere' }}>
        Repeats: {strategy.per_repetition.map(item => item.accuracy_percent === null ? 'not graded' : `${item.accuracy_percent.toFixed(1)}%`).join(', ')} · SD {strategy.population_sd_pp.toFixed(2)} pp
      </small>}
    </div>)}
    <figcaption><small>Bars show accuracy; labels show either the macro percentage or the correct / denominator count, as appropriate.</small></figcaption>
  </figure>;
}

function AuditOutcomeDonut({ result, failures, uncertain }: { result: AuditResult; failures: number; uncertain: number }) {
  const outcomes = [
    { name: 'Passed', value: result.tests_passed, colour: OUTCOME_COLOURS[0] },
    { name: 'Detected failures', value: failures, colour: OUTCOME_COLOURS[1] },
    { name: 'Awaiting review', value: uncertain, colour: OUTCOME_COLOURS[2] },
  ];
  const chartOutcomes = outcomes.filter(item => item.value > 0);
  const summary = outcomes.map(item => `${item.name}: ${item.value}`).join(', ');
  return <figure className="audit-outcome-chart" aria-label={`Saved audit outcome chart. ${summary}.`}>
    {chartOutcomes.length > 0 ? <div role="img" aria-label={`Donut chart of decided and uncertain audit outcomes. ${summary}.`}>
      <ResponsiveContainer width="100%" height={190}>
        <PieChart>
          <Pie data={chartOutcomes} dataKey="value" nameKey="name" innerRadius="52%" outerRadius="76%" paddingAngle={2} stroke="#fff">
            {chartOutcomes.map(item => <Cell key={item.name} fill={item.colour} />)}
          </Pie>
          <Tooltip formatter={(value, name) => [value, name]} />
        </PieChart>
      </ResponsiveContainer>
    </div> : <p>No assessed outcomes to chart.</p>}
    <ul className="chart-key" aria-label="Saved audit outcome counts">
      {outcomes.map(item => <li key={item.name}><i aria-hidden="true" style={{ backgroundColor: item.colour }} />{item.name}: <b>{item.value}</b></li>)}
    </ul>
    <figcaption><small>Counts include decided passes, detected failures and assessments awaiting review.</small></figcaption>
  </figure>;
}

function AbilityScoreChart({ dimensions }: { dimensions: Array<{ id: Dimension; label: string; score: AuditResult['dimensions'][number] | undefined }> }) {
  const data = dimensions.map(({ label, score }) => ({ label, percentage: score?.percentage ?? null }));
  const summary = dimensions.map(({ label, score }) => `${label}: ${score?.percentage == null ? 'not measured' : `${score.percentage.toFixed(1)}%`}`).join('; ');
  return <figure className="ability-score-chart" aria-label={`Four ability score bar chart. ${summary}`}>
    <div role="img" aria-label={`Horizontal bar chart of the four measured abilities. ${summary}. An absent bar means unmeasured.`}>
      <ResponsiveContainer width="100%" height={205}>
        <BarChart data={data} layout="vertical" margin={{ top: 2, right: 12, bottom: 2, left: 2 }}>
          <CartesianGrid strokeDasharray="3 3" horizontal={false} />
          <XAxis type="number" domain={[0, 100]} tickFormatter={value => `${value}%`} />
          <YAxis type="category" dataKey="label" width={125} tick={{ fontSize: 12 }} />
          <Tooltip formatter={value => value == null ? 'Not measured' : `${Number(value).toFixed(1)}%`} />
          <Bar dataKey="percentage" name="Score" fill="#167d93" isAnimationActive={false}>
            {data.map(row => <Cell key={row.label} fill={row.percentage == null ? '#c7ced6' : '#167d93'} />)}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
    <ul className="ability-score-key" aria-label="Ability score counts">
      {dimensions.map(({ id, label, score }) => <li key={id}>
        <span>{label}</span><b>{score?.percentage == null ? 'Not measured' : `${score.percentage.toFixed(1)}%`}</b>
        <small>{score ? `${score.passed}/${score.total} decided passed` : 'No saved dimension result'}{(score?.uncertain_count ?? 0) > 0 ? ` · ${score?.uncertain_count} uncertain` : ''}</small>
      </li>)}
    </ul>
    <figcaption><small>An absent score means the saved audit has no decided evidence for that ability; it is not a zero.</small></figcaption>
  </figure>;
}

function ProposalOverview({ report }: { report: DashboardReport }) {
  const a = report.proposal_a;
  return <div className="research-summary-grid">
    <Card className="research-summary-card" title="A · Target answer outcomes">
      <StackedReviewBar review={a.retrospective_review} />
      <small>Red shows answers that failed, not Auditor errors.</small><br />
      <small>{a.histories} histories · retrospective, score-exposed review; not independent validation.</small>
    </Card>
  </div>;
}

function AResults({ report }: { report: DashboardReport }) {
  const a = report.proposal_a, review = a.retrospective_review;
  return <Card className="research-summary-card" title="A · Audit-method review" style={{ height: '100%' }}>
    <p><b>{review.resolved}/{review.total} answers resolved</b> · {review.failures} failures · {review.passes} passes · {review.uncertain} uncertain.</p>
    <p>{a.histories} histories × {a.methods} methods × {a.questions_per_method_per_history} prompts.</p>
    <StackedReviewBar review={review} />
    <p><small>AI-assisted, score-exposed retrospective review; not independent blind validation. Formal distinct-failure discovery is unmeasured.</small></p>
    <details>
      <summary>Per-method counts, confusion matrix and limitations</summary>
      <p>Against the adopted retrospective references: TP {review.confusion_vs_adopted_references.tp}, FP {review.confusion_vs_adopted_references.fp}, FN {review.confusion_vs_adopted_references.fn}, TN {review.confusion_vs_adopted_references.tn}, among {review.confusion_vs_adopted_references.decided_total} decided answers. This is not an independent reliability estimate.</p>
      <table><thead><tr><th>Audit method</th><th>Answers</th><th>Resolved</th><th>Pass</th><th>Fail</th><th>Uncertain</th></tr></thead><tbody>
        {review.per_method.map(method => <tr key={method.label}><th scope="row">{method.label}</th><td>{method.answers}</td><td>{method.resolved}</td><td>{method.passes}</td><td>{method.failures}</td><td>{method.uncertain}</td></tr>)}
      </tbody></table>
      <p>{review.review_process}. {review.review_authorship}</p>
      <ul>{a.limitations.map(item => <li key={item}>{item}</li>)}</ul>
    </details>
    <p><a href="/research-results">Open the detailed Proposal A evidence →</a></p>
  </Card>;
}

function BResults({ report }: { report: DashboardReport }) {
  const b = report.proposal_b;
  return <Card className="research-summary-card" title="B · Target-memory policy comparison" style={{ height: '100%' }}>
    <p><b>{b.canonical_answers} answers</b> · {b.histories} related histories · 2 policies × {b.repetitions} repeats.</p>
    <StrategyBars ariaLabel="Proposal B macro accuracy chart" strategies={b.policies.map(policy => ({
      label: policy.label, correct: policy.passes, total: policy.passes + policy.failures + policy.uncertain,
      accuracy_percent: policy.macro_accuracy_percent, display_text: `${policy.macro_accuracy_percent.toFixed(2)}% macro`, population_sd_pp: policy.population_sd_pp,
    }))} />
    <p><b>Pass / fail / uncertain:</b> {b.policies.map(policy => `${policy.label} ${policy.passes}/${policy.failures}/${policy.uncertain}`).join(' · ')}.</p>
    <p><b>Paired history difference:</b> +{b.paired_mean_delta_pp.toFixed(2)} pp. Relationship-priority repeats {b.policies[1].per_repetition.map(item => `${item.macro_accuracy_percent.toFixed(2)}%`).join(', ')} · SD {b.policies[1].population_sd_pp.toFixed(2)} pp.</p>
    <p><small>Macro = unweighted mean of four dimension pass rates; excludes uncertain judgements.</small></p>
    <details>
      <summary>Four ability scores, repeats and paired-history details</summary>
      <p>{b.score_definition}</p>
      <table><thead><tr><th>Policy</th><th>Ability</th><th>Pass / decided</th><th>Scheduled</th><th>Uncertain</th><th>Accuracy</th></tr></thead><tbody>
        {b.policies.flatMap(policy => policy.dimensions.map(dimension => <tr key={`${policy.id}:${dimension.category}`}><th scope="row">{policy.label}</th><td>{dimension.category}</td><td>{dimension.correct}/{dimension.decided}</td><td>{dimension.scheduled}</td><td>{dimension.uncertain}</td><td>{percent(dimension.accuracy_percent, 2)}</td></tr>))}
      </tbody></table>
      <table><thead><tr><th>Repeat</th>{b.policies.map(policy => <th key={policy.id}>{policy.label}</th>)}</tr></thead><tbody>
        {Array.from({ length: b.repetitions }, (_, index) => index + 1).map(repetition => <tr key={repetition}><th scope="row">{repetition}</th>{b.policies.map(policy => {
          const row = policy.per_repetition.find(item => item.repetition === repetition);
          return <td key={policy.id}>{row ? `${row.macro_accuracy_percent.toFixed(2)}% · ${row.passes} pass, ${row.failures} fail, ${row.uncertain} uncertain` : 'Not recorded'}</td>;
        })}</tr>)}
      </tbody></table>
      <p>Paired history deltas: {b.paired_history_macro_deltas_pp.map(value => `${value.toFixed(2)} pp`).join(', ')} · mean +{b.paired_mean_delta_pp.toFixed(2)} pp · descriptive history-bootstrap interval {b.history_bootstrap_interval_pp[0].toFixed(2)} to {b.history_bootstrap_interval_pp[1].toFixed(2)} pp · exact sign-test p={b.exact_two_sided_sign_p.toFixed(2)}.</p>
      <p>Protocol SHA-256: <code>{b.protocol_sha256}</code>. Independent human validation received: {b.independent_human_results_received ? 'yes' : 'no'}.</p>
      <ul>{b.limitations.map(item => <li key={item}>{item}</li>)}</ul>
    </details>
    <p><a href="/research-results">Open the detailed Proposal B results →</a></p>
  </Card>;
}

function CResults({ report }: { report: DashboardReport }) {
  const c = report.proposal_c, archived = c.archived_compatibility, expanded = c.expanded_v5_v6;
  return <Card className="research-summary-card" title="C · LongMemEval comparison" style={{ height: '100%' }}>
    <p><b>{archived.cases}/{archived.available_cases} Oracle cases</b> · {archived.repetitions} repeats · {archived.usable_grades}/{archived.target_answers} usable grades.</p>
    <StrategyBars ariaLabel="Archived Proposal C accuracy chart" strategies={archived.policies} />
    <p><b>Ranking agreed in {archived.b_c_ordering_agreement.agreed_repetitions}/{archived.b_c_ordering_agreement.total_repetitions} repeats.</b> Direction only; absolute scores are not compared.</p>
    <p><small>Selected subset, not the full benchmark; automatic grades are not independently calibrated.</small></p>
    <details>
      <summary>Archived repeats, category results, separate v5/v6 collections and limitations</summary>
      <p>{archived.b_c_ordering_agreement.scope}</p>
      <table><thead><tr><th>Repeat</th>{archived.policies.map(policy => <th key={policy.id}>{policy.label}</th>)}</tr></thead><tbody>
        {Array.from({ length: archived.repetitions }, (_, index) => index + 1).map(repetition => <tr key={repetition}><th scope="row">{repetition}</th>{archived.policies.map(policy => {
          const row = policy.per_repetition.find(item => item.repetition === repetition);
          return <td key={policy.id}>{row ? formatAccuracy(row) : 'Not recorded'}</td>;
        })}</tr>)}
      </tbody></table>
      <table><thead><tr><th>Category</th>{archived.policies.map(policy => <th key={policy.id}>{policy.label}</th>)}</tr></thead><tbody>
        {archived.policies[0].categories?.map((row, index) => <tr key={row.category}><th scope="row">{row.category}</th>{archived.policies.map(policy => <td key={policy.id}>{policy.categories?.[index] ? formatAccuracy(policy.categories[index]) : 'Not reported'}</td>)}</tr>)}
      </tbody></table>
      <h4>Preserved v5 subset · {expanded.v5.case_count} cases</h4>
      <p>{expanded.v5.policies.map(policy => `${policy.label} ${formatAccuracy(policy)}`).join(' · ')}. This is a separate earlier collection.</p>
      <h4>New v6 extension · {expanded.v6.case_count} cases</h4>
      <p>{expanded.v6.policies.map(policy => `${policy.label} ${formatAccuracy(policy)}`).join(' · ')}. Relationship-priority ranked higher in {expanded.v6_within_collection_repeat_wins}/{expanded.v6.repetitions} v6 repeats. This is within-C repeat agreement, not B↔C cross-metric agreement.</p>
      <table><thead><tr><th>v6 category</th>{expanded.v6.policies.map(policy => <th key={policy.id}>{policy.label}</th>)}</tr></thead><tbody>
        {expanded.v6.categories.map(category => <tr key={category.category}><th scope="row">{category.category} · {category.case_count} cases</th>{category.per_policy.map(policy => <td key={policy.id}>{formatAccuracy(policy)}</td>)}</tr>)}
      </tbody></table>
      <p>v6 decision rule: {expanded.v6_decision_rule}</p>
      <p>Human review status: {expanded.v6_human_review.status}; {expanded.v6_human_review.review_items} answer rows from {expanded.v6_human_review.independent_histories} histories.</p>
      <p>v6 cost estimate: US${expanded.v6_operational_diagnostics.estimated_cost_usd.toFixed(3)}. {expanded.v6_operational_diagnostics.note}</p>
      <p>v5/v6 source revision {expanded.source_revision}; source SHA-256 <code>{expanded.source_sha256}</code>. {expanded.combined_secondary_summary}</p>
      <ul>{[...archived.limitations, ...expanded.limitations].map((item, index) => <li key={`${index}:${item}`}>{item}</li>)}</ul>
    </details>
    <p><a href="/expanded-c">Open the detailed Expanded C page →</a></p>
  </Card>;
}

function AuditorValidationStatus({ report }: { report: DashboardReport }) {
  const a = report.proposal_a;
  return <Card title="Auditor validation status">
    <p><b>The A retrospective review is not independent Auditor validation.</b> The A recheck has {a.retrospective_review.resolved}/{a.answers} adopted retrospective labels, but review was AI-assisted after outcome exposure. Six answers remain uncertain and formal failure discovery is unmeasured.</p>
    <p>Target-memory B/C scores measure the tested memory policies; they are not Auditor-accuracy estimates.</p>
    <p><a href="/quality">Open the Auditor reliability and independent-review page →</a></p>
  </Card>;
}

function HumanReviewSummary() {
  const [summary, setSummary] = useState<{ baseline_items: number; agreement: number; uncertain: number; disagreement: number; v7_items: number; v7_both_reviewed: number; additional_fact_disagreements: number } | null>(null);
  useEffect(() => {
    let active = true;
    fetch('/reports/human-review-summary-v1.json', { cache: 'no-store' })
      .then(response => response.ok ? response.json() : null)
      .then(value => {
        const keys = ['baseline_items', 'agreement', 'uncertain', 'disagreement', 'v7_items', 'v7_both_reviewed', 'additional_fact_disagreements'] as const;
        if (active && value?.format === 'human-review-summary-v1' && keys.every(key => Number.isInteger(value[key]) && value[key] >= 0)
            && value.baseline_items === value.agreement + value.uncertain + value.disagreement && value.v7_both_reviewed <= value.v7_items) setSummary(value);
      }).catch(() => { if (active) setSummary(null); });
    return () => { active = false; };
  }, []);
  if (!summary) return null;
  const slices = [
    { name: 'Agreement', value: summary.agreement },
    { name: 'Uncertain', value: summary.uncertain },
    { name: 'Disagreement', value: summary.disagreement },
  ];
  return <Card title="Human review · received" style={{ marginTop: 16 }}>
    <p>{summary.baseline_items} previously reviewed items · user confirmed two different human reviewers</p>
    <div role="img" aria-label={`Review comparison: ${summary.agreement} agree, ${summary.uncertain} uncertain, ${summary.disagreement} disagree`} style={{ width: '100%', height: 190 }}>
      <ResponsiveContainer><PieChart><Pie data={slices} dataKey="value" nameKey="name" innerRadius={48} outerRadius={72}>{slices.map((slice, i) => <Cell key={slice.name} fill={OUTCOME_COLOURS[i]} />)}</Pie><Tooltip /><Legend /></PieChart></ResponsiveContainer>
    </div>
    <p>{summary.agreement} agree · {summary.uncertain} uncertain · {summary.disagreement} disagree</p>
    <p>At this earlier review snapshot, four-strategy answers reviewed by both: {summary.v7_both_reviewed}/{summary.v7_items}.</p>
    <details><summary>Review limitations</summary><p>Agreement is not adjudication. {summary.additional_fact_disagreements} additional-fact entries differ. The user reports independent reviews without prior access to automatic scores; the original files contain conflicting declarations and are preserved. The archived automatic results above are unchanged.</p></details>
  </Card>;
}

function RepairReviewSummary() {
  const [data, setData] = useState<{ conditions: Array<{ name: string; pass: number; total: number }>; paired_original_to_target: { target_only_pass: number; original_only_pass: number } } | null>(null);
  useEffect(() => {
    let active = true;
    fetch('/reports/tutor-repair-human-review-v2.json', { cache: 'no-store' })
      .then(response => response.ok ? response.json() : null)
      .then(value => {
        if (active && value?.format === 'tutor-repair-human-review-public-v1' && Array.isArray(value.conditions)
          && value.conditions.length === 3 && value.conditions.every((r: { pass: number; total: number }) => Number.isInteger(r.pass) && r.pass >= 0 && r.total === 8 && r.pass <= r.total)
          && value.paired_original_to_target && Number.isInteger(value.paired_original_to_target.target_only_pass) && Number.isInteger(value.paired_original_to_target.original_only_pass)) setData(value);
      }).catch(() => { if (active) setData(null); });
    return () => { active = false; };
  }, []);
  if (!data) return null;
  return <Card title="Diagnose → improve → retest" style={{ marginTop: 16 }}>
    <p>Same 8 questions · two reviewers agreed on all 24 answers</p>
    <div role="img" aria-label={data.conditions.map(r => `${r.name}: ${r.pass} of ${r.total} passed`).join('; ')} style={{ width: '100%', height: 200 }}>
      <ResponsiveContainer><BarChart data={data.conditions} layout="vertical" margin={{ left: 12, right: 30 }}><CartesianGrid strokeDasharray="3 3" /><XAxis type="number" domain={[0, 8]} allowDecimals={false} /><YAxis type="category" dataKey="name" width={180} /><Tooltip /><Bar dataKey="pass" name="Passed" fill="#13849a" /></BarChart></ResponsiveContainer>
    </div>
    <p>Improved only: {data.paired_original_to_target.target_only_pass}/8 · original only: {data.paired_original_to_target.original_only_pass}/8</p>
    <p><small>One synthetic history and one run per condition; this does not establish general Auditor accuracy. Review procedure is user-reported; original declarations differ. <a href="/experiments/EXP627CCD21BC1D465996A30FF0E630739B">Open evidence →</a></small></p>
  </Card>;
}

function IntakeConfirmationSummary() {
  const [result, setResult] = useState<{ candidate_count: number; human_confirmed_count: number; relationships_reviewed: number } | null>(null);
  useEffect(() => {
    let active = true;
    fetch('/reports/ac4-intake-confirmation-v1.json', { cache: 'no-store' })
      .then(response => response.ok ? response.json() : null)
      .then(value => {
        if (active && value?.format === 'ac4-intake-confirmation-v1' && Number.isInteger(value.candidate_count)
          && Number.isInteger(value.human_confirmed_count) && value.human_confirmed_count <= value.candidate_count
          && Number.isInteger(value.relationships_reviewed)) setResult(value);
      }).catch(() => { if (active) setResult(null); });
    return () => { active = false; };
  }, []);
  if (!result) return null;
  return <Card title="Memory review · saved" style={{ marginTop: 16 }}>
    <p><b>{result.human_confirmed_count}/{result.candidate_count}</b> memories confirmed · {result.relationships_reviewed} relationships reviewed</p>
    <Progress percent={result.candidate_count ? 100 * result.human_confirmed_count / result.candidate_count : 0} showInfo={false} strokeColor="#13849a" aria-label="Confirmed memory candidates" />
    <p>No target audit had run for this intake when it was confirmed.</p>
    <details><summary>What this means</summary><p>Confirmation records the reviewed decisions; it does not by itself prove extraction completeness or Auditor accuracy.</p></details>
  </Card>;
}

function CategoryPilotSummary() {
  type Result = { correct: number; incorrect: number; unclassified?: number };
  const [pilot, setPilot] = useState<{ development: { original: Result; candidate: Result }; historical_check: { original: Result; candidate: Result } } | null>(null);
  useEffect(() => {
    let active = true;
    fetch('/reports/category-gate-summary-v1.json', { cache: 'no-store' }).then(r => r.ok ? r.json() : null).then(value => {
      const rows = [value?.development?.original, value?.development?.candidate, value?.historical_check?.original, value?.historical_check?.candidate];
      if (active && value?.format === 'category-gate-summary-v1' && value.deployed === false && rows.every(row => row && Number.isInteger(row.correct) && Number.isInteger(row.incorrect) && Number.isInteger(row.unclassified ?? 0) && row.correct >= 0 && row.incorrect >= 0 && (row.unclassified ?? 0) >= 0)) setPilot(value);
    }).catch(() => { if (active) setPilot(null); });
    return () => { active = false; };
  }, []);
  if (!pilot) return null;
  const rows = [
    { name: 'Development · original', ...pilot.development.original },
    { name: 'Development · candidate', ...pilot.development.candidate },
    { name: 'Earlier history · original', ...pilot.historical_check.original },
    { name: 'Earlier history · candidate', ...pilot.historical_check.candidate },
  ].map(row => ({ ...row, unclassified: row.unclassified ?? 0 }));
  return <Card title="Failure category · pilot" style={{ marginTop: 16 }}>
    <Tag color="gold">Candidate not deployed</Tag>
    <div role="img" aria-label={rows.map(r => `${r.name}: ${r.correct} correct, ${r.incorrect} incorrect, ${r.unclassified} unclassified`).join('; ')} style={{ width: '100%', height: 225 }}>
      <ResponsiveContainer><BarChart data={rows} layout="vertical" margin={{ left: 10, right: 24 }}><CartesianGrid strokeDasharray="3 3" /><XAxis type="number" domain={[0, 18]} allowDecimals={false} /><YAxis type="category" dataKey="name" width={180} /><Tooltip /><Legend /><Bar dataKey="correct" stackId="a" name="Correct" fill="#23836f" /><Bar dataKey="incorrect" stackId="a" name="Incorrect" fill="#c24b4b" /><Bar dataKey="unclassified" stackId="a" name="Unclassified" fill="#d39b32" /></BarChart></ResponsiveContainer>
    </div>
    <details><summary>How to interpret this pilot</summary><p>The candidate was developed on the first 13 failures and withheld two categories. On the separate historical example it withheld one correct category. It is not deployed and neither example is a prospective held-out validation.</p></details>
  </Card>;
}

function AcAdjudicationSummary() {
  const [result, setResult] = useState<{ items: number; ac1_candidate_valid: number; ac1_reference_partial: number; ac2_question_uncertain: number } | null>(null);
  const [joint, setJoint] = useState<{ revised_questions: number; valid_judgments: number; original_question_adjudication: { valid: number; invalid: number } } | null>(null);
  useEffect(() => {
    let active = true;
    fetch('/reports/ac1-ac2-confirmation-v1.json', { cache: 'no-store' }).then(r => r.ok ? r.json() : null).then(value => {
      if (active && value?.format === 'ac1-ac2-confirmation-v1' && value.human_confirmation_user_reported === true && value.ai_assisted === true
        && ['items', 'ac1_candidate_valid', 'ac1_reference_partial', 'ac2_question_uncertain'].every(key => Number.isInteger(value[key]) && value[key] >= 0)
        && value.items === value.ac1_candidate_valid + value.ac1_reference_partial + value.ac2_question_uncertain) setResult(value);
    }).catch(() => { if (active) setResult(null); });
    fetch('/reports/ac2-joint-review-summary-v1.json', { cache: 'no-store' }).then(r => r.ok ? r.json() : null).then(value => {
      if (active && value?.format === 'ac2-joint-review-summary-v1' && value.user_confirmed_human_review === true
        && Number.isInteger(value.revised_questions) && Number.isInteger(value.valid_judgments)
        && value.revised_questions >= 0 && value.valid_judgments === value.revised_questions * 3
        && Number.isInteger(value.original_question_adjudication?.valid) && Number.isInteger(value.original_question_adjudication?.invalid)
        && value.original_question_adjudication.valid + value.original_question_adjudication.invalid === value.revised_questions) setJoint(value);
    }).catch(() => { if (active) setJoint(null); });
    return () => { active = false; };
  }, []);
  if (!result) return null;
  const rows = [{ name: 'Candidate valid', value: result.ac1_candidate_valid }, { name: 'Partial coverage', value: result.ac1_reference_partial }, { name: 'Question uncertain', value: result.ac2_question_uncertain }];
  return <Card title="AC1 / AC2 · adjudication" style={{ marginTop: 16 }}>
    <p>{result.items} items · AI-assisted decisions confirmed by user</p>
    <div role="img" aria-label={rows.map(r => `${r.name}: ${r.value}`).join('; ')} style={{ width: '100%', height: 190 }}>
      <ResponsiveContainer><PieChart><Pie data={rows} dataKey="value" nameKey="name" innerRadius={48} outerRadius={72}>{rows.map((row, index) => <Cell key={row.name} fill={OUTCOME_COLOURS[index]} />)}</Pie><Tooltip /><Legend /></PieChart></ResponsiveContainer>
    </div>
    <p>Earlier adjudication: {result.ac1_candidate_valid} candidate valid · {result.ac1_reference_partial} partial · {result.ac2_question_uncertain} original questions uncertain</p>
    {joint && <><p>Later original-question adjudication: {joint.original_question_adjudication.valid} valid · {joint.original_question_adjudication.invalid} invalid.</p><p>Revised questions: {joint.revised_questions}/{joint.revised_questions} jointly reviewed with all three fields marked valid.</p></>}
    <details><summary>Review context</summary><p>The user confirmed the AI-assisted recommendations and later original-question adjudication. The earlier uncertain judgments and original experiments remain preserved. The user reports both reviewers participated; separate independent judgments were not established.</p></details>
  </Card>;
}

function Provenance({ report }: { report: DashboardReport }) {
  return <details style={{ marginTop: 16 }}>
    <summary>Aggregate generation and source-file hashes</summary>
    <p>Generated from the preserved {report.source_bundle} bundle · source revision {report.source_revision}.</p>
    <p>Generator: <code>{report.generator.path}</code> · SHA-256 <code>{report.generator.sha256}</code>.</p>
    <table><thead><tr><th>Source file</th><th>SHA-256</th></tr></thead><tbody>
      {report.source_hashes.map(source => <tr key={source.path}><th scope="row"><code>{source.path}</code></th><td><code>{source.sha256}</code></td></tr>)}
    </tbody></table>
    <p>Report generated <time dateTime={report.generated_at}>{new Date(report.generated_at).toLocaleString()}</time>.</p>
  </details>;
}

function CompletedAuditResults() {
  const [runs, setRuns] = useState<AuditRun[]>([]);
  const [runNames, setRunNames] = useState<Record<string, string>>({});
  const [selectedRunId, setSelectedRunId] = useState('');
  const [auditState, setAuditState] = useState<AuditState>('loading');
  const [auditError, setAuditError] = useState('');
  const [result, setResult] = useState<AuditResult | null>(null);
  const [resultState, setResultState] = useState<AuditState>('empty');
  const [resultError, setResultError] = useState('');
  const [refreshToken, setRefreshToken] = useState(0);
  const selectionIsExplicit = useRef(false);

  const refresh = useCallback(async () => {
    setAuditState('loading'); setAuditError('');
    try {
      const all = await api.audits();
      const completed = all.filter(run => run.status === 'COMPLETED').sort((a, b) =>
        (b.completed_at ?? b.created_at).localeCompare(a.completed_at ?? a.created_at));
      setRuns(completed);
      setRunNames(auditDisplayNames(all));
      setSelectedRunId(current => defaultCompletedAuditId(completed, current, selectionIsExplicit.current));
      setAuditState(completed.length ? 'ready' : 'empty');
      setRefreshToken(value => value + 1);
    } catch (cause) {
      setAuditError(cause instanceof Error ? cause.message : 'Saved completed audit results could not be loaded.');
      setAuditState('error');
    }
  }, []);

  useEffect(() => { void refresh(); }, [refresh]);
  useEffect(() => {
    const onFocus = () => { if (document.visibilityState === 'visible') void refresh(); };
    window.addEventListener('focus', onFocus); document.addEventListener('visibilitychange', onFocus);
    return () => { window.removeEventListener('focus', onFocus); document.removeEventListener('visibilitychange', onFocus); };
  }, [refresh]);

  useEffect(() => {
    if (!selectedRunId) { setResult(null); setResultState('empty'); setResultError(''); return; }
    let current = true;
    setResultState('loading'); setResultError('');
    api.results(selectedRunId).then(value => {
      if (current) { setResult(value); setResultState('ready'); }
    }).catch(cause => {
      if (current) { setResult(null); setResultError(cause instanceof Error ? cause.message : 'The saved assessment could not be loaded.'); setResultState('error'); }
    });
    return () => { current = false; };
  }, [selectedRunId, refreshToken]);

  const selectedRun = useMemo(() => runs.find(run => run.run_id === selectedRunId), [runs, selectedRunId]);
  const failureRows = result?.failures ?? [];
  const uncertainRows = result?.uncertain_answers ?? [];
  const uncertainCount = result?.uncertain_count ?? uncertainRows.length;
  const dimensions = DIMENSIONS.map(dimension => ({
    ...dimension,
    score: result?.dimensions.find(score => score.dimension === dimension.id),
  }));
  const measuredAbilityCount = dimensions.filter(({ score }) => score?.percentage !== null && score !== undefined).length;
  const role = selectedRun?.reproducibility?.study_role;

  return <Card title="Latest completed audit" extra={<Button onClick={() => void refresh()} loading={auditState === 'loading'}>Refresh</Button>}>
    {auditState === 'loading' && <section role="status" aria-label="Loading completed audits"><Skeleton active paragraph={{ rows: 2 }} /></section>}
    {auditState === 'error' && <Alert role="alert" type="warning" showIcon title="Saved completed audits could not be loaded" description={auditError} />}
    {auditState === 'empty' && <p>No completed audits are available yet. Start a memory audit and return here after it completes.</p>}
    {auditState === 'ready' && runs.length > 0 && <>
      <label htmlFor="completed-audit-select"><b>Choose a completed audit</b></label>
      <Select id="completed-audit-select" aria-label="Choose a completed audit" value={selectedRunId} onChange={runId => { selectionIsExplicit.current = true; setSelectedRunId(runId); }} style={{ display: 'block', maxWidth: 720, margin: '0.5rem 0 1rem' }} options={runs.map(run => ({
        value: run.run_id, label: completedAuditOptionLabel(run, runNames[run.run_id]),
      }))} />
      {selectedRun && <p><Tag>{role ? role.replaceAll('_', ' ') : 'single completed audit'}</Tag> {memoryStrategyLabel(selectedRun.memory_strategy)} · {modelDisplayName(selectedRun.model)} · completed {(selectedRun.completed_at ?? selectedRun.created_at).slice(0, 10)}</p>}
      {resultState === 'loading' && <section role="status" aria-label="Loading selected audit result"><Skeleton active paragraph={{ rows: 4 }} /></section>}
      {resultState === 'error' && <Alert role="alert" type="warning" showIcon title="The selected audit result could not be loaded" description={resultError} />}
      {result && selectedRun && <>
        <p><b>{result.tests_passed}/{result.tests_total} passed</b> · {failureRows.length} failed · {uncertainCount} uncertain{result.excluded_evidence_count ? ` · ${result.excluded_evidence_count} excluded` : ''}.</p>
        <div className="audit-result-grid">
          <Card size="small" title="Audit outcomes">
            <AuditOutcomeDonut result={result} failures={failureRows.length} uncertain={uncertainCount} />
          </Card>
          <Card size="small" title="Overall memory health across measured abilities">
            <div className="health-score-value">{result.overall_score === null ? 'Not measured' : percent(result.overall_score)}</div>
            <p>{measuredAbilityCount}/4 abilities measured</p>
          {result.formal_overall_score == null
              ? <small>Formal four-ability score unavailable.</small>
              : <small>All four abilities contribute to this score.</small>}
            <p><small>Saved automated assessments; independent reference review is separate.</small></p>
          </Card>
        </div>
        <Card size="small" title="Scores by ability" style={{ marginTop: 12 }}>
          <AbilityScoreChart dimensions={dimensions} />
        </Card>
        <p style={{ marginTop: 14 }}>Detected failures: {failureRows.length} · Awaiting review: {uncertainRows.length}. Open the audit below for questions and evidence.</p>
        <p style={{ marginTop: 12 }}><a href={`/audits/${selectedRun.run_id}`}>Open full saved audit evidence →</a>
          {selectedRun.experiment_id && <> · <a href={`/experiments/${selectedRun.experiment_id}`}>{REPAIR_ROLES.has(role ?? '') ? 'Open diagnosis / repair experiment' : 'Open experiment group'} →</a></>}
          {selectedRun.reproducibility?.assessment_source_run_id && <> · <a href={`/audits/${selectedRun.reproducibility.assessment_source_run_id}`}>Open original target run →</a></>}
        </p>
      </>}
    </>}
  </Card>;
}

export function FinalResultsDashboard() {
  return <main className="page final-results-dashboard">
    <div className="page-heading">
      <div><h1>Audit and experiment results</h1><p>See the studies and your completed audits in one place.</p></div>
    </div>
    <CompactExperimentResults />
    <section aria-label="Selected completed audit results" className="dashboard-section"><h2>Completed audits</h2><CompletedAuditResults /></section>
    <p className="dashboard-links"><a href="/research-results">Research details</a> · <a href="/experiments">Experiments</a> · <a href="/history">Audit history</a></p>
  </main>;
}
