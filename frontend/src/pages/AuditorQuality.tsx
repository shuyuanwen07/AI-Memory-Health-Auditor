import { Alert, Button, Card, Col, Row, Statistic, Table, Tag } from 'antd';
import { useEffect, useState } from 'react';
import { api } from '../services/api';
export interface QualityMetric {percentage:number|null;numerator:number;denominator:number;interval_95:[number,number]|null}
export interface QualityReport {evaluated:number;decided:number;uncertain:number;resolved_reference_count:number;double_reviewed_count:number;completed_runs:number;scenario_count:number;evidence_status:string;notice:string;accuracy:QualityMetric;failure_precision:QualityMetric;failure_recall:QualityMetric;false_positive_rate:QualityMetric;review_coverage:QualityMetric;decided_reference_count:number;labelled_abstention_rate:QualityMetric;failure_classification_accuracy:QualityMetric;failure_detection_and_classification_recall:QualityMetric;review_queue:Array<{run_id:string;model:string;created_at:string;unreviewed:number}>}
export function AuditorQualityPage() {
  const [report,setReport]=useState<QualityReport|null>(null);
  const [busy,setBusy]=useState(false);
  const [error,setError]=useState('');
  const load=async()=>{setBusy(true);setError('');try{setReport(await api.auditorQuality());}catch(cause){setError(cause instanceof Error?cause.message:'Quality evidence could not be loaded.');}finally{setBusy(false);}};
  useEffect(()=>{void load();},[]);
  return <main className="page"><Card title="Auditor reliability" extra={<Button onClick={load} loading={busy}>Refresh evidence</Button>}>
    <p>This page measures the auditor against human reference labels. Target AI scores are shown separately in audit reports.</p>
    {error&&<Alert type="error" title={error} showIcon/>}
    {report&&<>
      <Alert type={report.resolved_reference_count?'info':'warning'} title={report.resolved_reference_count?'Human reference evidence available — review coverage and uncertainty before drawing conclusions':'Not yet calibrated: there are no resolved human references. Automated checks do not prove assessment accuracy.'} showIcon/>
      <p><Tag>{report.completed_runs} completed audits</Tag><Tag>{report.scenario_count} source histories</Tag><Tag>{report.resolved_reference_count}/{report.evaluated} resolved references</Tag><Tag>{report.double_reviewed_count} double-reviewed answers</Tag><Tag>{report.uncertain} uncertain assessments</Tag></p>
      <Row gutter={[16,16]}>{([['accuracy','Assessment accuracy'],['failure_precision','Reported errors confirmed'],['failure_recall','Human errors detected'],['false_positive_rate','False alarm rate'],['failure_classification_accuracy','Failure category accuracy'],['failure_detection_and_classification_recall','Errors found with correct category']] as const).map(([key,label])=><Col xs={24} md={12} xl={6} key={key}><Card><Statistic title={label} value={report[key].percentage===null?'Not measured':`${report[key].percentage.toFixed(1)}%`}/><p>{report[key].numerator}/{report[key].denominator} eligible labels</p><small>{report[key].interval_95?`95% descriptive interval: ${report[key].interval_95![0]}–${report[key].interval_95![1]}%`:'Independent human labels are required.'}</small></Card></Col>)}</Row>
      <p>{report.decided_reference_count} human references have a decided automated assessment. {report.labelled_abstention_rate.numerator} human-labelled answers remain uncertain and are excluded from decision metrics.</p><p>{report.notice} Intervals here assume independent labelled items; related questions and repeated histories require scenario-level analysis for research claims.</p>
      <h2>Independent review queue</h2><p>Use the dedicated blind-review page before reading the model report. The review endpoint withholds automated verdicts and other reviewers' labels. AI pre-review must never be submitted as a human label.</p>
      <Table rowKey="run_id" dataSource={report.review_queue} pagination={{pageSize:10}} columns={[{title:'Review batch',render:(_,row)=>new Date(row.created_at).toLocaleString()},{title:'Awaiting resolved reference',dataIndex:'unreviewed'},{title:'Review',render:(_,row)=><a href={`/blind-review/${row.run_id}`}>Start blind review →</a>}]}/>
    </>}
  </Card></main>;
}
