/** Restyle the preserved seven-minute deck in a restrained blue palette.
 * Four speakers, three slides each. Sources and detailed qualifications stay
 * in the notes, separately from the simple-English spoken script.
 */
import fs from 'node:fs/promises';
import path from 'node:path';
import crypto from 'node:crypto';
import {fileURLToPath,pathToFileURL} from 'node:url';

const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'../..');
const runtime=process.env.ARTIFACT_RUNTIME_MODULES??'/Users/y/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules';
const skill=process.env.PRESENTATIONS_SKILL_DIR??'/Users/y/.codex/plugins/cache/openai-primary-runtime/presentations/26.1026.10807/skills/presentations';
const python=process.env.ARTIFACT_PYTHON??'/Users/y/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3';
process.env.RUNTIME_NODE_MODULES=runtime;
const {PresentationFile,FileBlob}=await import(pathToFileURL(path.join(runtime,'@oai/artifact-tool/dist/artifact_tool.mjs')));
const {finalizePresentation,applyPresentationChartFont}=await import(pathToFileURL(path.join(skill,'container_tools/artifact_tool_utils.mjs')));
const outDir=path.join(root,'research/presentation-blue-20261101');
const build=path.join(root,process.env.PRESENTATION_BUILD_DIR??'.presentation-blue-build-20261101');
const inputRel='research/presentation-blue-20261101/Memory-Auditor-Presentation-7min-Blue-20261101.pptx';
const output=path.join(build,'export','validated-value-revision.pptx');
const deliverable=path.join(outDir,'Memory-Auditor-Presentation-7min-Blue-20261101.pptx');
await fs.mkdir(outDir,{recursive:true});await fs.mkdir(build,{recursive:true});await fs.mkdir(path.dirname(output),{recursive:true});
const read=async rel=>JSON.parse(await fs.readFile(path.join(root,rel),'utf8'));
const sha=async file=>crypto.createHash('sha256').update(await fs.readFile(file)).digest('hex');
const ac2Path='frontend/public/reports/ac2-astra-ten-source-v1.json';
const ac3Path='frontend/public/reports/ac3-astra-max-retest-v2.json';
const writerPath='frontend/public/reports/ac2-astra-comparison-v1.json';
const bPath='frontend/public/reports/bc-astra-repeat-retest-v2.json';
const cPath='frontend/public/reports/bc-astra-repeat-retest-v2.json';
const aPath='frontend/public/reports/a-astra-max-retest-v2.json';
const diagnosticPath='frontend/public/reports/ac3-balanced-diagnostic-v1.json';
const diagnosticAnalysisPath='output/proposal-delivery/ac3-balanced-taxonomy-validation-20261102-v1/analysis.json';
const diagnosticReferencePath='output/proposal-delivery/ac3-balanced-taxonomy-validation-20261102-v1/reference-consensus.json';
const diagnosticConfirmationPath='output/proposal-delivery/ac3-balanced-taxonomy-validation-20261102-v1/human-confirmation.json';
const mainReportPath='docs/EXPERIMENT_REPORT_ASTRA_MAX_20261102.md';
const mainReportExpectedSha='09dda6c00e8e4dd2727706f5f584a23b2432a3c639753a7fa848e15afc9b9c54';
const ac2=(await read(ac2Path)).ten_scene_retest;
const ac3=await read(ac3Path);
const diagnostic=await read(diagnosticPath),diagnosticAnalysis=await read(diagnosticAnalysisPath);
const writer=(await read(writerPath)).writer_four_followup;
const a=await read(aPath);
if(ac2.valid!==40||ac2.revised_questions!==2||ac2.review_status!=='human_confirmed'||ac2.execution_check.answers!==40)throw Error('Latest confirmed AC2 evidence changed');
if(!ac3.complete || ac3.provenance.target.reasoning_effort!=='max' || ac3.provenance.candidate_judge.reasoning_effort!=='max' || ac3.candidate.metrics.failure_recall_conservative.numerator!==63 || ac3.candidate.metrics.failure_recall_conservative.denominator!==69 || ac3.cohort.saved_target_answers!==120)throw Error('Astra MAX AC3 cohort changed');
if(writer.before_pass!==12||writer.after_pass!==16||writer.review_status!=='human_confirmed')throw Error('Confirmed repair evidence changed');
const policies=['weak_first_hit','strong_rule_based','scope_aware','temporal_importance'];
const retestPath='frontend/public/reports/bc-astra-repeat-retest-v2.json';
const repeated=await read(retestPath);
if(repeated.format!=='bc-astra-repeat-retest-v2' || repeated.provider!=='openai' || repeated.model!=='gpt-6-astra' || repeated.reasoning_effort!=='max' || repeated.planned_per_strategy!==48 || !['ai_reviewed','human_confirmed'].includes(repeated.review_status))throw Error('Repeated Astra results are not ready');
const currentB=repeated.studies.find(s=>s.id==='B'),currentC=repeated.studies.find(s=>s.id==='C');
if(!currentB || !currentC || [currentB,currentC].some(s=>s.conditions.length!==4 || s.conditions.some(c=>c.planned!==48 || c.saved!==48 || c.reviewed!==48 || c.remaining!==0 || c.errors!==0 || c.pass+c.fail+c.unresolved!==48)))throw Error('Finish all B/C answers and independent reviews before updating the deck');
if(a.review_status!=='human_confirmed' || a.human_confirmation_pending!==false || repeated.review_status!=='human_confirmed' || ac3.human_confirmed!==true)throw Error('Wait for the user-reported human verification records before generating the updated deck');
const reviewLabel=repeated.review_status==='human_confirmed'?'Independently human-verified AI-assisted reviews':`Independent Astra ${repeated.review_reasoning_effort??'high'} review; human confirmation pending`;
const retestScore=(study,key)=>{const row=study.conditions.find(c=>c.strategy===key);return `${row.pass}/48${row.unresolved?`\n${row.unresolved} unresolved`:''}`;};

