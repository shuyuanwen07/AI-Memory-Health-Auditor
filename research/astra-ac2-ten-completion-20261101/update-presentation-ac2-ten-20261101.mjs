/** Edit the preserved 13-slide file with the source-bound ten-scene AC2 result.
 * Original input remains unchanged. The two revised questions are development
 * revisions within forty slots, not forty first-pass automatic successes.
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
const relativeInput='research/astra-ac2-20261101/Memory-Auditor-Presentation-20261101.pptx';
const relativeOutput='research/astra-ac2-ten-completion-20261101/Memory-Auditor-Presentation-20261101-AC2-Ten-Scenes.pptx';
const input=path.join(root,relativeInput),output=path.join(root,relativeOutput);
const build=path.join(root,'.presentation-build-ac2-ten-20261101');
await fs.mkdir(build,{recursive:true});
const hash=async filename=>crypto.createHash('sha256').update(await fs.readFile(filename)).digest('hex');
const summaryRelative='output/proposal-delivery/ac2-original-ten-effective-review-analysis-20261101-v1/summary.json';
const confirmationRelative='output/proposal-delivery/ac2-original-ten-effective-review-analysis-20261101-v1/human-confirmation.json';
const summary=JSON.parse(await fs.readFile(path.join(root,summaryRelative),'utf8'));
const confirmation=JSON.parse(await fs.readFile(path.join(root,confirmationRelative),'utf8'));
if(summary.question_total!==40||summary.valid_questions!==40||summary.invalid_questions!==0||summary.uncertain_questions!==0||summary.missing!==0)throw Error('The reviewed forty-question source is incomplete');
if(confirmation.two_distinct_humans!==true||confirmation.independent!==true||confirmation.completed_by_human!==true||confirmation.review_summary_sha256!==await hash(path.join(root,summaryRelative)))throw Error('Explicit human confirmation must bind this source review');
if(summary.counts.relationships.valid!==26||summary.counts.relationships.uncertain!==6)throw Error('The six unresolved relationship labels must remain separate');
const p=await PresentationFile.importPptx(await FileBlob.load(input));
const before=await p.inspect({kind:'slide,textbox,shape,notes,layout',maxChars:200000});
const records=before.records;
if(p.slides.items.length!==13)throw Error('Preserve the thirteen slides');
function edit(slide,old,value){
 const matches=records.filter(r=>r.slideIndex===slide-1&&r.kind==='textbox'&&r.text===old);
 if(matches.length!==1)throw Error(`Expected one text match on slide ${slide}: ${old}`);
 p.resolve(matches[0].id).text=value;
}
edit(11,'AC2: product-flow question quality','AC2: questions across ten original histories');
edit(11,'Separate development studies. Denominators include every planned question slot.','Same ten source histories. Each comparison includes all 40 planned question slots.');
edit(11,'Ten-history product flow','Original product flow');
edit(11,'Latest revised source','After repair and review');
edit(11,'4 / 4 valid','40 / 40 valid');
edit(11,'Ten-history study: 14 invalid and 12 not generated.\nLatest repaired flow: 4 saved, all four accepted after AI and human review.\nOne revised history does not establish recovery across all ten.',
 'Original: 14 valid, 14 invalid, 12 missing.\nNew run: 38 valid and 2 uncertain at first review. We regenerated both.\nCurrent 40 accepted in two AI reviews, followed by two independent human checks.');
edit(11,'Previously studied synthetic sources. Planning and timeout repairs. Some prompts disclose the existence of conflict.',
 'Related development sources. Includes two post-review regenerations. Six relationship labels remain unconfirmed.');
edit(13,'Improve product-flow question quality and retrieval on long histories. Evaluate more diverse, independent cases and retain missing results.',
 'Test question generation on independent histories. Improve retrieval on long histories and retain missing results.');
const new11=`Speaker 4\nWe completed the same ten original histories through the product workflow using direct OpenAI GPT-6 Astra at its maximum reasoning setting. The original result contained fourteen valid questions, fourteen invalid questions and twelve missing slots. After repairing evidence-based planning and the chronology check for scoped instructions, all ten histories saved their four questions. Two independent Astra high reviewers judged thirty-eight questions valid and two uncertain. We used the product regeneration endpoint to revise those two questions, then the same reviewers independently checked the effective suite. All forty current questions met their four validity criteria. The user reports that two people independently checked the forty questions, sixty extracted facts and source completeness, and accepted these results. These human checks could see the AI suggestions, so we record AI-assisted human verification rather than a blind human study.\n\nThe result is forty valid current questions after feedback and two revisions. It is not a forty-out-of-forty first-pass automatic result. The histories are unchanged but previously studied and related in structure. Many prompts disclose the existence of conflict, so they test how the target handles a known conflict. Six of thirty-two automatically extracted relationship labels remain disputed or uncertain. We preserve the original graph and exclude those six from the count of confirmed-correct reference relationships. All sixty individual facts have source support. This AC2 chart measures question validity and completion, not target answer accuracy.\n\nSources and scope:\n${summaryRelative}\n${confirmationRelative}\noutput/proposal-delivery/ac2-original-ten-repaired-review-analysis-20261101-v1/summary.json\noutput/proposal-delivery/ac2-original-ten-question-revisions-20261101-v1/summary.json\noutput/proposal-delivery/ac2-original-ten-effective-cohort-20261101-v1/protocol.json\nfrontend/public/reports/ac2-astra-ten-source-v1.json\nOriginal ten IDs: prospective-01, 04, 07, 10, 13, 16, 19, 22, 25, 28. The earlier revised four-question pilot is separate and does not enter this comparison.`;
p.slides.items[10].speakerNotes.text=new11;
p.slides.items[10].speakerNotes.setVisible(true);
const note10=p.slides.items[9].speakerNotes.text;
p.slides.items[9].speakerNotes.text=note10+'\n\nScope distinction for the latest ten-history AC2 cohort: its separate source reviews found 60/60 supported facts and 26/32 relationships agreed correct, with six relationship labels excluded from confirmed-correct counts. The four-history AC1 pilot on this slide remains a separate study. See '+summaryRelative+' and '+confirmationRelative+'.';
const note13=p.slides.items[12].speakerNotes.text;
p.slides.items[12].speakerNotes.text=note13+'\n\nLatest AC2 follow-up: the same ten original sources now retain forty valid current questions after two post-review regenerations. This is a development repair result with user-reported independent human verification of AI-assisted reviews. Six automatic relationship labels remain outside the confirmed-correct count. Independent histories and unattended first-pass question generation still need further evaluation. Sources: '+summaryRelative+'; '+confirmationRelative+'.';
await fs.writeFile(path.join(build,'after-inspect.json'),JSON.stringify(await p.inspect({kind:'slide,textbox,shape,notes,layout',maxChars:200000}),null,2));
for(let i=0;i<p.slides.items.length;i++){
 await fs.writeFile(path.join(build,`after-${i+1}.png`),new Uint8Array(await(await p.slides.items[i].export({format:'png',scale:1})).arrayBuffer()));
 await fs.writeFile(path.join(build,`after-${i+1}.layout.json`),JSON.stringify(await p.slides.items[i].export({format:'layout'}),null,2));
}
const candidate=path.join(build,'candidate.pptx');
await(await PresentationFile.exportPptx(p)).save(candidate);
const inputHash=await hash(input);
const result=await finalizePresentation({workspaceDir:root,candidatePath:candidate,finalPath:output,pythonExecutable:python,integrityValidatorPath:path.join(skill,'container_tools/inspect_presentation_package_integrity.py'),layoutValidatorPath:path.join(skill,'container_tools/inspect_presentation_layout_geometry.py'),layoutArgs:['--expected-slide-size-emu','12192000,6858000','--validate-heading-fit','--validate-bullet-geometry'],explicitTotalSlideCount:13,requiredNativeTableOwnerSlides:[],requiredNativeChartOwnerSlides:[],fontPolicy:{basis:'reference',families:['Arial'],referencePath:input,referenceSha256:inputHash},verifyArtifactToolImport:true,receiptPath:path.join(build,'validation.json')});
await fs.writeFile(path.join(build,'finalization-result.json'),JSON.stringify(result,null,2));
const sources=[summaryRelative,confirmationRelative,'output/proposal-delivery/ac2-original-ten-repaired-review-analysis-20261101-v1/summary.json','output/proposal-delivery/ac2-original-ten-question-revisions-20261101-v1/summary.json','output/proposal-delivery/ac2-original-ten-effective-cohort-20261101-v1/protocol.json'];
await fs.writeFile(path.join(root,'research/astra-ac2-ten-completion-20261101/presentation-provenance-20261101.json'),JSON.stringify({original:relativeInput,original_sha256:inputHash,output:relativeOutput,output_sha256:await hash(output),source_files:Object.fromEntries(await Promise.all(sources.map(async rel=>[rel,await hash(path.join(root,rel))]))),slide_count:13,speaker_scripts:'Embedded in slide notes, Speaker 1–4; no separate Word script',changed_visible_slides:[11,13],changed_notes_slides:[10,11,13],authoring_source:'research/astra-ac2-ten-completion-20261101/update-presentation-ac2-ten-20261101.mjs',limitations:'Forty current valid questions after two actual regenerations, not first-pass automatic success. Related development sources. Six relationship labels remain outside the confirmed-correct count. Human verification is user-reported, AI-assisted, and not an independently authenticated blind human study. AC2 validity is separate from target answer accuracy.'},null,2)+'\n');
console.log(JSON.stringify({output,result}));
