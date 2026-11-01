/** Reorganise the preserved deck into six requested topics and a seven-minute talk.
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
const outDir=path.join(root,'research/presentation-7min-20261101');
const build=path.join(root,process.env.PRESENTATION_BUILD_DIR??'.presentation-build-7min-20261101-final');
const inputRel='research/astra-ac2-ten-completion-20261101/Memory-Auditor-Presentation-20261101-AC2-Ten-Scenes.pptx';
const output=path.join(outDir,process.env.PRESENTATION_FILENAME??'Memory-Auditor-Presentation-7min-20261101.pptx');
await fs.mkdir(outDir,{recursive:true});await fs.mkdir(build,{recursive:true});
const read=async rel=>JSON.parse(await fs.readFile(path.join(root,rel),'utf8'));
const sha=async file=>crypto.createHash('sha256').update(await fs.readFile(file)).digest('hex');
const ac2Path='frontend/public/reports/ac2-astra-ten-source-v1.json';
const ac3Path='frontend/src/data/compactFinalDashboard.json';
const writerPath='frontend/public/reports/ac2-astra-comparison-v1.json';
const bPath='frontend/public/reports/b-astra-four-strategy-v1.json';
const cPath='research/astra-ac2-20261101/dashboard-latest-c-plan.json';
const aPath='research/astra-ac2-20261101/experiment-a-historical-metrics.json';
const ac2=(await read(ac2Path)).ten_scene_retest;
const ac3=(await read(ac3Path)).ac3;
const writer=(await read(writerPath)).writer_four_followup;
const b=await read(bPath),c=await read(cPath),a=await read(aPath);
if(await sha(path.join(root,cPath))!=='f5735c9ed3088b4b65c75fa8aa6534ae348ca43251d0f06084086f7fb97e0842')throw Error('The separately verified LongMemEval plan changed; recompute consensus before editing its figures');
if(ac2.valid!==40||ac2.revised_questions!==2||ac2.review_status!=='human_confirmed'||ac2.execution_check.answers!==40)throw Error('Latest confirmed AC2 evidence changed');
if(ac3.new.failure_recall_conservative.numerator!==61||ac3.new.failure_recall_conservative.denominator!==68||ac3.new.classification_accuracy_conservative.numerator!==54)throw Error('AC3 cohort changed');
if(writer.before_pass!==12||writer.after_pass!==16||writer.review_status!=='human_confirmed')throw Error('Confirmed repair evidence changed');
const policies=['weak_first_hit','strong_rule_based','scope_aware','temporal_importance'];
if(JSON.stringify(policies.map(k=>b.complete_paired_only[k].pass))!=='[3,3,0,0]')throw Error('Astra paired strategy evidence changed');
if(!a.methods.every(x=>x.inventoried_defects_detected.numerator===3&&x.inventoried_defects_detected.denominator===9))throw Error('Method comparison source changed');

const speech=[
  `Our project is the AI Memory Health Auditor. It checks how an AI assistant uses information from earlier conversations. A memory can be correct when stored, but wrong for a later task. Our web app turns this hidden behaviour into tests, evidence and clear results. We also use that evidence to test repairs.`,
  `We study four types of memory failure. Accuracy means recalling the right fact. Freshness means following an explicit update. Conflict resolution means handling records that disagree. Appropriate use means applying a memory only in the right context. For example, a user may prefer Python, while one assignment requires Java. A useful audit must check which rule the assistant actually follows.`,
  `We make three contributions. First, users can confirm or correct extracted facts before testing. Second, the system generates questions linked to those facts. Third, every result connects the source, expected behaviour and observed answer. We can then change one part of the memory system and repeat the same tests. These contributions form a complete, inspectable research workflow.`,
  `Existing work gives us a strong starting point. Mem0 builds memory extraction and retrieval. LongMemEval provides an external benchmark for long-term memory. Our focus is the user-facing audit workflow: confirm personal facts, generate behavioural tests, inspect failures and compare repairs. We complement these tools. We do not claim to replace them or to beat every existing memory system.`,
  `The product has five stages. We import an authorised history. AI agents extract facts and relationships, and a person confirms them. A generation agent writes source-linked questions and expected behaviour. Code checks format, evidence and test budget. The target answers, then rules or an AI judge with a fixed scoring guide assess it. We save each component's model settings and reasons.`,
  `We separate question validity, Auditor reliability and target performance. Experiment A varies the audit method under equal budgets. B changes retrieval on the same questions. C checks a LongMemEval subset. For controlled retests, we freeze inputs and record settings. The answer judge does not receive the policy name. Independent reviewers check sources, and people verify AI-assisted judgments. We preserve missing runs, disagreements and negative findings. These safeguards reduce bias, but reused cases still limit independence.`,
  `Here is the question-generation result on ten unchanged histories. Originally, only fourteen of forty planned questions were valid. After repairs, independent reviewers accepted thirty-eight and questioned two. We regenerated those two through the product, then reviewed the full set again. Two people confirmed the current forty questions. All forty also executed. This is a reviewed development result, rather than perfect first-pass generation.`,
  `We checked the Auditor against human reference judgments separately. On the same agreed answers, the revised scorer detected sixty-one of sixty-eight failures. It correctly classified fifty-four of the sixty-one detected failures. We observed no false positives among fifty human-pass answers. However, the interval for detection improvement includes zero. We therefore report improvement on this sample without claiming a statistically clear general gain.`,
  `The four policies choose memories differently. First-match takes the first relevant record. Relationship-priority follows memory links. Task-and-project matching selects the relevant context. Time-and-importance ranks records by those signals. Relationship-priority tied with first-match in B and led in C. But C used another model and only two LongMemEval cases. Outcomes vary across these two settings. We cannot identify one universal winner.`,
  `A practical example completes the repair loop. The audit showed that venue facts were missing from the target memory. We changed the memory writer and kept the same sixteen questions across four histories. Human-checked passes increased from twelve to sixteen. Four answers improved and none worsened. This shows how an audit can guide a useful repair on the tested cases.`,
  `We use saved results for the demonstration. First, open the Dashboard. Next, inspect one failed answer, its source and its memory trace. Finally, compare the same question before and after the writer change. Preloaded pages let us follow the evidence without a new model call.`,
  `Our main finding is that traceable audits can support useful repairs. The limits are important. Histories are mostly related and synthetic, reviews use AI assistance, and no method or policy wins consistently. Six relationship labels remain unresolved. Next, we need new diverse histories, reviewers who do not see automatic scores, and larger external benchmark tests. We also want easier review tools and lower running costs. These are the next research and product steps.`
];
const timings=[25,40,40,30,35,40,30,35,40,35,30,40];
const titles=[
 'AI Memory Health Auditor','Four ways memory can fail','Our main contributions',
 'Related work and the gap','Implementation: a source-based pipeline','Research design and bias controls',
 'Question quality improved after repair and review','Auditor judgments against human references','Four strategies, different effects',
 'Evidence guided a memory-writer repair','Demonstration: inspect one saved repair','Limits and the next research steps'
];
const sections=['Project introduction','Background and motivation','Main contributions','Related work and the gap','Methodology and implementation','Methodology and implementation','Results and demonstration','Results and demonstration','Results and demonstration','Results and demonstration','Results and demonstration','Results, limitations and future work'];
const sources=[
 ['docs/PROPOSAL_STATUS_20261101.md'],
 ['ELEC5623_Group2_Proposal.pdf, Sections 3 and 7.1. Examples here are explanatory, not measured results.'],
 ['docs/PROPOSAL_STATUS_20261101.md','docs/ARCHITECTURE.md'],
 ['LongMemEval: Wu et al., ICLR 2025. https://arxiv.org/abs/2410.10813','Mem0: Chhikara et al., 2025. https://arxiv.org/abs/2504.19413','The gap is our chosen workflow focus. We do not claim that memory platforms lack evaluation capabilities.'],
 ['docs/ARCHITECTURE.md','backend/app/test_generator/agent.py','backend/app/extraction/relationship_agent.py','Research review agents are separate from the runtime extraction, generation and evaluation components.'],
 ['docs/PROPOSAL_STATUS_20261101.md',aPath,bPath,cPath,'Freeze claims concern the recorded controlled retests. Not all earlier exploratory analyses were preregistered. AI-assisted human checks are not claimed as blind first-pass human annotation.'],
 [ac2Path,'docs/AC2_TEN_SCENE_RETEST_20261101.md','output/proposal-delivery/ac2-original-ten-effective-review-analysis-20261101-v1/human-confirmation.json','The ten sources are unchanged, previously observed and structurally related. Two questions were actually regenerated after review. Question validity is distinct from target-answer correctness. The separate 40-answer smoke had automatic outcomes 9 pass, 12 fail, 19 uncertain, not human answer labels. Of 32 relationships, 26 are confirmed and 6 uncertain/disputed labels are excluded from confirmed-correct counts.'],
 [ac3Path,'docs/EXPERIMENT_REPORT_2026-10-28.md','Same 118 agreed answers out of 120 across 30 related synthetic histories. Two disagreements remain excluded. Classification is conditional on detected failures, not overall accuracy. Recall difference interval is -5.4 to +23.2 percentage points. The revised scorer is an optional reassessment candidate, not the default evaluator.'],
 [bPath,cPath,'backend/app/memory_agent/store.py: _select, _select_scope_aware, _select_temporal_importance','B: three complete paired histories, 12 questions per policy, Astra, one run. Overall 52/64 answers saved, 12 missing; incomplete fourth history excluded. C: two selected and reused LongMemEval cases, three repeats per policy, six answers per policy. GPT-6 Luna through OpenRouter, human consensus. Different models and datasets across columns; do not compare absolute scores between B and C or claim an official benchmark result.'],
 [writerPath,'research/astra-ac2-20261101/four-writer-prospective-evidence.zip','Same 16 question prompts, evidence, histories and paired settings, with the writer intentionally changed. Four related synthetic histories; AI-assisted reviews independently checked and accepted by two people according to the user. Development evidence, not population-wide causal proof.'],
 ['http://localhost:5173/','http://localhost:5173/audits/RUN1FDDFC16B9F0406E9AD4B1CE6945E081','http://localhost:5173/compare?before=RUN1FDDFC16B9F0406E9AD4B1CE6945E081&after=RUN22924F327B0F4D00AB920E69C55542CF','Open the local system before presenting. Preload the saved Dashboard, report and comparison tabs. The per-pair page shows automatic assessments; aggregate 12/16 to 16/16 uses the independent AI-assisted human reference checks. No paid call or new question generation is part of the seven-minute demonstration.'],
 ['docs/PROPOSAL_STATUS_20261101.md',aPath,bPath,cPath,ac2Path,'Latest ten-scene cohort is a development repair result. A historical comparison found the same 3/9 inventoried defects for all three methods. Expected strategy superiority is not consistently observed. New data, genuinely independent review and larger benchmark coverage remain future work.']
];
const words=s=>s.match(/[A-Za-z0-9]+(?:['’-][A-Za-z0-9]+)*/g)?.length??0;
const speakerStats=[0,1,2,3].map(i=>({speaker:`Speaker ${i+1}`,slides:[i*3+1,i*3+2,i*3+3],words:speech.slice(i*3,i*3+3).reduce((n,s)=>n+words(s),0),seconds:timings.slice(i*3,i*3+3).reduce((a,b)=>a+b,0)}));
if(timings.reduce((a,b)=>a+b,0)!==420||speech.reduce((n,s)=>n+words(s),0)>850)throw Error('Seven-minute speaking budget exceeded');