if(a.reasoning_effort!=='max' || a.answered!==48 || JSON.stringify(a.methods.map(x=>x.candidate_patterns_exposed))!=='[1,1,3]')throw Error('Astra MAX method comparison changed');
if(await sha(path.join(root,mainReportPath))!==mainReportExpectedSha)throw Error('Main report changed after the final source signal');
if(!diagnostic.complete || !diagnostic.human_confirmed || diagnostic.provider!=='openai' || diagnostic.model!=='gpt-6-astra' || diagnostic.reasoning_effort!=='max' || diagnostic.cases!==150 || diagnostic.histories!==30 || !diagnostic.curated_answers || !diagnosticAnalysis.human_confirmed || diagnosticAnalysis.target_model_performance_claim!==false || diagnosticAnalysis.paired_counts.identical_prediction!==150)throw Error('Balanced diagnostic is not the final verified150-case result');
const diagnosticCategories=[['accuracy','Accuracy'],['freshness','Freshness'],['conflict_resolution','Conflict resolution'],['appropriate_use','Appropriate use']];
for(const arm of ['original','revised']){
 const result=diagnosticAnalysis[arm];
 if(result.metrics.joint_detection_and_correct_category.numerator!==120 || result.metrics.joint_detection_and_correct_category.denominator!==120 || result.metrics.false_positive_rate_all_reference_passes.numerator!==0 || result.metrics.false_positive_rate_all_reference_passes.denominator!==30 || result.metrics.decided_coverage.numerator!==150 || result.metrics.decided_coverage.denominator!==150)throw Error('Balanced diagnostic metrics changed');
 for(const [key] of diagnosticCategories){const ratio=result.per_category[key].joint_detection_and_correct_category;if(ratio.numerator!==30||ratio.denominator!==30)throw Error('Actual agreed category coverage changed');}
 if(JSON.stringify(diagnostic.analysis[arm].metrics)!==JSON.stringify(result.metrics))throw Error('Dashboard and full diagnostic analysis differ');
}
const countRatio=r=>`${r.numerator}/${r.denominator}`;

const speech=[
  "Do you remember me? Our research asks whether evidence-based auditing can identify AI memory failures and guide improvements. An incorrect answer is the starting point. We inspect the evidence to understand what may have gone wrong, then test whether a targeted change helps. We present our methods, findings and limits.",
  "Remembering information does not guarantee using it correctly. We study four abilities: recalling a fact, following an update, handling conflicting records, and applying information in the right context. For example, a personal Python preference should not override a Java assignment. A wrong answer can come from missing memory, poor retrieval, or incorrect reasoning. Developers need evidence to locate the problem.",
  "Our research follows a cycle. First, we find a failure and trace its cause. Then we improve the relevant component, repeat the same questions and compare the results. Source evidence and human checks support the whole process. For example, the audit revealed missing venue facts. After a change to the memory writer, correct answers rose from twelve to sixteen out of sixteen. Remaining failures can guide the next test. These related development cases do not establish performance in every setting.",
  "Mem0 informs our research on extracting, updating and retrieving memories. LongMemEval provides external histories and questions, so we test beyond our own examples. Our study connects these foundations through controlled diagnosis and paired repair tests. We use a selected benchmark subset, not official full-benchmark scores. The research question is whether tracing a failure can guide a change that improves answers under the same test conditions.",
  "Our prototype is the experimental platform. We start with a history and verify the extracted facts. Source-linked questions test the target. We compare the source, stored memories, retrieved context and answer. This can reveal a missing fact, a retrieval issue or an error in how the answer uses the evidence. We identify a cause only when the trace supports it. We save the evidence and assessments for review.",
  "We measure three different things: question validity, evaluator reliability and target performance. Study A compares three testing methods. B compares four retrieval strategies. C repeats the strategy comparison on LongMemEval. Both B and C use Astra MAX, sixteen questions and three repeats per strategy. We freeze inputs for controlled comparisons, keep unresolved cases, and preserve old results. Two reviewers work independently, followed by human verification of AI-assisted judgments. Reused histories and related review models still limit independence.",
  "We first tested whether the questions themselves were valid. On ten histories, fourteen of forty planned slots were valid, fourteen invalid and twelve missing. After repairs and review, two uncertain questions required regeneration. The current reviewed set has forty valid questions, and all forty executed. This is a development comparison on reused histories. It supports improved test quality after repair and review, rather than perfect first-pass generation on unseen data.",
  "To check whether the Auditor itself is reliable, we compare its judgments with human-verified references. On the same answers, failure detection rose from fifty-five to sixty-three of sixty-nine. False alarms fell from eighteen to zero out of fifty-one passes. Only thirty-five of sixty-three detections have verified correct types, and twenty-seven reference failures lack one agreed type. On separately designed errors, both scoring guides tied. The controlled result does not guarantee performance on natural answers.",
  "The four strategies differ in memory selection. First-match takes the first relevant record. Relationship-priority uses update and conflict links. Task-and-project matching filters by context. Time-and-importance ranks relevant records using those signals. Relationship-priority and time-and-importance tied at thirty-three passes in B. Relationship-priority had twenty-eight in C. All counts use forty-eight planned answers. Unresolved cases stay visible. This comparison shows strategy choice matters in our samples, but does not establish a universal winner.",
  "The paired repair experiment illustrates our method. The audit found a failed answer and the trace showed that venue facts were missing from target memory. We changed the writer and kept the same sixteen questions across four related histories. Human-checked passes rose from twelve to sixteen. Four answers improved and none worsened. The result supports targeted repair on these development cases; new data is needed to test generalisation.",
  "In the demonstration, follow one piece of evidence. Open the Dashboard and choose a saved failed answer. Inspect its source and the target memory to see the omission. Then open the paired result after the writer repair. The same question now passes. The saved aggregate connects this example to all sixteen questions. This is how a developer could use the audit during maintenance.",
  "Our experiments support targeted diagnosis and repair on the tested cases. They do not establish reliability in every setting. Natural failure categories remain incomplete, synthetic histories share structure, and the benchmark subset is small. Next, we should test unseen natural histories, expand the benchmark, and use more independent reviewers. We should also measure review effort and cost. The contribution is a traceable experimental method and evidence that a targeted repair can improve answers."
];
const timings=[25,40,40,30,35,40,30,35,40,50,0,55];
const activeIndices=[0,1,2,3,4,5,6,7,8,9,11];
speech[7]="For the sixty-three natural-answer failures detected by Astra, thirty-five have a verified correct type. The other twenty-eight cannot be counted as verified correct; some have no agreed reference type. Across all sixty-nine failures, twenty-seven lack one agreed type. In a separate set of deliberately designed errors, both scoring rubrics detected and classified all one hundred and twenty errors, with no false alarms on thirty controls. That supports clear-case classification, but does not settle the natural-answer gaps.";
const matched=await read('output/ac3-generated/four-evaluator-matched-20261102-v1/analysis.json');
if(!matched.complete || matched.cases!==120 || matched.reference_fail!==69 || matched.reference_pass!==51)throw Error('Matched comparison is not complete');
const matchedOrder=['rule','luna','astra'];
const mr=k=>matched.results[k];
speech[9]="The audit found missing venue facts in target memory. We changed the writer and repeated the same sixteen questions across four related histories. Human-checked passes rose from twelve to sixteen. Four improved and none worsened. This supports targeted repair on these cases. New data is needed to test whether it generalises.";
speech[10]="";
speech[9]+=" The same questions and conditions let us assess the change, while the evidence trail helps explain the observed failure. These related cases cannot establish a universal result.";
speech[11]="Our results support targeted diagnosis and repair on these cases. Natural failure categories remain incomplete, the histories are related and the benchmark subset is small. Future work should test unseen, diverse histories, expand the benchmark and use independent reviewers. We should also measure review effort and cost. The contribution is a traceable research method supported by a paired repair experiment.";

