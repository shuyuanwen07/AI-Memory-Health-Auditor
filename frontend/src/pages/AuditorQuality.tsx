import { Alert, Button, Card, Modal, Skeleton, Table, Tag } from 'antd';
import { useCallback, useEffect, useId, useRef, useState } from 'react';
import { UIPanel, UISummary } from '../components/ui';
import { api } from '../services/api';
import { friendlyText } from '../services/display';
export interface QualityMetric {percentage:number|null;numerator:number;denominator:number;interval_95:[number,number]|null}
export interface ScenarioAnalysis {labelled_histories:number;resamples:number;notice:string;metrics:Record<string,{interval_95:[number,number]|null;valid_resamples:number}>}
export interface QualityMethod {
  evidence_integrity?:{expected_questions:number;eligible_questions:number;excluded_questions:number;discarded_review_labels:number;reasons:Record<string,number>};
  reviewed_difference_count?:number;reviewed_examples?:Array<{run_id:string;question:string;answer:string;automated_passed:boolean|null;human_passed:boolean;assessment_reason:string;review_note:string|null;review_role:string;kind:string}>;
  scenario_analysis?:ScenarioAnalysis;method:string;label:string;completed_runs:number;scenario_count:number;run_ids:string[];
  evaluated:number;resolved_reference_count:number;adjudicated_reference_count:number;reference_only_count:number;
  accuracy:QualityMetric;failure_precision:QualityMetric;failure_recall_including_abstentions:QualityMetric;review_coverage:QualityMetric;
  labelled_abstention_rate:QualityMetric;confusion:{true_positive:number;false_positive:number;false_negative:number;true_negative:number};
}
export interface QualityReport {evidence_integrity?:{expected_questions:number;eligible_questions:number;excluded_questions:number;discarded_review_labels:number;reasons:Record<string,number>};evaluated:number;decided:number;uncertain:number;resolved_reference_count:number;double_reviewed_count:number;completed_runs:number;scenario_count:number;evidence_status:string;notice:string;accuracy:QualityMetric;failure_precision:QualityMetric;failure_recall:QualityMetric;false_positive_rate:QualityMetric;review_coverage:QualityMetric;decided_reference_count:number;labelled_abstention_rate:QualityMetric;failure_classification_accuracy:QualityMetric;failure_detection_and_classification_recall:QualityMetric;scenario_analysis?:ScenarioAnalysis;adjudicated_reference_count?:number;reference_only_count?:number;failure_recall_including_abstentions?:QualityMetric;by_method?:QualityMethod[];method_comparison_notice?:string;review_queue:Array<{run_id:string;model:string;created_at:string;unreviewed:number;independent_pending?:number;adjudication_pending?:number}>}
const qualityMetrics = [['accuracy','Reference agreement','How often the auditor’s pass or fail decision agrees with a saved reference label.'],['failure_precision','Reference-supported failures','Of the answers flagged as failures, how many do saved reference labels also mark as failures?'],['failure_recall','Reference-labelled failures detected','Of reference-labelled failures with a decided assessment, how many did the auditor catch?'],['false_positive_rate','False alarm rate','How often the auditor flags an answer that a saved reference label marks as a pass. Lower is better.'],['failure_classification_accuracy','Failure category accuracy','When both the auditor and reference label identify a failure, how often does the auditor identify the same problem category?'],['failure_detection_and_classification_recall','Failures found with correct category','Of reference-labelled failures with known categories, how many were detected and correctly explained?']] as const;
export function AuditorQualityPage() {
  const [report,setReport]=useState<QualityReport|null>(null);
  const [busy,setBusy]=useState(false);
  const [error,setError]=useState('');
  const [selectedMethod,setSelectedMethod]=useState<string|null>(null);
  const requestVersion=useRef(0);
  const load=useCallback(async()=>{
    const version=++requestVersion.current;
    setBusy(true);setError('');
    try{const next=await api.auditorQuality();if(version===requestVersion.current)setReport(next);}
    catch(cause){if(version===requestVersion.current)setError(cause instanceof Error?cause.message:'Quality evidence could not be loaded.');}
    finally{if(version===requestVersion.current)setBusy(false);}
  },[]);
  useEffect(()=>{void load();return()=>{++requestVersion.current;};},[load]);
  useEffect(()=>{
    // Returning from blind review immediately reflects persisted labels.
    const refresh=()=>{if(document.visibilityState==='visible')void load();};
    window.addEventListener('focus',refresh);document.addEventListener('visibilitychange',refresh);
    return()=>{window.removeEventListener('focus',refresh);document.removeEventListener('visibilitychange',refresh);};
  },[load]);
  return <main className="page"><Card title="Auditor reliability" extra={<Button onClick={load} loading={busy}>Refresh evidence</Button>}>
    <p>This page compares the auditor’s decisions with saved reference labels. To see how well a model answered, open its audit report.</p><UIPanel><UISummary>How to read these results</UISummary><p>Pass means the answer meets the test’s requirements. Fail means a requirement was missed. Uncertain means the auditor could not make a reliable decision; it does not count as a pass.</p><p>Not measured means there is not enough reviewed evidence to calculate a score. It is different from 0%. Each score shows the number of reference labels it uses. Small samples can produce misleading percentages.</p><p>Independent reviews are completed separately, without seeing the auditor’s decision. An adjudicated reference is the final decision after at least two independent reviews. Statistical intervals describe uncertainty in the available sample; they do not prove performance on every future conversation.</p></UIPanel>
    {error&&<Alert type="error" title={error} showIcon/>}
    {!report&&busy&&<section role="status" aria-label="Loading review evidence"><p>Loading saved audits and reference labels…</p><Skeleton active paragraph={{rows:4}}/></section>}
    {report&&<>
      {report.evidence_integrity&&(report.evidence_integrity.excluded_questions>0||report.evidence_integrity.discarded_review_labels>0)&&<Alert type="warning" showIcon role="alert" aria-label="Saved evidence integrity" title="Some saved evidence could not be used" description={<><p>{report.evidence_integrity.eligible_questions} of {report.evidence_integrity.expected_questions} saved questions have usable answer and assessment records. {report.evidence_integrity.excluded_questions} excluded; {report.evidence_integrity.discarded_review_labels} review labels belonged to a different audit.</p><p>Excluded records count as missing evidence, not model failures or passes. Review coverage includes all saved questions.</p>{Object.entries(report.evidence_integrity.reasons).map(([key,count])=><Tag key={key}>{({multiple_assessments:'Conflicting assessments',missing_assessment:'Assessment missing',missing_answer:'Answer missing',answer_belongs_elsewhere:'Answer belongs to another question or audit'} as Record<string,string>)[key]||'Unusable evidence'}: {count}</Tag>)}</>}/>}

      <Alert type={report.adjudicated_reference_count?'info':'warning'} title={report.resolved_reference_count?(report.adjudicated_reference_count ? 'Independent review results are available. Check the sample size before drawing conclusions.' : 'Some answers have reference labels. Independent validation is still incomplete.'):'Independent reviews are needed before the auditor’s accuracy can be measured.'} showIcon/>
      <section aria-label="Review evidence and next step" style={{marginTop:16,marginBottom:16}}>
        <p><b>{report.decided_reference_count} answers can be checked for pass/fail agreement.</b> Each needs a saved reference label and a clear automated decision.</p>
        {report.labelled_abstention_rate.numerator>0&&<p>{report.labelled_abstention_rate.numerator} reviewed answers have an uncertain automated result. They count in the uncertainty analysis, but cannot measure pass/fail agreement.</p>}
        <p>{report.adjudicated_reference_count??0} references adjudicated from independent reviews · {report.reference_only_count??report.resolved_reference_count} other reference labels. Ordinary reference labels do not establish independent validation.</p>
        <Button href="#independent-review-queue">Go to independent reviews</Button>
      </section>
      <p><Tag>{report.completed_runs} completed audits</Tag><Tag>{report.scenario_count} source histories</Tag><Tag>{report.resolved_reference_count}/{report.evidence_integrity?.expected_questions??report.evaluated} resolved references</Tag><Tag>{report.double_reviewed_count} double-reviewed answers</Tag><Tag>{report.uncertain} uncertain assessments</Tag></p>

      <ReliabilityOverviewChart report={report}/>
      <p>Saved reference labels may be assisted or non-independent. Check their source and review process before interpreting agreement or failure-detection percentages.</p>
      <UIPanel><UISummary>Score definitions, intervals & evidence limits</UISummary>
        {qualityMetrics.map(([key,label,explanation])=><p key={key}><b>{label}:</b> {explanation} {report[key].interval_95?`95% descriptive interval: ${formatInterval(report[key].interval_95)}.`:'Interval not measured.'}</p>)}
        <p>{report.notice}</p><p>Reviewer identities and independence are supplied attestations, not verified by this application. Related questions from the same source history can have similar outcomes; use history-level uncertainty when comparing results.</p>
      </UIPanel>
      {report.failure_recall_including_abstentions&&<p><b>Reference-labelled failure detection, including uncertain answers: {formatMetric(report.failure_recall_including_abstentions)}</b> · {report.failure_recall_including_abstentions.numerator}/{report.failure_recall_including_abstentions.denominator} reference-labelled failures detected. These labels may be assisted or non-independent; use the counts above to judge their provenance. Uncertain answers remain in this denominator.</p>}
      {report.scenario_analysis&&<section aria-label="Scenario-level uncertainty">
        <h2>Uncertainty across source histories</h2>
        <p>{report.scenario_analysis.labelled_histories} histories with resolved reference labels · {report.scenario_analysis.resamples} complete-history resamples.</p>
        <p>{report.scenario_analysis.notice}</p>
        <p>Decision accuracy interval: {formatInterval(report.scenario_analysis.metrics.accuracy?.interval_95)} · Failure detection interval (including uncertain answers): {formatInterval(report.scenario_analysis.metrics.failure_recall_including_abstentions?.interval_95)}</p>
      </section>}
      {!!report.by_method?.length&&<section aria-label="Reliability by audit method">
        <h2>Where each audit method makes mistakes</h2>
        <p>{report.method_comparison_notice}</p>
        <ReliabilityMethodChart methods={report.by_method.filter(method=>method.method!=="custom")}/>
        <Table rowKey="method" dataSource={report.by_method} pagination={false} scroll={{x:900}} columns={[
          {title:'Audit method',dataIndex:'label'},
          {title:'Reference labels',render:(_,row:QualityMethod)=>`${row.resolved_reference_count}/${row.evidence_integrity?.expected_questions??row.evaluated}`},
          {title:'Adjudicated references',dataIndex:'adjudicated_reference_count'},
          {title:'Decision accuracy',render:(_,row:QualityMethod)=>formatMetric(row.accuracy)},
          {title:'Reference-supported failures',render:(_,row:QualityMethod)=>formatMetric(row.failure_precision)},
          {title:'Failures detected (including uncertain)',render:(_,row:QualityMethod)=>formatMetric(row.failure_recall_including_abstentions)},
          {title:'Review differences',render:(_,row:QualityMethod)=><Button onClick={()=>setSelectedMethod(row.method)}>Inspect {row.reviewed_difference_count??0} cases</Button>},
          {title:'Inspect audits',render:(_,row:QualityMethod)=><a href={`/audits/${row.run_ids[0]}`}>Latest of {row.completed_runs} audits</a>},
        ]}/>
      </section>}
      <Modal title="Reference-labelled assessment differences" open={selectedMethod!==null} onCancel={()=>setSelectedMethod(null)} footer={<Button onClick={()=>setSelectedMethod(null)}>Close</Button>} width={800}>
        {(()=>{
          const method=report.by_method?.find(row=>row.method===selectedMethod);
          const examples=method?.reviewed_examples??[];
          return <><p>{method?.label}</p><p>Showing {examples.length} of {method?.reviewed_difference_count??0} reviewed differences. Reference labels are not automatically independent validation.</p>
            {!examples.length&&<p>No reviewed differences are available. This does not establish agreement on unreviewed answers.</p>}
            {examples.map((example,index)=><Card key={`${example.run_id}:${index}`} title={`Case ${index+1} · ${{false_alarm:'False alarm',missed_failure:'Missed failure',uncertain:'Uncertain assessment'}[example.kind]??example.kind}`} style={{marginBottom:16}}>
              <p><b>Question:</b> {example.question}</p><p><b>Target answer:</b> {example.answer}</p>
              <p><b>Automated assessment:</b> {example.automated_passed===null?'Uncertain':example.automated_passed?'Pass':'Fail'} · <b>Saved reference label:</b> {example.human_passed?'Pass':'Fail'} · {example.review_role==='adjudication'?'Adjudicated reference':'Single reference'}</p>
              <p><b>Assessment reason:</b> {friendlyText(example.assessment_reason)}</p>{example.review_note&&<p><b>Review note:</b> {example.review_note}</p>}
              <a href={`/audits/${example.run_id}`}>Inspect the full audit evidence →</a>
            </Card>)}
          </>;
        })()}
      </Modal>
      <h2 id="independent-review-queue" style={{scrollMarginTop:100}}>Independent review queue</h2><p>Start a blind review to judge the answer before seeing the auditor’s decision or other reviewers’ labels. Two people should review independently, then a final reviewer resolves their differences. Submit your own judgement; an AI suggestion does not count as an independent human review. Reviewer identity and independence are attestations, not verified by the app. Share the direct blind-review link with reviewers before they view automated reports.</p>
      <Table rowKey="run_id" dataSource={report.review_queue} pagination={{pageSize:10}} scroll={{x:800}} locale={{emptyText:'No completed answers are waiting for independent review.'}} columns={[{title:'Review batch',render:(_,row)=>new Date(row.created_at).toLocaleString()},{title:'Awaiting reference',dataIndex:'unreviewed'},{title:'Needs two independent reviews',dataIndex:'independent_pending'},{title:'Needs a final decision',dataIndex:'adjudication_pending'},{title:'Review',fixed:'right',width:150,render:(_,row)=><a href={`/blind-review/${row.run_id}`}>Start blind review →</a>}]}/>
    </>}
  </Card></main>;
}