const p=await PresentationFile.importPptx(await FileBlob.load(path.join(root,inputRel)));
await fs.writeFile(path.join(build,'original-inspect.json'),JSON.stringify(await p.inspect({kind:'slide,shape,textbox,notes,layout',maxChars:180000}),null,2));
const layoutId=(p.layouts.items.find(l=>l.name==='Blank')??p.layouts.items[0]).id;
p.slides.keep([]);
const C={navy:'#143047',ink:'#152B3C',teal:'#087F8C',muted:'#536B7C',paper:'#F7F7F4',line:'#D8E2E6',light:'#E5EDF0',invalid:'#8C9DA8',amber:'#C79034',white:'#FFFFFF'};
function txt(slide,name,text,left,top,width,height,size=24,color=C.ink,bold=false){
 const s=slide.shapes.add({name,geometry:'textbox',position:{left,top,width,height},fill:'none',line:{fill:'none',width:0}});
 s.text=text;s.text.style={typeface:'Arial',fontSize:size,color,bold};return s;
}
function base(index,subtitle='',foot=''){
 const s=p.slides.add({layoutId,background:{fill:C.paper}});
 txt(s,'section',sections[index].toUpperCase(),64,30,1050,25,14,C.teal,true);
 txt(s,'headline',titles[index],64,78,1152,64,36,C.ink,true);
 const wrap=(copy,length)=>copy.split('\n').map(line=>{const rows=[];let row='';for(const word of line.split(' ')){if(row&&row.length+word.length+1>length){rows.push(row);row=word;}else row+=(row?' ':'')+word;}if(row)rows.push(row);return rows.join('\n');}).join('\n');
 if(subtitle)txt(s,'subtitle',wrap(subtitle,104),64,145,1152,65,23,C.muted);
 if(foot)txt(s,'scope',wrap(foot,122),64,640,1010,51,15,C.muted);
 txt(s,'speaker',`Speaker ${Math.floor(index/3)+1}    ${String(index+1).padStart(2,'0')}`,1080,675,144,22,14,C.muted);
 const cue=index===10?'Open the preloaded Dashboard, saved failure and saved before/after tabs. Pause for clicks.':index===11?'State the limits and concrete next steps. End without reading the references.':'Explain the finding rather than reading every number.';
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
   const cell=t.getCell(r,c);cell.fill=r===0?C.navy:r%2?C.white:C.paper;
   cell.text.style={typeface:'Arial',fontSize:r===0?headerSize:fontSize,color:r===0?C.white:C.ink,bold:r===0};
  }
 }
 return t;
}
function bar(s,categories,series,max,{top=225,height=320,width=1125,left=64}={}){
 const chart=s.charts.add('bar',{position:{left,top,width,height},categories,series,barOptions:{direction:'bar',grouping:'stacked',gapWidth:80,overlap:100},hasLegend:true,legend:{position:'bottom',textStyle:{fontSize:19,fill:C.ink}},xAxis:{visible:true,min:0,max,majorUnit:max===40?10:4,numberFormatCode:'0',textStyle:{fontSize:21,fill:C.ink},majorGridlines:null,line:{fill:'none',width:0}},yAxis:{visible:true,min:0,max,majorUnit:max===40?10:4,numberFormatCode:'0',textStyle:{fontSize:19,fill:C.muted},majorGridlines:{fill:C.line,width:0.8},line:{fill:C.line,width:0.8}},dataLabels:{showValue:true,position:'center',numberFormatCode:'0',textStyle:{fontSize:24,bold:true,fill:C.white}},chartFill:'none',chartLine:{fill:'none',width:0},plotAreaFill:'none',plotAreaLine:{fill:'none',width:0}});
 applyPresentationChartFont(chart,{fontFamily:'Arial'});return chart;
}