const titles=["Do You Remember Me?", "Four dimensions of AI memory behaviour", "From discovery to a tested repair", "How these foundations support our research", "Research procedure: evidence to evaluation", "How we keep the comparison objective", "Repair and review improved question quality", "How reliable is error classification?", "Retrieval choices change the results", "Paired repair experiment: 4 answers improved", "Evaluators on the same answers", "What the evidence supports next"];
const sections=["Research question", "Problem and motivation", "Research value and implications", "Related work", "Method", "Evaluation design", "Finding 1: question quality", "Finding 2: evaluator reliability", "Finding 3: strategy comparison", "Main result: diagnosis and repair", "Research method development", "Limitations and future work"];
const sources=[
 ['docs/PROPOSAL_STATUS_20261101.md'],
 ['ELEC5623_Group2_Proposal.pdf, Sections 3 and 7.1. Examples here are explanatory, not measured results.'],
 ['docs/PROPOSAL_STATUS_20261101.md','docs/ARCHITECTURE.md'],
 ['LongMemEval: Wu et al., ICLR 2025. https://arxiv.org/abs/2410.10813','Mem0: Chhikara et al., 2025. https://arxiv.org/abs/2504.19413','The gap is our chosen workflow focus. We do not claim that memory platforms lack evaluation capabilities.'],
 ['docs/ARCHITECTURE.md','backend/app/test_generator/agent.py','backend/app/extraction/relationship_agent.py','Research review agents are separate from the runtime extraction, generation and evaluation components.'],
 ['docs/PROPOSAL_STATUS_20261101.md',aPath,bPath,cPath,diagnosticPath,'output/proposal-delivery/ac3-balanced-taxonomy-validation-20261102-v1/protocol.json','Freeze claims concern the recorded controlled retests. Not all earlier exploratory analyses were preregistered. The new diagnostic freezes150curated answers and balances75original-first/75revised-first pairs. Its source-only independent MAX reviews omit intended labels, grader scores and the other review. The later human verification sees AI opinions and is not first-pass blind human annotation.'],
 [ac2Path,'docs/AC2_TEN_SCENE_RETEST_20261101.md','output/proposal-delivery/ac2-original-ten-effective-review-analysis-20261101-v1/human-confirmation.json','The ten sources are unchanged, previously observed and structurally related. Two questions were actually regenerated after review. Question validity is distinct from target-answer correctness. The separate 40-answer smoke had automatic outcomes 9 pass, 12 fail, 19 uncertain, not human answer labels. Of 32 relationships, 26 are confirmed and 6 uncertain/disputed labels are excluded from confirmed-correct counts.'],
 [diagnosticPath,diagnosticAnalysisPath,diagnosticReferencePath,diagnosticConfirmationPath,mainReportPath,'New diagnostic:30fictional histories,150intentionally curated answers. These are controlled fault injections, not natural target responses or an estimate of model error frequency. Actual independent MAX source-only reviews determine reference labels, not the author-intended key. The user explicitly reports two people independently verified all150source/question/answer/type-reference judgments with AI assistance. This does not claim authenticated identities, first-pass blind human annotation, blindness to automatic scores, or human approval of the300automatic grader predictions.','Both original and revised MAX rubric arms:120/120joint detection+correct type, each of four actual categories30/30, false positives0/30, decided coverage150/150. All150paired predictions are identical. There is no observed improvement or regression, so the original production rubric is retained and the revised text remains a research candidate. Zero observed errors on designed cases does not establish zero population risk.',ac3Path,'output/proposal-delivery/ac3-astra-max-retest-20261101-v2/analysis.json','Earlier natural model-answer cohort remains separate:120AstraMAXanswers across30related reused synthetic histories.51human-verified AI-assisted passes and69failures. Candidate detects63/69 versus rule baseline55/69; false positives0/51 versus18/51. Verified category35/63all detected, or35/42conditional on agreed single types.27failures lack a single agreed type. Gold type coverage38accuracy,2conflict,2appropriate,0freshness. Appropriate typing0/2, freshness unmeasured in that earlier cohort. Recall-change95%descriptive history-bootstrap interval−2.6to+25.4pp includes0. The clean diagnostic does not replace or resolve these natural-case results.'],
 [retestPath,'output/proposal-delivery/bc-reader-retest-20261101-v2/analysis.json','output/proposal-delivery/bc-reader-retest-20261101-v2/diagnosis/findings.json','B: four related synthetic histories,16 questions,three repeats perpolicy. Strong common reader replaces the old single-record reader; rule writer remains fixed and misses venue facts. Same-source historical overlap has only FS01-FS03.','C: sixteen stratified LongMemEval Oracle cases,three repeats,including two old anchors. Dataset difficulty differs from B; not official full-benchmark scores.','Eachpolicy has48plannedslots. Reference/question ambiguity and reviewer disagreements remain unresolved,not failures. Latest labels retain independent Astra max AI reviews and user-reported independent human verification of the AI-assisted judgments. This does not establish first-pass blind human annotation or blindness to automatic scores. Source validity and outputs are separate.'],
 [writerPath,'research/astra-ac2-20261101/four-writer-prospective-evidence.zip','Same 16 question prompts, evidence, histories and paired settings, with the writer intentionally changed. Four related synthetic histories; AI-assisted reviews independently checked and accepted by two people according to the user. Development evidence, not population-wide causal proof.'],
 ['http://localhost:5173/','http://localhost:5173/audits/RUNB8AF4F09C517464F9C965F0860001313','http://localhost:5173/compare?before=RUNB8AF4F09C517464F9C965F0860001313&after=RUNB53C3562569941B7A5E6A8F66B6B53FE','Open the local system before presenting. Preload the saved Dashboard, report and comparison tabs. The per-pair page shows automatic assessments; aggregate 12/16 to 16/16 uses the independent AI-assisted human reference checks. No paid call or new question generation is part of the seven-minute demonstration.'],
 ['docs/PROPOSAL_STATUS_20261101.md',mainReportPath,aPath,bPath,cPath,ac2Path,diagnosticPath,'Latest ten-scene cohort is a development repair result. New Astra MAX A comparison: each method5/16targetpasses, while distinct confirmed predefined patterns found are1direct,1template,3contextual out16potential patterns. This is discovery count, not sensitivity against16provedbugs. One mapping dispute remains. The user confirms two people independently verified AI-assisted judgments for the552newA/B/C/AC3answers, and separately the150new diagnostic references. Original AI labels, source/reference uncertainty and type disputes remain preserved. The diagnostic ceiling tie shows no rubric advantage. Designed cases cannot resolve classification generalisation to naturally incomplete or ambiguous model answers. Expected strategy superiority is not consistently observed. New natural failures, diverse held-out histories and larger external benchmark coverage remain future work.']
];
sources[10]=['output/ac3-generated/four-evaluator-matched-20261102-v1/analysis.json','output/ac3-generated/four-evaluator-matched-20261102-v1/protocol.json','docs/EXPERIMENT_REPORT_ASTRA_MAX_20261102.md','Same 120 saved answers and human-verified AI-assisted references. Reference failures69 and passes51. Rule55/69 and18/51 false alarms; OpenAI gpt-6-luna medium60/69 and0/51; OpenAI gpt-6-astra max63/69 and0/51. Each covers120/120. The rule additionally uses archived structured fields including expected behavior; model effort and providers differ. The sources are related reused synthetic development histories, not held-out evidence or a universal model ranking.'];
 sources[3].push('Mem0 is design background in this main-result presentation. The optional native Mem0 demo described in README.md is not the target behind the reported writer-repair or B/C main results. LongMemEval supplied actual external cases for experiment C. The repair example uses four related synthetic development histories.');