function ReliabilityOverviewChart({report}:{report:QualityReport}) {
  const titleId=useId(),descriptionId=useId();
  const lines=[['Reference','agreement'],['Reference-supported','failures'],['Reference-labelled','failures detected'],['False alarm','rate ↓'],['Failure category','accuracy'],['Failures found with','correct category']];
  return <figure aria-label="Auditor reliability metrics" style={{margin:'20px 0'}}>
    <small className="validity-scroll-hint">Scroll horizontally to compare measures.</small>
    <div role="region" aria-label="Scrollable reliability overview" tabIndex={0} style={{overflowX:'auto'}}>
      <svg viewBox="0 0 960 355" style={{width:'100%',minWidth:850}} role="img" aria-labelledby={titleId} aria-describedby={descriptionId}>
        <title id={titleId}>Auditor reliability overview</title>
        <desc id={descriptionId}>{qualityMetrics.map(([key,label])=>`${label}: ${formatMetric(report[key])}; ${report[key].numerator} of ${report[key].denominator} eligible reference labels.`).join(' ')} False alarm rate is lower when better. Each measure uses its own denominator.</desc>
        {[0,25,50,75,100].map(value=><g key={value}><line x1={50} x2={950} y1={260-value*2} y2={260-value*2} stroke="#dbe4ea"/><text x={43} y={265-value*2} textAnchor="end" fontSize={12} fill="#536b7e">{value}%</text></g>)}
        {qualityMetrics.map(([key,label],index)=>{
          const metric=report[key],centre=125+index*150;
          return <g key={key}><title>{label}: {formatMetric(metric)} · {metric.numerator}/{metric.denominator} eligible reference labels{metric.interval_95?` · 95% descriptive interval ${formatInterval(metric.interval_95)}`:''}</title>
            {metric.percentage!==null&&<rect x={centre-24} y={260-metric.percentage*2} width={48} height={metric.percentage*2} rx={3} fill={key==='false_positive_rate'?'#b7791f':'#087ea4'}/>}
            <text x={centre} y={metric.percentage===null?245:250-metric.percentage*2} textAnchor="middle" fontSize={12} fill="#23475e">{formatMetric(metric)}</text>
            <text x={centre} y={282} textAnchor="middle" fontSize={13} fill="#23475e">{lines[index].map((line,i)=><tspan key={line} x={centre} dy={i?16:0}>{line}</tspan>)}</text>
            <text x={centre} y={326} textAnchor="middle" fontSize={12} fill="#536b7e">{metric.numerator}/{metric.denominator} eligible reviews</text>
          </g>;
        })}
      </svg>
    </div>
    <figcaption>Scale: 0–100%. Higher is better except false alarms (↓). Each measure uses its own eligible reviews. Not measured means insufficient evidence; it is different from 0%.</figcaption>
  </figure>;
}

