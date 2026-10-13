import {OperationChart} from './AssessorOperationCharts';
import {generatorName} from './GeneratorQualityCharts';
import {comparisonColours} from '../services/chartColours';
import type {GeneratorComparisonBatch,GeneratorUsage} from '../types/domain';

export function GeneratorUsageCharts({entries}:{entries:GeneratorComparisonBatch['entries']}){
  const rows=entries.map((entry,index)=>({name:generatorName(entry),colour:comparisonColours[index%comparisonColours.length],usage:entry.usage}));
  const chart=(title:string,unit:string,value:(usage:GeneratorUsage)=>number|null,coverage:(usage:GeneratorUsage)=>string)=>
    <OperationChart title={title} unit={unit} subject="generator" rows={rows.map(row=>({name:row.name,colour:row.colour,
      value:row.usage?value(row.usage):null,coverage:row.usage?coverage(row.usage):'No receipts'}))}/>;
  return <section aria-label="Recorded generation effort"><h2>Generation time & usage</h2>
    <div className="reliability-legend">{rows.map((row,index)=><span key={index}><i style={{background:row.colour}}/>{row.name}</span>)}</div>
    <div className="visual-grid">
      {chart('Recorded generation time','s',usage=>usage.observed_elapsed_ms==null?null:usage.observed_elapsed_ms/1000,
        usage=>`${usage.timed_invocations}/${usage.recorded_invocations} timed${usage.failed_http_attempts?` · ${usage.failed_http_attempts} failed`:''}${usage.unfinished_operations?' · unfinished':''}`)}
      {chart('Reported generation credits','credits',usage=>usage.observed_cost_credits,
        usage=>`${usage.cost_reported_invocations}/${usage.recorded_invocations} reported${usage.complete_cost_coverage?'':' · partial'}`)}
      {chart('Recorded HTTP attempts','calls',usage=>usage.request_attempts,
        usage=>`${usage.receipt_count}/${usage.recorded_invocations} receipts${usage.failed_http_attempts==null?'':` · ${usage.failed_http_attempts} failed`}`)}
      {chart('Reported generation tokens','tokens',usage=>usage.observed_total_tokens,
        usage=>`${usage.token_reported_invocations}/${usage.recorded_invocations} reported`)}
    </div>
    <p>Includes recorded suite generation, semantic duplicate checks, failures, repairs and retries. Question replacements, target answers and human review are separate. Missing receipts stay unknown; reported credits are not a full invoice.</p>
  </section>;
}