const words=s=>s.match(/[A-Za-z0-9]+(?:['’-][A-Za-z0-9]+)*/g)?.length??0;
const speakerStats=[0,1,2,3].map(i=>{const indices=activeIndices.filter(n=>Math.floor(n/3)===i);return {speaker:`Speaker ${i+1}`,slides:indices.map(n=>activeIndices.indexOf(n)+1),words:indices.reduce((total,n)=>total+words(speech[n]),0),seconds:indices.reduce((total,n)=>total+timings[n],0)};});
if(timings.reduce((a,b)=>a+b,0)!==420||speakerStats.some(s=>s.seconds!==105)||speech.reduce((n,s)=>n+words(s),0)>900)throw Error('Seven-minute speaking budget exceeded');

const p=await PresentationFile.importPptx(await FileBlob.load(path.join(root,inputRel)));
await fs.writeFile(path.join(build,'original-inspect.json'),JSON.stringify(await p.inspect({kind:'slide,shape,textbox,notes,layout',maxChars:180000}),null,2));
const layoutId=(p.layouts.items.find(l=>l.name==='Blank')??p.layouts.items[0]).id;
p.slides.keep([]);
const C={navy:'#243B53',ink:'#1D2C40',teal:'#346A9A',muted:'#5F7184',paper:'#F9FBFD',line:'#D9E1E8',light:'#E8EFF6',invalid:'#7A8B9C',amber:'#9F6F25',white:'#FFFFFF'};
function txt(slide,name,text,left,top,width,height,size=24,color=C.ink,bold=false){
 const s=slide.shapes.add({name,geometry:'textbox',position:{left,top,width,height},fill:'none',line:{fill:'none',width:0}});
 s.text=text;s.text.style={typeface:'Arial',fontSize:size,color,bold};return s;
}
function base(index,subtitle='',foot=''){
 const s=p.slides.add({layoutId,background:{fill:C.paper}});
 txt(s,'section',sections[index],64,30,1050,28,18,C.teal,true);
 txt(s,'headline',titles[index],64,78,1152,64,36,C.ink,true);
 const wrap=(copy,length)=>copy.split('\n').map(line=>{const rows=[];let row='';for(const word of line.split(' ')){if(row&&row.length+word.length+1>length){rows.push(row);row=word;}else row+=(row?' ':'')+word;}if(row)rows.push(row);return rows.join('\n');}).join('\n');
 if(subtitle)txt(s,'subtitle',wrap(subtitle,104),64,145,1152,65,23,C.muted);
 if(foot)txt(s,'scope',wrap(foot,122),64,640,1010,51,15,C.muted);
 txt(s,'speaker',`Speaker ${Math.floor(index/3)+1}    ${String(activeIndices.indexOf(index)+1).padStart(2,'0')}`,1080,675,144,22,14,C.muted);
 const cue=index===10?'Explain the matched answers and the limits of the comparison.':index===11?'State the limits and concrete next steps. End without reading the references.':'Explain the finding rather than reading every number.';
 s.speakerNotes.text=`Speaker ${Math.floor(index/3)+1}\nPlanned time: ${timings[index]} seconds\n\nSPOKEN SCRIPT\n${speech[index]}\n\nPRESENTER CUE (not spoken)\n${cue}\n\nSOURCES AND SCOPE (not spoken)\n${sources[index].join('\n')}`;
 s.speakerNotes.setVisible(true);return s;
}
function table(s,name,values,widths,{left=64,top=225,height=340,fontSize=23,headerSize=20,paddingY=12}={}){
 const t=s.tables.add({rows:values.length,columns:values[0].length,left,top,width:widths.reduce((a,b)=>a+b,0),height,columnWidths:widths,values});
 t.styleOptions={headerRow:true,bandedRows:false};
 t.cells.block({row:0,column:0,rowCount:values.length,columnCount:values[0].length}).assign({textStyle:{typeface:'Arial',fontSize,color:C.ink},margins:{left:14,right:14,top:paddingY,bottom:paddingY},anchor:'center',horizontalOverflow:'wrap'});
 t.borders.assign({fill:C.line,width:0.8,style:'solid'});
 for(let r=0;r<values.length;r++){
  for(let c=0;c<values[0].length;c++){
   const cell=t.getCell(r,c);cell.fill=r===0?C.light:r%2?C.white:C.paper;
   cell.text.style={typeface:'Arial',fontSize:r===0?headerSize:fontSize,color:r===0?C.navy:C.ink,bold:r===0};
  }
 }
 return t;
}
function bar(s,categories,series,max,{top=225,height=320,width=1125,left=64,grouping='stacked',dataFont=24,labelPosition='center',labelColor=C.white}={}){
 const chart=s.charts.add('bar',{position:{left,top,width,height},categories,series,barOptions:{direction:'bar',grouping,gapWidth:grouping==='clustered'?45:80,overlap:grouping==='stacked'?100:0},hasLegend:true,legend:{position:'bottom',textStyle:{fontSize:19,fill:C.ink}},xAxis:{visible:true,min:0,max,majorUnit:max===40?10:max===69?23:max===48?12:4,numberFormatCode:'0',textStyle:{fontSize:21,fill:C.ink},majorGridlines:null,line:{fill:'none',width:0}},yAxis:{visible:true,min:0,max,majorUnit:max===40?10:max===69?23:max===48?12:4,numberFormatCode:'0',textStyle:{fontSize:19,fill:C.muted},majorGridlines:{fill:C.line,width:0.8},line:{fill:C.line,width:0.8}},dataLabels:{showValue:true,position:labelPosition,numberFormatCode:'0',textStyle:{fontSize:dataFont,bold:true,fill:labelColor}},chartFill:'none',chartLine:{fill:'none',width:0},plotAreaFill:'none',plotAreaLine:{fill:'none',width:0}});
 applyPresentationChartFont(chart,{fontFamily:'Arial'});return chart;
}

// 1: an asymmetric typographic cover, limited to the topic and question.
{
 const s=base(0);s.background.fill=C.paper;
 const title=s.shapes.items.find(x=>x.name==='headline');title.text='Do You Remember Me?';title.position={left:82,top:185,width:1110,height:110};title.text.style={typeface:'Arial',fontSize:68,color:C.ink,bold:true};
 txt(s,'project-name','An experimental study of AI memory auditing',84,320,1100,55,29,C.teal,true);
 txt(s,'question-label','RESEARCH QUESTION',84,435,1060,35,18,C.muted,true);
 txt(s,'purpose','Can evidence-based auditing identify AI memory failures\nand guide improvements?',84,480,1100,90,30,C.ink);
}
// 2: a balanced 2x2 editorial layout keeps each diagnostic lens distinct.
{
 const s=base(1,'Four dimensions used to evaluate memory behaviour.','Illustrative examples only.');
 s.shapes.items.find(x=>x.name==='headline').text='Four dimensions of AI memory behaviour';
 const cards=[
  {n:'01',title:'Accuracy',question:'Is the fact correct?',example:'Asked Alex. Answered Sam.',x:78,y:230},
  {n:'02',title:'Freshness',question:'Did it follow the update?',example:'Address changed. Old one used.',x:678,y:230},
  {n:'03',title:'Conflict resolution',question:'Did it handle disagreement?',example:'Hall A or Hall B. No priority.',x:78,y:435},
  {n:'04',title:'Appropriate use',question:'Does it fit this task?',example:'Python preference on Java task.',x:678,y:435}
 ];
 for(const c of cards){
  s.shapes.add({name:`dimension-card-${c.n}`,geometry:'roundRect',position:{left:c.x,top:c.y,width:525,height:160},fill:C.white,line:{fill:C.line,width:1}});
  s.shapes.add({name:`number-badge-${c.n}`,geometry:'ellipse',position:{left:c.x+22,top:c.y+24,width:48,height:48},fill:C.teal,line:{fill:C.teal,width:1}});
  txt(s,`number-${c.n}`,c.n,c.x+25,c.y+31,42,34,20,C.white,true);
  txt(s,`title-${c.n}`,c.title,c.x+90,c.y+25,410,42,28,C.ink,true);
  txt(s,`question-${c.n}`,c.question,c.x+90,c.y+72,410,32,22,C.teal);
  txt(s,`example-${c.n}`,c.example,c.x+90,c.y+113,410,30,19,C.muted);
 }
}
// 3: research cycle and the observed paired repair example.
{
 const s=base(2,'Source evidence and human checks support every stage.','Four related synthetic development histories; findings require validation on new data.');
 s.shapes.items.find(x=>x.name==='headline').text='From discovery to a tested repair';
 const steps=[['1','Find','Detect a failure'],['2','Diagnose','Trace its cause'],['3','Improve','Change the writer'],['4','Retest','Repeat fixed questions'],['5','Compare','Check the results']];
 const boxes=[];
 steps.forEach((r,i)=>{const x=65+i*245;const box=s.shapes.add({name:`cycle-${i+1}`,geometry:'roundRect',position:{left:x,top:235,width:205,height:135},fill:i===2?C.teal:C.light,line:{fill:i===2?C.teal:C.line,width:1}});boxes.push(box);txt(s,`cycle-num-${i}`,r[0],x+14,250,34,36,22,i===2?C.white:C.muted,true);txt(s,`cycle-title-${i}`,r[1],x+49,250,150,40,25,i===2?C.white:C.ink,true);txt(s,`cycle-detail-${i}`,r[2],x+14,315,180,40,19,i===2?C.white:C.muted);});
 for(let i=0;i<4;i++)s.shapes.add({name:`cycle-arrow-${i}`,geometry:'connector',kind:'straight',from:boxes[i],fromIdx:s.shapes.getConnectionSiteIndex(boxes[i],'right'),to:boxes[i+1],toIdx:s.shapes.getConnectionSiteIndex(boxes[i+1],'left'),line:{fill:C.teal,width:2},tail:{type:'triangle',width:'med',length:'med'}});
 s.shapes.add({name:'cycle-return-right',geometry:'connector',kind:'straight',position:{left:1147,top:370,width:0,height:30},line:{fill:C.muted,width:1.5}});
 s.shapes.add({name:'cycle-return-bottom',geometry:'connector',kind:'straight',position:{left:167,top:400,width:980,height:0},line:{fill:C.muted,width:1.5}});
 s.shapes.add({name:'cycle-return-up',geometry:'connector',kind:'straight',position:{left:167,top:370,width:0,height:30},line:{fill:C.muted,width:1.5},head:{type:'triangle',width:'med',length:'med'}});
 txt(s,'cycle-label','EXAMPLE: MISSING VENUE FACTS',80,426,1050,34,18,C.teal,true);
 txt(s,'cycle-example','Missing facts identified. Memory writer improved.',80,468,1110,42,27,C.ink,true);
 txt(s,'cycle-result','Same 16 questions: 12 correct before, 16 after.',80,520,1110,50,30,C.teal,true);
 txt(s,'cycle-feedback','Review the evidence and use remaining failures to guide the next test.',80,580,1110,44,23,C.muted);
}
// 4: explain the need and contribution of each research foundation.
{
 const s=base(3,'Design reference, external evidence and a tested repair workflow.','Mem0: Chhikara et al., 2025. LongMemEval: Wu et al., ICLR 2025. Selected benchmark subset, not official scores.');
 s.shapes.items.find(x=>x.name==='headline').text='How these foundations support our research';
 const rows=[['Mem0','Manage changing facts','Informs extraction,\nupdates and retrieval','Design reference'],['LongMemEval','Test beyond our examples','External histories for\nstrategy comparison','Used in experiment C'],['Our study','Test audit-guided repairs','Controlled diagnosis;\npaired comparisons','Experimental evidence']];
 rows.forEach((r,i)=>{const x=84+i*397;txt(s,`work-${i}`,r[0],x,240,355,55,33,C.teal,true);txt(s,`need-${i}`,r[1],x,330,355,74,27,C.ink,true);txt(s,`help-${i}`,r[2],x,419,355,100,27,C.ink);txt(s,`use-${i}`,r[3],x,525,355,42,22,C.muted);});
 txt(s,'example','Tested example: missing facts diagnosed; repair improved 12/16 to 16/16.',84,591,1120,47,27,C.teal,true);
}

// 5: editable process boxes and attached arrows highlight human confirmation.
{
 const s=base(4,'The prototype provides a controlled experimental platform.','Saved sources, memories, retrieved context and answers support review.');
 s.shapes.items.find(x=>x.name==='headline').text='Research procedure: evidence to evaluation';
 const rows=[['Import','Authorised\nhistory'],['Extract','Facts and\nrelationships'],['Confirm','Human\nreview'],['Test','Source-linked\nquestions'],['Assess','Answers and\njudgments']];
 const boxes=[];
 rows.forEach((r,i)=>{const x=75+i*238,isHuman=i===2;
  txt(s,`step-number-${i}`,String(i+1),x+15,235,155,48,30,C.muted);
  const box=s.shapes.add({name:`process-stage-${i+1}`,geometry:'roundRect',position:{left:x,top:302,width:180,height:180},fill:isHuman?C.teal:C.light,line:{fill:isHuman?C.teal:C.line,width:1}});boxes.push(box);
  txt(s,`stage-${i}`,r[0],x+15,324,155,45,28,isHuman?C.white:C.teal,true);
  txt(s,`detail-${i}`,r[1],x+15,389,155,73,22,isHuman?C.white:C.ink);
 });
 for(let i=0;i<boxes.length-1;i++)s.shapes.add({name:`flow-arrow-${i+1}`,geometry:'connector',kind:'straight',from:boxes[i],fromIdx:s.shapes.getConnectionSiteIndex(boxes[i],'right'),to:boxes[i+1],toIdx:s.shapes.getConnectionSiteIndex(boxes[i+1],'left'),line:{fill:C.teal,width:2},tail:{type:'triangle',width:'med',length:'med'}});
 txt(s,'trace','Trace writing, retrieval and use where evidence permits.',80,575,1120,58,31,C.ink,true);
}

// 6: complementary columns for comparison design and bias controls.
{
 const s=base(5,'Measure the target and check the evaluator separately.','Reused cases and shared AI review models still limit independence.');
 txt(s,'left-title','What we compare',85,240,520,52,33,C.teal,true);
 txt(s,'studies','A   Three test methods\nB   Four retrieval policies\nC   LongMemEval subset',85,328,540,180,29);
 txt(s,'right-title','How we reduce bias',700,240,510,52,33,C.teal,true);
 txt(s,'controls','Fixed inputs and settings\nIndependent review + human check\nUncertainty retained',700,328,505,180,27);
 txt(s,'evaluator','Evaluator check: judgments against verified references.',85,590,1120,48,29,C.ink,true);
}

// 7: matched doughnuts compare the composition of all planned slots.
{
 const s=base(6,'Same ten histories. Same 40 planned slots.','Related development histories. Human-checked AI reviews. Six relationship labels remain unresolved.');
 function ring(left,values,categories){
  const chart=s.charts.add('doughnut',{position:{left,top:255,width:390,height:250},categories,series:[{name:'Planned question slots',values,points:values.map((_,idx)=>({idx,fill:[C.teal,C.invalid,C.amber][idx]}))}],doughnutOptions:{holeSize:65,firstSliceAngle:270},hasLegend:false,dataLabels:{showValue:false,showPercent:false,showCategoryName:false},chartFill:'none',chartLine:{fill:'none',width:0}});
  applyPresentationChartFont(chart,{fontFamily:'Arial'});
 }
 txt(s,'original-label','Original: 14/40 valid',95,215,450,43,29,C.ink,true);
 txt(s,'repaired-label','After repair: 40/40 valid',715,215,480,43,29,C.ink,true);
 ring(90,[14,14,12],['Valid','Invalid','Not generated']);ring(710,[40],['Valid']);
 txt(s,'gain','+26',542,326,170,66,47,C.teal,true);
 txt(s,'gain-label','valid questions',510,389,240,40,24,C.muted);
 txt(s,'original-valid','14 valid',92,503,130,38,23,C.teal,true);txt(s,'original-invalid','14 invalid',235,503,150,38,23,C.invalid,true);txt(s,'original-missing','12 missing',398,503,160,38,23,C.amber,true);
 txt(s,'repaired-counts','40 valid after repair and review',715,503,500,38,23,C.teal,true);
 txt(s,'revision','38 accepted first. Two regenerated and reviewed.',78,553,1120,43,25,C.ink,true);
 txt(s,'execution','40/40 current questions executed.',78,600,1120,34,23,C.muted);
}
// 8: verified error categories, distinct from the four-evaluator detection comparison.
{
 const s=base(7,'Among the 63 failures detected by Astra MAX on natural model answers.','Related reused synthetic histories. AI-assisted references verified by two people according to the user.');
 s.shapes.items.find(x=>x.name==='headline').text='How reliable is error classification?';
 const chart=s.charts.add('doughnut',{position:{left:80,top:225,width:480,height:280},categories:['Verified correct','Other or unverified'],series:[{name:'Detected failures',values:[35,28],points:[{idx:0,fill:C.teal},{idx:1,fill:C.invalid}]}],doughnutOptions:{holeSize:65},hasLegend:false,dataLabels:{showValue:false},chartFill:'none',chartLine:{fill:'none',width:0}});applyPresentationChartFont(chart,{fontFamily:'Arial'});
 txt(s,'verified','35 / 63',650,235,480,66,45,C.teal,true);
 txt(s,'verified-label','verified correct type',650,300,490,40,25,C.ink);
 txt(s,'remaining','28 / 63',650,367,480,55,36,C.ink,true);
 txt(s,'remaining-label','not verified correct',650,426,490,40,25,C.muted);
 txt(s,'gap','27 of 69 reference failures lack one agreed type.',80,534,1120,42,25,C.ink,true);
 txt(s,'controlled','Designed cases: 120/120 detected and typed; 0/30 false alarms.\nBoth scoring rubrics tied. Clear-case evidence only.',80,583,1120,55,21,C.muted);
}

// 9: grouped pass counts show strategy differences; tied outcomes stay tied.
{
 const s=base(8,'Astra MAX. 16 questions, 3 repeats: 48 answers per strategy.','B: four related synthetic histories. C: 16 selected LongMemEval cases, with four reference flags. Different datasets.');
 bar(s,['First match','Relationship','Task / project','Time / importance'],[
 {name:'B: synthetic',values:policies.map(k=>currentB.conditions.find(c=>c.strategy===k).pass),fill:C.teal},
 {name:'C: LongMemEval subset',values:policies.map(k=>currentC.conditions.find(c=>c.strategy===k).pass),fill:C.invalid}
 ],48,{top:205,height:285,grouping:'clustered',dataFont:16,labelPosition:'outEnd',labelColor:C.ink});
 txt(s,'policy-meaning','Selection: first record / update links / task context / time and importance.',78,503,1120,38,22);
 txt(s,'strategy-conclusion','B: relationship = time. C: relationship led the pass count.',78,545,1120,38,26,C.ink,true);
 txt(s,'unresolved','Unresolved B/C: first 0/12; relationship 3/13; task 3/12; time 3/13.\nUnresolved answers remain separate from failures. No universal winner established.',78,590,1120,44,18,C.muted);
}

// 10: a two-point line connects paired conditions, not a time trend.
{
 const s=base(9,'Diagnosis: missing venue facts. Intervention: repair the memory writer.','Four related synthetic histories, same 16 questions. Human-checked AI-assisted judgments. Paired conditions, not a time series.');
 const chart=s.charts.add('line',{
  position:{left:78,top:225,width:765,height:310},categories:['Before repair','After repair'],
  series:[{name:'Correct answers',values:[12,16],line:{fill:C.teal,width:4},marker:{symbol:'circle',size:11,fill:C.teal}}],
  lineOptions:{grouping:'standard',smooth:false},hasLegend:false,
  xAxis:{visible:true,textStyle:{fontSize:23,fill:C.ink},line:{fill:C.line,width:1}},
  yAxis:{visible:true,min:0,max:16,majorUnit:4,numberFormatCode:'0',textStyle:{fontSize:20,fill:C.muted},majorGridlines:{fill:C.line,width:1},line:{fill:'none',width:0}},
  dataLabels:{showValue:true,position:'top',numberFormatCode:'0',textStyle:{fontSize:27,bold:true,fill:C.ink}},chartFill:'none',chartLine:{fill:'none',width:0},plotAreaFill:'none',plotAreaLine:{fill:'none',width:0}
 });applyPresentationChartFont(chart,{fontFamily:'Arial'});
 txt(s,'pass-rate','75% to 100%',900,272,310,57,36,C.teal,true);
 txt(s,'difference','+25 percentage\npoints',900,338,310,92,29,C.ink,true);
 txt(s,'paired-check','4 improved\n0 worsened',900,445,310,65,26,C.muted);
 txt(s,'repair-takeaway','Same 16 questions: 12 correct before, 16 correct after.',78,558,1120,54,30,C.ink,true);
 txt(s,'repair-control','Evidence guided the repair. Fixed questions checked it.',78,610,1120,32,22,C.muted);
}
// 12: three research priorities and one measured conclusion.
{
 const s=base(11,'Evidence for targeted repair, with clear limits.','Selected development cases. No claim of universal reliability or official full-benchmark scores.');
 const rows=[['Classification','Unresolved natural cases','New reference judgments'],['Generalisability','Related synthetic histories','Unseen, diverse histories'],['Practical use','Review time and cost unknown','Measure effort in real use']];
 rows.forEach((r,i)=>{const x=84+i*397;txt(s,`topic-${i}`,r[0],x,268,355,55,31,C.teal,true);txt(s,`limit-${i}`,r[1],x,359,350,98,27);txt(s,`next-${i}`,r[2],x,478,350,94,27,C.muted);});
 txt(s,'closing','Finding: targeted diagnosis guided a measurable repair.',84,593,1120,50,30,C.ink,true);
}

if(p.slides.items.length!==11)throw Error('Eleven slides are required after removing the evaluator comparison');
const inspect=await p.inspect({kind:'slide,textbox,shape,table,chart,notes,layout',maxChars:220000});
await fs.writeFile(path.join(build,'final-inspect.json'),JSON.stringify(inspect,null,2));
for(let i=0;i<p.slides.items.length;i++){
 const s=p.slides.items[i];
 await fs.writeFile(path.join(build,`slide-${String(i+1).padStart(2,'0')}.png`),new Uint8Array(await(await s.export({format:'png',scale:1})).arrayBuffer()));
 await fs.writeFile(path.join(build,`slide-${String(i+1).padStart(2,'0')}.layout.json`),JSON.stringify(await s.export({format:'layout'}),null,2));
}
await fs.writeFile(path.join(build,'montage.webp'),new Uint8Array(await(await p.export({format:'webp',montage:true,scale:.4})).arrayBuffer()));
await fs.rm(output,{force:true});
const candidate=path.join(build,'candidate.pptx');await(await PresentationFile.exportPptx(p)).save(candidate);
const inputHash=await sha(path.join(root,inputRel));
const result=await finalizePresentation({workspaceDir:root,candidatePath:candidate,finalPath:output,pythonExecutable:python,integrityValidatorPath:path.join(skill,'container_tools/inspect_presentation_package_integrity.py'),layoutValidatorPath:path.join(skill,'container_tools/inspect_presentation_layout_geometry.py'),layoutArgs:['--expected-slide-size-emu','12192000,6858000','--validate-heading-fit','--validate-bullet-geometry',...[]],explicitTotalSlideCount:11,requiredNativeTableOwnerSlides:[],requiredNativeChartOwnerSlides:[7,8,9,10],materializeLiteralChartWorkbooks:true,fontPolicy:{basis:'reference',families:['Arial'],referencePath:path.join(root,inputRel),referenceSha256:inputHash},verifyArtifactToolImport:true,receiptPath:path.join(build,'validation.json')});
await fs.copyFile(output,deliverable);
const sourceFiles=[ac2Path,ac3Path,diagnosticPath,diagnosticAnalysisPath,diagnosticReferencePath,diagnosticConfirmationPath,writerPath,bPath,cPath,aPath,retestPath,'output/proposal-delivery/bc-reader-retest-20261101-v2/analysis.json','docs/PROPOSAL_STATUS_20261101.md',mainReportPath,'backend/app/memory_agent/store.py'];
const provenance={input:inputRel,input_sha256:inputHash,output:path.relative(root,deliverable),output_sha256:await sha(deliverable),source_files:Object.fromEntries(await Promise.all(sourceFiles.map(async rel=>[rel,await sha(path.join(root,rel))]))),slide_count:11,total_seconds:420,total_spoken_words:speech.reduce((n,s)=>n+words(s),0),speaker_distribution:speakerStats,sections:activeIndices.map((i,n)=>({slide:n+1,section:sections[i],title:titles[i],seconds:timings[i],spoken_words:words(speech[i])})),notes:'Speaker labels, simple-English spoken scripts, presenter cues and source/scope notes. No separate Word script.',related_work_primary_sources:['https://arxiv.org/abs/2410.10813','https://arxiv.org/abs/2504.19413'],preserved_original:true,restyling:'Native doughnut charts show question composition, grouped bars show strategy differences, and a two-point native line chart shows the paired writer repair. Qualitative slides use text and stages, with no tables. Consistent light blue-white background, deep-blue text and light table headers across every slide. Same output file, four speakers, seven minutes. Main A/B/C/AC3 results use verified Astra MAX studies, with the separate balanced diagnostic added. Previously human-confirmed MAX AC1/AC2/writer evidence remains.',source_verification:'Main experimental model-backed generation, target and candidate scoring calls use actual OpenAI Astra MAX receipts. New A/B/C/AC3 independent research reviews are MAX; the user reports two people independently verified all552newanswers and AI-assisted judgments. The new150answer diagnostic has separate user-reported two-person independent AI-assisted reference verification, not approval of300machine grader predictions. Its answers are intentionally curated, not natural model outputs or an estimate of model error frequency. Both rubric arms achieve120/120joint detection/category,30/30in each actual class,0/30false alarms and150/150coverage, with150identicalpaired predictions. This ceiling tie provides no improvement evidence. The original production rubric remains and the revised text stays a research candidate. Earlier natural-answer63/69detection,35/63verifiedtypes,27unclassifiablefailures and0freshnesspositives in that cohort remain explicit; the new diagnostic does not replace or resolve them. AI-assisted verification is not first-pass blind human annotation or authenticated human identity. Blindness to automatic scores is not separately established. Accepted older AC1/AC2/writer references retain their original AI-assisted provenance, including high-effort reviewers. Deterministic rules/statistics have no effort setting. B/C each48plannedslots perpolicy and unresolved outcomes remain. No official full benchmark or population-wide claim.'};
await fs.writeFile(path.join(outDir,'presentation-provenance.json'),JSON.stringify(provenance,null,2)+'\n');
await fs.writeFile(path.join(build,'finalization-result.json'),JSON.stringify(result,null,2));
console.log(JSON.stringify({output,result,totalWords:provenance.total_spoken_words,speakers:speakerStats}));