function formatMetric(metric:QualityMetric){return metric.percentage===null?'Not measured':`${metric.percentage.toFixed(1)}%`;}
const methodColours:Record<string,string>={rules:'#087ea4',model_generation:'#16806a',hybrid:'#b7791f',custom:'#7952b3'};
function ReliabilityMethodChart({methods}:{methods:QualityMethod[]}) {
  if(!methods.length)return <p>No declared audit-method comparisons have completed yet.</p>;
  const outcomes=[{key:'correct',label:'Confirmed decisions'},{key:'false_positive',label:'False alarms'},
    {key:'false_negative',label:'Missed failures'},{key:'uncertain',label:'Uncertain answers'}] as const;
  return <figure className="reliability-method-chart" aria-label="Reference-labelled outcomes by audit method">
    <div className="reliability-legend">{methods.map(method=><span key={method.method}><i style={{background:methodColours[method.method]??methodColours.custom}} aria-hidden="true"/>{method.label}</span>)}</div>
    <div className="reliability-plot">{outcomes.map(outcome=><div className="reliability-outcome" key={outcome.key}>
      <div className="reliability-columns">{methods.map(method=>{
        const count=outcome.key==='correct'?method.confusion.true_positive+method.confusion.true_negative:
          outcome.key==='uncertain'?method.labelled_abstention_rate.numerator:method.confusion[outcome.key];
        const value=method.resolved_reference_count?count*100/method.resolved_reference_count:null;
        return <div key={method.method} className="reliability-column" title={`${method.label}: ${value===null?'Not measured':`${count}/${method.resolved_reference_count} (${value.toFixed(1)}%)`}`}>
          <span className="reliability-value">{value===null?'—':`${value.toFixed(1)}%`}</span>
          <div className="reliability-track"><div style={{height:`${value??0}%`,background:methodColours[method.method]??methodColours.custom}}/></div>
        </div>;
      })}</div><b>{outcome.label}</b>
    </div>)}</div>
    <figcaption>Scale: 0–100%. Each column is a share of that method’s resolved reference labels; — means no references. False alarms are reference-pass answers flagged as failures. Missed failures are reference-fail answers marked as passing; uncertain answers are separate. These reference labels may be assisted or non-independent. Different review coverage can change this comparison.</figcaption>
  </figure>;
}

function formatInterval(value:[number,number]|null|undefined){return value?`${value[0]}–${value[1]}%`:'Not measured';}
