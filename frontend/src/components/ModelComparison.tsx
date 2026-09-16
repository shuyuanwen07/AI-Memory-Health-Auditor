import type { AuditResult, Dimension } from '../types/domain';

type ComparisonRun = { label: string; result: AuditResult };

const dimensions: Array<{ key: Dimension; label: string }> = [
  { key: 'accuracy', label: 'Accuracy' },
  { key: 'freshness', label: 'Freshness' },
  { key: 'conflict_resolution', label: 'Conflict Resolution' },
  { key: 'appropriate_use', label: 'Appropriate Use' },
];

function score(result: AuditResult, dimension?: Dimension) {
  const value = dimension ? result.dimensions.find((item) => item.dimension === dimension)?.percentage : result.overall_score;
  return value === null || value === undefined ? 'Not tested' : `${value.toLocaleString(undefined, { maximumFractionDigits: 1 })}%`;
}

/** All rows use the same confirmed ground truth and settings for a fair comparison. */
export function ModelComparison({ runs }: { runs: ComparisonRun[] }) {
  return <section className="model-comparison" aria-label="Model comparison results">
    <h2>Model Comparison</h2>
    <p>All models were tested against the same confirmed ground truth and audit settings.</p>
    <div className="comparison-scroll"><table>
      <thead><tr><th>Model</th><th>Overall</th>{dimensions.map((item) => <th key={item.key}>{item.label}</th>)}<th>Tests passed</th></tr></thead>
      <tbody>{runs.map(({ label, result }) => <tr key={result.run_id}><th scope="row">{label}</th><td><b>{score(result)}</b></td>{dimensions.map((item) => <td key={item.key}>{score(result, item.key)}</td>)}<td>{result.tests_passed} / {result.tests_total}</td></tr>)}</tbody>
    </table></div>
  </section>;
}