// 1: introduction. The reference's colour, dimensions and typography remain.
{
 const s=base(0);s.background.fill=C.navy;
 const section=s.shapes.items.find(x=>x.name==='section');section.text='ELEC5623   GROUP 2';section.text.style={typeface:'Arial',fontSize:14,color:'#78DAD0',bold:true};
 const title=s.shapes.items.find(x=>x.name==='headline');title.text='AI Memory\nHealth Auditor';title.position={left:82,top:146,width:1100,height:160};title.text.style={typeface:'Arial',fontSize:57,color:C.white,bold:true};
 txt(s,'purpose','A web app for testing how AI uses remembered information',84,340,1080,88,30,'#D3E5ED');
 txt(s,'problem','Wrong facts. Old information. Conflicts. Wrong context.',84,466,1080,80,26,'#B6D0DE');
 const speaker=s.shapes.items.find(x=>x.name==='speaker');speaker.text.style={typeface:'Arial',fontSize:14,color:'#B6D0DE'};
}
// 2: motivation with accessible terminology.
{
 const s=base(1,'A stored memory can still lead to the wrong answer.','Illustrative examples explain the four abilities; they are not experimental observations.');
 const rows=[['Accuracy','Recall the right fact.'],['Freshness','Respect an explicit update.'],['Conflict resolution','Handle records that disagree.'],['Appropriate use','Apply the rule for the current task.']];
 rows.forEach((r,i)=>{txt(s,`risk-${i}`,r[0],78,230+i*76,360,54,28,C.teal,true);txt(s,`meaning-${i}`,r[1],450,230+i*76,740,54,28);});
 txt(s,'example','Example: a Python preference does not change a Java assignment.',78,554,1110,62,26,C.ink,true);
}
// 3: contributions, not a generic chatbot pitch.
{
 const s=base(2,'Personalised tests with source evidence and controlled repair comparisons.','Prototype scope: a controlled memory-enabled target, with explicit human confirmation.');
 [['01','Human-confirmed memories','Accept, correct or reject facts while keeping their sources.'],['02','Grounded behavioural tests','Check recall, updates, conflicts and context in actual answers.'],['03','Traceable repair evidence','Inspect failures and repeat frozen questions after a change.']].forEach((r,i)=>{
  const y=238+i*120;txt(s,`n-${i}`,r[0],74,y,78,66,38,C.teal,true);txt(s,`contribution-${i}`,r[1],174,y,1000,48,30,C.ink,true);txt(s,`detail-${i}`,r[2],174,y+48,1000,58,24,C.muted);
 });
}
// 4: related work, accurate modest positioning.
{
 const s=base(3,'Memory infrastructure and evaluation benchmarks provide complementary foundations.','Sources: Mem0 (Chhikara et al., 2025) and LongMemEval (Wu et al., ICLR 2025).');
 table(s,'related',[['Existing work','Main focus'],['Mem0','Extract, consolidate and retrieve memories for AI agents.'],['LongMemEval','Evaluate long-term memory with curated questions and histories.']],[320,830],{top:230,height:250,fontSize:26});
 txt(s,'gap-title','Our focus',78,510,1060,45,28,C.teal,true);
 txt(s,'gap','One user-facing workflow combines confirmed facts, personalised tests,\nfailure evidence and before/after repair comparisons.',78,558,1110,72,25);
}
// 5: runtime methodology, separate from independent research reviewers.
{
 const s=base(4,'GenAI proposes and judges. People confirm facts. Code enforces the workflow.','React frontend, FastAPI backend, persisted sources, settings, answers and judgments.');
 table(s,'pipeline',[['Stage','Component','Saved output'],['1  Import','User authorisation','Original messages'],['2  Extract','GenAI extraction and relationship agents','Candidate facts and links'],['3  Confirm','Human ground-truth review','Approved or corrected facts'],['4  Test','GenAI generation and code checks','Questions and evidence'],['5  Assess','Controlled target and evaluator','Answers, scores and reasons']],[200,510,440],{top:215,height:390,fontSize:22,headerSize:20});
}
// 6: research design and objectivity, including the external benchmark.
{
 const s=base(5,'Measure question validity, Auditor reliability and target performance separately.','Controlled retests freeze inputs and record settings. Reused cases and AI-assisted review still limit independence.');
 table(s,'experiments',[['Study','What changes','What stays fixed'],['A  Audit methods','Direct, template or contextual questions','Histories, target and test budget'],['B  Four strategies','Memory retrieval policy','Model, histories and frozen questions'],['C  External check','Policy results on LongMemEval subset','Cases and settings within C']],[235,440,475],{top:220,height:280,fontSize:23});
 txt(s,'safeguards-title','How we reduce bias',78,523,1000,38,25,C.teal,true);
 txt(s,'safeguards','Independent source checks. Human verification. Judges omit policy names.\nKeep failed runs, disagreements, uncertainty and negative findings',78,568,1110,66,24);
}
// 7: all planned slots retained; first-pass and revision judgments separate.
{
 const s=base(6,'Same ten original histories and 40 planned question slots per condition.','Related development histories. Human-checked AI reviews. Six relationship labels remain unresolved.');
 bar(s,['Original','After repair and review'],[
  {name:'Valid',values:[14,40],fill:C.teal},
  {name:'Invalid',values:[14,0],fill:C.invalid,dataLabelOverrides:[{idx:1,showValue:false}]},
  {name:'Not generated',values:[12,0],fill:C.amber,dataLabelOverrides:[{idx:1,showValue:false}]}
 ],40,{top:225,height:285});
 txt(s,'revision','First review: 38 valid, 2 uncertain. We regenerated both questions.',78,535,1120,50,26,C.ink,true);
 txt(s,'execution','Current suite: 40 valid after review. All 40 returned answers and assessments.',78,585,1120,48,23,C.muted);
}
// 8: a table preserves different denominators rather than pooling accuracy.
{
 const s=base(7,'Same 118 human-consensus answers, from 120 reviewed answers across 30 related histories.','Two human disagreements excluded. AI-assisted reference checks. Revised scorer is an optional reassessment.');
 table(s,'scorer',[['Measure','Earlier scorer','Revised scorer'],['Failure detection','55/68   80.9%','61/68   89.7%'],['Correct type among\ndetected failures','0/55 classified','54/61   88.5%'],['False positives among\nhuman-pass answers','18/50','0/50 observed']],[550,300,300],{top:220,height:300,fontSize:26});
 txt(s,'interval','Detection-change interval: -5.4 to +23.2 percentage points.',78,550,1120,44,25,C.muted);
 txt(s,'inference','The interval includes zero. We cannot claim a statistically clear detection gain.',78,596,1120,42,23,C.ink,true);
}
// 9: one table explains the four policies and displays separate study outcomes.
{
 const s=base(8,'Target answers passed. B and C use different models and datasets.','B: 3 paired histories, 12 questions per strategy, one run. Overall: 52/64 answers saved.\nC: 2 reused LongMemEval cases, 3 repeats. Exploratory subset, not official benchmark scores.');
 table(s,'strategies',[['Memory strategy','How it selects memories','B: Astra\nsynthetic','C: Luna\nLongMemEval'],['First-match retrieval','Take the first relevant record.','3/12','0/6'],['Relationship-priority\nretrieval','Use update and relationship priorities.','3/12','3/6'],['Match the task\nand project','Select the relevant task and project.','0/12','0/6'],['Consider time\nand importance','Rank by relevance, time and importance.','0/12','1/6']],[310,430,205,205],{top:215,height:340,fontSize:22,headerSize:20,paddingY:6});
 txt(s,'strategy-conclusion','Relationship-priority tied in B and led in C. No universal winner.',78,596,1120,42,26,C.ink,true);
}
// 10: the tutor's diagnose-repair-retest chain, with real paired outcomes.
{
 const s=base(9,'Missing venue facts in the target store motivated a structured memory writer.','Four related synthetic histories, same 16 questions. Human-checked AI-assisted judgments; limited development evidence.');
 bar(s,['Before writer repair','After writer repair'],[
  {name:'Passed',values:[12,16],fill:C.teal},
  {name:'Failed',values:[4,0],fill:C.invalid,dataLabelOverrides:[{idx:1,showValue:false}]}
 ],16,{top:225,height:280});
 txt(s,'repair-takeaway','12/16 passed before. 16/16 after. Four improved, none worsened.',78,530,1120,64,30,C.teal,true);
 txt(s,'repair-control','Change the writer, retain the paired questions and other comparison settings.',78,591,1120,45,23,C.muted);
}
// 11: working hyperlinks to real saved product evidence; no new inference call.
{
 const s=base(10,'Use saved results to show the complete evidence chain.','Saved local results. Compare automatic judgments with the separately human-checked aggregate on slide 10.');
 const steps=[['1','Dashboard','Find question quality, Auditor judgments and strategy results.','http://localhost:5173/'],['2','One failed answer','Inspect the source fact, response and target memory trace.','http://localhost:5173/audits/RUN1FDDFC16B9F0406E9AD4B1CE6945E081'],['3','Before and after','Inspect the same question after the memory-writer repair.','http://localhost:5173/compare?before=RUN1FDDFC16B9F0406E9AD4B1CE6945E081&after=RUN22924F327B0F4D00AB920E69C55542CF']];
 steps.forEach((r,i)=>{const y=232+i*123;txt(s,`demo-n-${i}`,r[0],78,y,64,60,39,C.teal,true);const title=txt(s,`demo-link-${i}`,r[1],175,y,990,47,30,C.teal,true);title.text.get(r[1]).link={uri:r[3],isExternal:true};txt(s,`demo-detail-${i}`,r[2],175,y+51,990,65,24);});
}
// 12: limits and future development get equal space in the closing message.
{
 const s=base(11,'Tested cases support the workflow. Broader reliability needs more evidence.','A also showed no method advantage: each historical method found 3/9 inventoried defects. Negative results remain part of the evidence.');
 table(s,'future',[['Current limitation','Next research or product step'],['Mostly related synthetic histories\nand small benchmark subsets','Use new diverse histories and larger\nLongMemEval subsets with frozen protocols.'],['AI-assisted review and\nsix unresolved relationship labels','Strengthen blind reference review\nand improve source/relationship checks.'],['No consistent method or policy winner\nand limited repeat evidence','Run broader repeated controlled comparisons.\nImprove review usability and cost reporting.']],[520,630],{top:220,height:330,fontSize:24,headerSize:22});
 txt(s,'closing','The key result: inspectable evidence can guide a tested repair.',78,583,1120,50,28,C.teal,true);
}

