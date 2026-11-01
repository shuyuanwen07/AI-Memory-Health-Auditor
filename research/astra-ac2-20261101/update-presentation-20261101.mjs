/** Update the preserved 13-slide presentation with source-bound 1 November results.
 * Requires the bundled @oai/artifact-tool runtime. Set ARTIFACT_RUNTIME_MODULES,
 * PRESENTATIONS_SKILL_DIR and ARTIFACT_PYTHON for a different runtime location.
 * Original input is read-only. Outputs use a new dated path and are validated.
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
const {finalizePresentation}=await import(pathToFileURL(path.join(skill,'container_tools/artifact_tool_utils.mjs')));
const input=path.join(root,'research/full-project-backup-20261029/Memory-Auditor-Presentation-20261030.pptx');
const build=path.join(root,'.presentation-build-20261101');
const output=path.join(root,process.env.PRESENTATION_OUTPUT??'research/astra-ac2-20261101/Memory-Auditor-Presentation-20261101.pptx');
await fs.mkdir(build,{recursive:true});
const p=await PresentationFile.importPptx(await FileBlob.load(input));
const original=await p.inspect({kind:'shape,textbox,notes,layout',maxChars:100000});
const records=original.records;
function edit(slide,old,value){
 const matches=records.filter(r=>r.slideIndex===slide-1&&r.kind==='textbox'&&r.text===old);
 if(!matches.length)throw Error(`Missing slide ${slide} text: ${old}`);
 for(const r of matches)p.resolve(r.id).text=value;
}
function bar(slide,top,fraction){
 const matches=records.filter(r=>r.slideIndex===slide-1&&r.kind==='shape'&&r.fillColor==='#087F8C'&&r.position.left===520&&r.position.top===top);
 if(matches.length!==1)throw Error(`Ambiguous bar ${slide}/${top}`);
 const r=matches[0],s=p.resolve(r.id);s.position={...r.position,width:Math.max(0.01,510*fraction)};
 if(fraction===0)s.fill='none';
}
function text(slide,name,copy,top,height=70,fontSize=18){
 const s=p.slides.items[slide-1].shapes.add({name,geometry:'textbox',position:{left:70,top,width:1140,height},fill:'none',line:{fill:'none',width:0}});
 s.text=copy;s.text.style={typeface:'Arial',fontSize,color:'#536B7C'};
}
edit(5,'A: all methods found the same known defects','A: three methods exposed failed answers');
edit(5,'Each method detected 3 of 9 predefined defect IDs.','Each method produced 5 passes and 11 failed answers across four scenarios.');
edit(5,'3 / 9','5 / 16 passed');for(const top of [253,343,433])bar(5,top,5/16);
edit(5,'No advantage for contextual questions was demonstrated in this sample.','The methods tied. Failed answers identify problems in the tested target.');
edit(5,'3 related synthetic histories · 36 answers · 18 failed answers outside the frozen defect inventory.','4 related synthetic histories. Single human reference after AI review. These counts do not measure Auditor accuracy.');
edit(6,'B: four strategies on the same histories','B: four memory strategies with Astra');
edit(6,'Human-consensus passes across 36 answers per strategy.','Same 12 questions per strategy across three complete paired histories.');
edit(6,'9 / 36  ·  25%','3 / 12   25%');edit(6,'27 / 36  ·  75%','3 / 12   25%');
// The last row shared the old text with the second row. Correct it explicitly.
const lastB=records.find(r=>r.slideIndex===5&&r.kind==='textbox'&&r.position.top===469);p.resolve(lastB.id).text='0 / 12   0%';
edit(6,'18 / 36  ·  50%','0 / 12   0%');[223,308,393,478].forEach((top,i)=>bar(6,top,[.25,.25,0,0][i]));
edit(6,'3 previously used synthetic histories · 3 repeats per history · repeated answers are related.','52/64 answers saved overall, 12 missing. Paired chart excludes the incomplete fourth history. Human-checked AI reviews.');
text(6,'b-conclusion','No relationship-priority advantage in this Astra sample. One run per strategy.',550,54,20);
edit(7,'C: four strategies on selected benchmark cases','C: latest saved benchmark plan');
edit(7,'Human-adjudicated pass rate among decided answers.','GPT-6 Luna via OpenRouter. Two reused cases, three repeats per strategy.');
for(const [old,value] of [['17 / 87  ·  19.5%','0 / 6   0%'],['57 / 81  ·  70.4%','3 / 6   50%'],['47 / 84  ·  56.0%','0 / 6   0%'],['50 / 84  ·  59.5%','1 / 6   16.7%']])edit(7,old,value);
[223,308,393,478].forEach((top,i)=>bar(7,top,[0,.5,0,1/6][i]));
edit(7,'30 selected LongMemEval cases · 3 repeats · 24 uncertain answers excluded from decided denominators.','Human-review consensus. Two previously used cases. Repeats reuse cases. Exploratory check, without an official score.');
text(7,'c-astra-separate','Separate Astra development check: capacity 50, 0/4 passed. Capacity 500, 0/3 passed and 1 request missing. No observed improvement on these two cases.',540,82,18);
edit(9,'Auditor scoring improved on the same answers','Auditor judgments on the same answers');
edit(9,'Old scorer → new scorer','Before and after');
text(9,'detection-uncertainty','Failure-detection difference interval: −5.4 to 23.2 percentage points. It includes zero improvement.',545,65,19);
edit(10,'AC1: relation matching improved, fact matching fell','AC1: source-only extraction with Astra');
edit(10,'Paired comparison on the 27 histories completed in both runs.','Four related synthetic histories, checked against their source messages.');
edit(10,'REFERENCE RELATIONSHIP IDs','SOURCE-SUPPORTED CANDIDATES');edit(10,'58 / 80   to   79 / 80','30 / 30 candidates');edit(10,'72.5% to 98.8%','12 / 12 extracted relationships correct');
edit(10,'REFERENCE FACT IDs','REFERENCE RECORD COVERAGE');edit(10,'212 / 215   to   205 / 215','32 / 32 records');edit(10,'98.6% to 95.3%','12 / 12 reference relationships covered');
edit(10,'ID matches can be partial; six human-reviewed relations have disputed meanings. Three incomplete histories are excluded.','Reference records can combine several facts, and several candidates can cover one record. Record coverage does not establish atomic fact recall.');
edit(10,'Selected synthetic histories · reviewed reference is not exhaustive · ID matching is not strict recall.','Two independent AI reviews, followed by user-reported independent checks by two people. Previously studied sources.');
edit(11,'AC2: more valid questions, but many remain invalid','AC2: product-flow question quality');
edit(11,'Both versions were reviewed against the same selected histories.','Separate development studies. Denominators include every planned question slot.');
edit(11,'Earlier generator','Ten-history product flow');edit(11,'50 / 111  ·  45.0%','14 / 40 valid');bar(11,258,14/40);
edit(11,'Newer generator','Latest revised source');edit(11,'62 / 117  ·  53.0%','4 / 4 valid');bar(11,358,1);
edit(11,'55 / 117 newer questions were invalid; 38 passed the old gate.\nA later two-person recheck changed one question in each group.\nSource review requests help, but do not guarantee valid questions.','Ten-history study: 14 invalid and 12 not generated.\nLatest repaired flow: 4 saved, all four accepted after AI and human review.\nOne revised history does not establish recovery across all ten.');
edit(11,'30 related synthetic histories · retrospective replay, not independent validation.','Previously studied synthetic sources. Planning and timeout repairs. Some prompts disclose the existence of conflict.');
edit(12,'A four-history development pilot illustrates the complete workflow.','A missing-memory diagnosis led to a controlled writer comparison.');
edit(12,'Missing facts','Missing venue records');edit(12,'Inspect answer-time evidence to identify the retrieval problem.','Inspect the answer and memory trace. The venue facts were absent from the target store.');
edit(12,'Change retrieval','Structured writer');edit(12,'Try a targeted retrieval policy for the same task.','Change how the target writes memories while retaining the paired test conditions.');
edit(12,'Same questions','Same 16 questions');
edit(12,'Update-history answers: 0 / 4 before → 4 / 4 after','12 / 16 passed before, 16 / 16 after. Four improved, none worsened.');
edit(12,'4 related synthetic histories · AI-assisted human review · development pilot, not general proof.','4 related synthetic histories. Human-checked AI reviews. Development comparison, without a population-wide claim.');
edit(13,'The Auditor can expose and compare failures. Its newer scorer improved on the selected paired sample.','The Auditor exposes failures and traces their causes. A targeted writer repair improved answers on the same test suite.');
edit(13,'Improve question quality and source coverage. Resolve interpretation differences; test on more diverse, independent histories.','Improve product-flow question quality and retrieval on long histories. Evaluate more diverse, independent cases and retain missing results.');
edit(13,'A did not establish a method advantage · repeated cases are related · C covers a selected subset.','A did not establish a method advantage. B and C depend on the selected model, cases and memory configuration.');
const scripts=[
`Speaker 1\nOur project is the AI Memory Health Auditor. We test how an AI uses remembered information, preserve the evidence behind failures, and check whether a targeted repair improves its answers. We will explain the workflow, compare audit methods and memory strategies, and demonstrate a diagnosis followed by a controlled retest.`,
`Speaker 1\nConsider an assistant that remembers a preference for Python. A particular project then requires Java. Both facts can be correct, but the assistant must apply the project requirement in that project. This is why storage accuracy alone is insufficient. Our four abilities cover recalling facts, respecting updates, handling unresolved conflicts, and applying information within its proper context. The example here explains the problem rather than reporting an experimental result.`,
`Speaker 1\nThe system imports an authorised conversation and extracts candidate facts with relationships between them. A person can inspect and confirm those records before the target answers any audit questions. GenAI components assist extraction, test generation and assessment. Each report links the source, question, expected behaviour, actual answer and assessment. In our experiments, scripted confirmation simulated the operator step where stated, followed by separately recorded reviews. Completed audits and new experiment groups feed the Dashboard automatically.`,
`Speaker 2\nOur three experiments answer distinct questions. A compares three testing methods under the same question budget. B holds the questions fixed and compares four memory strategies. C uses selected LongMemEval cases as an external check. We also validate the Auditor itself against reviewed reference judgments. A poor target answer and an incorrect Auditor judgment are different outcomes, so their denominators and evidence remain separate.`,
`Speaker 2\nThe latest A campaign covers four synthetic scenarios. Each method generated sixteen answers, with five passes and eleven failures according to the saved human reference. The tie means we cannot claim that contextual questions outperform the alternatives. The failures still provide material to inspect and repair. These are failures of the tested target answers, rather than eleven errors by the Auditor. The system exposes this campaign as single-human reference data after AI review, rather than presenting it as blind two-person consensus.`,
`Speaker 2\nFor the latest Astra comparison, we have twelve shared questions across three complete histories for each strategy. First-match and Relationship-priority each passed three. The task-and-project and time-and-importance strategies passed none. We saved fifty-two of sixty-four planned answers overall, but excluded the incomplete fourth history from this paired chart. Two independent Astra high reviews received subsequent independent human checks, as the user reported. This sample shows no Relationship-priority advantage. It also shows why a stronger model or a more elaborate policy cannot be assumed to improve every memory task.`,
`Speaker 3\nThe latest saved C plan uses GPT-6 Luna through OpenRouter on two previously used knowledge-update cases from our archived LongMemEval selection, repeated three times. Relationship-priority passed three of six answers, time-and-importance passed one, and the other two strategies passed none. The six answers reuse two cases, so they do not represent six independent problems. A separate Astra development comparison increased memory capacity from fifty to five hundred. All four old answers and all three completed new answers failed review. The fourth new request is missing. We therefore observed no capacity-only improvement on those two cases.`,
`Speaker 3\nMem0 provides memory storage and retrieval for AI applications. LongMemEval evaluates abilities involving long-term conversational memory. Our contribution connects a reviewed source to audit questions, failure evidence and an explicit repair comparison. We aim to explain which recorded information caused or failed to support an answer. The Dashboard also preserves negative and missing outcomes, so a favourable example cannot silently replace the full experimental record.`,
`Speaker 3\nWe compared two scorers on the same saved answers, using one hundred and eighteen answers with agreed human labels. Failure detection rose from fifty-five to sixty-one out of sixty-eight. The newer scorer assigned the correct category to fifty-four of its sixty-one detected failures. False positives fell from eighteen of fifty agreed passes to zero. These are descriptive results on selected synthetic histories. The interval for the detection difference includes zero, and observing zero false positives does not establish zero error in the wider population.`,
`Speaker 4\nOur latest AC1 pilot uses four related synthetic histories. All thirty extracted candidates had source support. The reviewed reference records were fully covered, and all twelve selected relationships were correct. The thirty-two references can contain multiple facts, and multiple candidates can jointly cover a reference. We therefore call this record coverage rather than atomic fact recall. Two AI reviews received subsequent independent human checks according to the user.`,
`Speaker 4\nThe actual ten-history product-flow test exposed a question-quality problem: fourteen valid questions, fourteen invalid questions, and twelve planned slots without a saved question. Some references incorrectly resolved known conflicts. After repairing planning intent and request timeouts, a revised development history produced four saved questions. Both Astra high reviewers and the subsequent human checks accepted them. This is a useful repair example, but the revised source and multiple changes prevent a claim that every failure in the ten-history study is fixed.`,
`Speaker 4\nThis is our clearest complete diagnosis and retest chain. The Auditor exposed answers that lacked venue information. Inspecting the memory trace showed that the target had not stored the venue records. We changed the writer and tested both conditions on the same sixteen questions across four histories. Passes rose from twelve to sixteen, with four improvements and no regressions. In the demonstration, open the Dashboard repair result, then inspect the linked experiment's shared questions and before-and-after answers. These development results support targeted usefulness within the tested cases.`,
`Speaker 4\nThe project delivers an evidence-backed workflow for finding and investigating memory failures. The writer repair demonstrates measurable improvement on a shared test suite. Our next steps are more reliable product-flow question generation, better retrieval on long histories, and evaluation on diverse independent cases. We retain ties, failures, uncertainty and missing results because they determine the scope of the claims we can support.`
];
const sources=[
'docs/PROPOSAL_STATUS_20261101.md',
'docs/EXPERIMENT_REPORT_2026-10-28.md',
'frontend/public/reports/b-astra-four-strategy-v1.json',
'frontend/public/reports/ac1-astra-four-source-v1.json',
'frontend/public/reports/ac2-astra-ten-source-v1.json',
'frontend/public/reports/ac2-astra-comparison-v1.json',
'frontend/public/reports/c-astra-capacity-development-v1.json',
'research/astra-ac2-20261101/dashboard-latest-c-plan.json'
];
const slideSources={5:['Dashboard four-scenario campaign diverse-a-20261030-v7; saved single-human reference'],6:[sources[2]],7:['research/astra-ac2-20261101/dashboard-latest-c-plan.json. Plan CP24c3f81bba294dcc86c7977e6716977b. Cases affe2881 and ba61f0b9. First two previously used knowledge-update cases from the archived 30-case selection. Exploratory UI verification, not independent validation.',sources[6],'Historical 30-case results remain in '+sources[1]],8:['https://github.com/mem0ai/mem0','https://github.com/xiaowu0162/LongMemEval'],9:[sources[1]],10:[sources[3]],11:[sources[4],'research/astra-ac2-20261101/ac2-intent-timeout-product-retest.zip','research/astra-ac2-20261101/ac2-intent-timeout-human-confirmation.zip','Direct 30-history generation: 62/120 scheduled valid slots in the earlier condition and 120/120 in the direct Astra condition, with different generator inputs and review procedures. These are not a model-only comparison or held-out validation.'],12:[sources[5],'research/astra-ac2-20261101/four-writer-prospective-evidence.zip']};
for(let i=0;i<p.slides.items.length;i++){
 p.slides.items[i].speakerNotes.text=scripts[i]+'\n\nSources and scope:\n'+(slideSources[i+1]??sources.slice(0,2)).join('\n');
 p.slides.items[i].speakerNotes.setVisible(true);
 await fs.writeFile(path.join(build,`after-${i+1}.png`),new Uint8Array(await(await p.slides.items[i].export({format:'png',scale:1})).arrayBuffer()));
 await fs.writeFile(path.join(build,`after-${i+1}.layout.json`),JSON.stringify(await p.slides.items[i].export({format:'layout'}),null,2));
}
const inspect=await p.inspect({kind:'slide,textbox,shape,notes,layout',maxChars:100000});await fs.writeFile(path.join(build,'after-inspect.json'),JSON.stringify(inspect,null,2));
const candidate=path.join(build,'candidate.pptx');await(await PresentationFile.exportPptx(p)).save(candidate);
const inputHash=crypto.createHash('sha256').update(await fs.readFile(input)).digest('hex');
const result=await finalizePresentation({workspaceDir:root,candidatePath:candidate,finalPath:output,pythonExecutable:python,integrityValidatorPath:path.join(skill,'container_tools/inspect_presentation_package_integrity.py'),layoutValidatorPath:path.join(skill,'container_tools/inspect_presentation_layout_geometry.py'),layoutArgs:['--expected-slide-size-emu','12192000,6858000','--validate-heading-fit','--validate-bullet-geometry'],explicitTotalSlideCount:13,requiredNativeTableOwnerSlides:[],requiredNativeChartOwnerSlides:[],fontPolicy:{basis:'reference',families:['Arial'],referencePath:input,referenceSha256:inputHash},verifyArtifactToolImport:true,receiptPath:path.join(build,'validation.json')});
await fs.writeFile(path.join(build,'finalization-result.json'),JSON.stringify(result,null,2));
await fs.writeFile(path.join(root,'research/astra-ac2-20261101/presentation-provenance-20261101.json'),JSON.stringify({original: path.relative(root,input),original_sha256:inputHash,output:path.relative(root,output),source_files:Object.fromEntries(await Promise.all(sources.map(async rel=>[rel,crypto.createHash('sha256').update(await fs.readFile(path.join(root,rel))).digest('hex')]))),slide_count:13,speaker_scripts:'Embedded in slide notes, Speaker 1–4',authoring_source:'research/astra-ac2-20261101/update-presentation-20261101.mjs',limitations:'Read each slide and its notes. Separate studies and missing calls remain separate. User-reported independent human checks of AI-assisted reviews are not an independently authenticated blind human study.'},null,2)+'\n');
console.log(JSON.stringify({output,result}));