if(p.slides.items.length!==12)throw Error('Exactly twelve slides are required for this outline');
const inspect=await p.inspect({kind:'slide,textbox,shape,table,chart,notes,layout',maxChars:220000});
await fs.writeFile(path.join(build,'final-inspect.json'),JSON.stringify(inspect,null,2));
for(let i=0;i<p.slides.items.length;i++){
 const s=p.slides.items[i];
 await fs.writeFile(path.join(build,`slide-${String(i+1).padStart(2,'0')}.png`),new Uint8Array(await(await s.export({format:'png',scale:1})).arrayBuffer()));
 await fs.writeFile(path.join(build,`slide-${String(i+1).padStart(2,'0')}.layout.json`),JSON.stringify(await s.export({format:'layout'}),null,2));
}
await fs.writeFile(path.join(build,'montage.webp'),new Uint8Array(await(await p.export({format:'webp',montage:true,scale:.4})).arrayBuffer()));
const candidate=path.join(build,'candidate.pptx');await(await PresentationFile.exportPptx(p)).save(candidate);
const inputHash=await sha(path.join(root,inputRel));
const result=await finalizePresentation({workspaceDir:root,candidatePath:candidate,finalPath:output,pythonExecutable:python,integrityValidatorPath:path.join(skill,'container_tools/inspect_presentation_package_integrity.py'),layoutValidatorPath:path.join(skill,'container_tools/inspect_presentation_layout_geometry.py'),layoutArgs:['--expected-slide-size-emu','12192000,6858000','--validate-heading-fit','--validate-bullet-geometry',...[4,5,6,8,9,12].flatMap(n=>['--require-native-table-slide',String(n)])],explicitTotalSlideCount:12,requiredNativeTableOwnerSlides:[4,5,6,8,9,12],requiredNativeChartOwnerSlides:[7,10],materializeLiteralChartWorkbooks:true,fontPolicy:{basis:'reference',families:['Arial'],referencePath:path.join(root,inputRel),referenceSha256:inputHash},verifyArtifactToolImport:true,receiptPath:path.join(build,'validation.json')});
const sourceFiles=[ac2Path,ac3Path,writerPath,bPath,cPath,aPath,'docs/PROPOSAL_STATUS_20261101.md','backend/app/memory_agent/store.py'];
const provenance={input:inputRel,input_sha256:inputHash,output:path.relative(root,output),output_sha256:await sha(output),source_files:Object.fromEntries(await Promise.all(sourceFiles.map(async rel=>[rel,await sha(path.join(root,rel))]))),slide_count:12,total_seconds:420,total_spoken_words:speech.reduce((n,s)=>n+words(s),0),speaker_distribution:speakerStats,sections:sections.map((section,i)=>({slide:i+1,section,title:titles[i],seconds:timings[i],spoken_words:words(speech[i])})),notes:'Speaker labels, simple-English spoken scripts, presenter cues and source/scope notes. No separate Word script.',related_work_primary_sources:['https://arxiv.org/abs/2410.10813','https://arxiv.org/abs/2504.19413'],preserved_original:true,source_verification:'C counts independently recomputed from the saved two-reviewer consensus before authoring. B/C retain separate model/sample labels. No official benchmark or universal winner claim.'};
await fs.writeFile(path.join(outDir,'presentation-provenance.json'),JSON.stringify(provenance,null,2)+'\n');
await fs.writeFile(path.join(build,'finalization-result.json'),JSON.stringify(result,null,2));
console.log(JSON.stringify({output,result,totalWords:provenance.total_spoken_words,speakers:speakerStats}));
