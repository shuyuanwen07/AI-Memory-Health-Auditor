"""Pre-execution C plans and server-origin benchmark execution receipts."""
from contextlib import ExitStack
from datetime import datetime, timezone
from uuid import uuid4
from sqlalchemy import select
from fastapi import HTTPException

from app.models import AuditRunModel, BenchmarkPlanModel, TestCaseModel, TargetResponseModel
from app.schemas.benchmark_plan import BenchmarkPlanResponse
from app.schemas.domain import Dimension
from app.benchmarks.live import LiveBenchmarkRunner
from app.benchmarks.longmemeval import LongMemEvalAdapter
from app.benchmarks.runner import LongMemEvalDeterministicRunner
from app.research.ranking_agreement import RepeatedRankingService
from app.services.formal_freeze import formal_input_signature
from app.services.runtime_freeze import audit_runtime_signature
from app.services.stage_lock import database_stage_lock

fingerprint = LongMemEvalDeterministicRunner._fingerprint
NOTICE = ('Server-frozen execution metadata. Benchmark source and full responses are not retained; '
          'save returned evidence locally for scoring. A lost or interrupted response is not silently rerun. '
          'This receipt proves this server recorded the plan and dispatched calls, not reviewer independence, '
          'provider identity authenticity, prior unseen results, or an official LongMemEval score.')


def benchmark_identity(request):
    if not request.source_authorised:
        raise ValueError('Confirm source authorisation before processing the benchmark.')
    if request.include_mem0 or request.native_repair_comparison or request.provider.value not in {'ollama', 'openrouter'}:
        raise ValueError('Experiment C requires the controlled real-model Weak/Strong pair.')
    if [s.value for s in request.strategies] != ['weak_first_hit', 'strong_rule_based']:
        raise ValueError('Freeze Weak first-hit then Strong rule-based as the two benchmark conditions.')
    if request.target_memory_profile.output_token_limit is None:
        raise ValueError('Freeze an explicit output token limit for both suites.')
    cases, report = LongMemEvalAdapter().adapt(request.payload)
    if len(cases) > request.max_cases or sum(len(m.content) for c in cases for m in c.messages) > 1_000_000:
        raise ValueError('The subset exceeds its declared case or source-text budget; no cases were dropped.')
    return {'source_fingerprint_sha256': fingerprint(request.payload),
            'configuration': request.model_dump(mode='json', exclude={'payload', 'source_authorised', 'source_label'}),
            'case_ids': report.case_ids, 'adapter_version': report.adapter_version,
            'adapter_fingerprint_sha256': LongMemEvalAdapter.fingerprint_sha256(), 'runtime_signature': audit_runtime_signature()}


def checked_plan(db, plan_id):
    plan = db.get(BenchmarkPlanModel, plan_id)
    if plan is None:
        raise HTTPException(404, 'The benchmark plan was not found.')
    if fingerprint(plan.protocol) != plan.fingerprint_sha256:
        raise HTTPException(409, 'The saved benchmark plan was changed. Existing results are preserved.')
    return plan


def assert_benchmark_plan_inputs_frozen(db, audit):
    if audit is None:
        raise HTTPException(409, 'A planned audit is missing. Existing results are preserved.')
    for plan in db.scalars(select(BenchmarkPlanModel)):
        snapshots = plan.protocol.get('audit_input_fingerprints', {})
        if audit.id in snapshots:
            checked_plan(db, plan.id)
            if formal_input_signature(db, audit) != snapshots[audit.id]:
                raise HTTPException(409, 'This audit no longer matches its frozen Experiment C plan. Existing results are preserved.')


class BenchmarkPlanService:
    VERSION = 'preexecution-ranking-plan-v1'

    def view(self, db, plan_id):
        plan = checked_plan(db, plan_id)
        return BenchmarkPlanResponse(plan_id=plan.id, created_at=plan.created_at.replace(tzinfo=timezone.utc) if plan.created_at.tzinfo is None else plan.created_at,
            plan_fingerprint_sha256=plan.fingerprint_sha256, protocol=plan.protocol,
            executions=plan.executions, notice=NOTICE)

    def create(self, db, request):
        if not request.metadata_storage_authorised:
            raise ValueError('Confirm permission to save source fingerprints, licence/citation and execution metadata.')
        identity = benchmark_identity(request.benchmark)
        run_ids = sorted(r for t in request.trials for r in (t.reference_run_id, t.candidate_run_id))
        with ExitStack() as stack:
            for run_id in run_ids:
                stack.enter_context(database_stage_lock(db, run_id, 'An audit is busy; freeze the plan before execution.'))
            db.expire_all()
            runs = {r.id:r for r in db.scalars(select(AuditRunModel).where(AuditRunModel.id.in_(run_ids)))}
            if len(runs) != len(run_ids):
                raise ValueError('Every planned trial needs two existing saved audits.')
            snapshots, anchor = {}, None
            for trial in request.trials:
                for run_id, strategy in ((trial.reference_run_id,'weak_first_hit'), (trial.candidate_run_id,'strong_rule_based')):
                    run = runs[run_id]
                    if run.status != 'TESTS_GENERATED' or db.scalar(select(TargetResponseModel.id).where(TargetResponseModel.run_id==run_id).limit(1)):
                        raise ValueError('Freeze Experiment C before any target answers: every planned audit must be TESTS_GENERATED.')
                    meta = run.reproducibility_metadata or {}
                    if (run.memory_strategy != strategy or not run.experiment_id or run.target_configuration != 'strong'
                        or run.target_memory_writer != 'rule_based' or run.target_system_adapter != 'controlled-memory'
                        or run.memory_maintenance_policy != 'update_aware_consolidation'
                        or meta.get('assessment_source_run_id') or meta.get('shared_answer_source_run_id') or meta.get('intervention')):
                        raise ValueError('Use original pending Weak/Strong controlled executions from one frozen experiment.')
                    cfg = identity['configuration']
                    if ((run.provider,run.model,run.temperature,run.random_seed,run.target_memory_capacity) !=
                        (cfg['provider'],cfg['model'],cfg['temperature'],cfg['random_seed'],cfg['target_memory_capacity'])
                        or meta.get('target_memory_profile') != cfg['target_memory_profile']
                        or meta.get('audit_runtime_signature') != identity['runtime_signature']):
                        raise ValueError('Audit and benchmark model, settings, memory profile or installed software differ.')
                    tests = db.scalars(select(TestCaseModel).where(TestCaseModel.run_id==run_id)).all()
                    if len(tests)!=run.test_budget or {t.dimension for t in tests}!={d.value for d in Dimension} or any(t.quality_status!='accepted' for t in tests):
                        raise ValueError('Every planned audit needs its complete accepted four-dimensional frozen suite.')
                    from app.api.routes import test_schema
                    from app.test_generator.quality import RuleBasedTestQualityValidator
                    suite_problem = RuleBasedTestQualityValidator.validate_suite([test_schema(t) for t in tests])
                    if suite_problem:
                        raise ValueError(suite_problem)
                    suite = sorted([(t.suite_test_id or t.id,t.dimension,t.prompt,t.expected_behavior,t.supporting_memory_ids) for t in tests])
                    controls = {field:getattr(run,field) for field in ('experiment_id','conversation_id','test_budget','evaluator_provider','evaluator_model','pipeline_provider','pipeline_model','retrieval_mode','retrieval_provider','retrieval_model','target_memory_writer_version','target_system_adapter_version')}
                    comparable = {'controls':controls,'suite':suite}
                    if anchor is not None and comparable != anchor:
                        raise ValueError('All planned audits must share one exact frozen suite and assessment configuration.')
                    anchor = comparable
                    snapshots[run_id] = formal_input_signature(db,run)
                    if any(run_id in p.protocol.get('audit_input_fingerprints',{}) for p in db.scalars(select(BenchmarkPlanModel))):
                        raise ValueError('A planned audit execution already belongs to a frozen Experiment C plan.')
            protocol = {'version':self.VERSION,'benchmark':identity,'trials':[t.model_dump() for t in request.trials],
                        'sampling_rule':request.sampling_rule.strip(),'evaluator_model':request.evaluator_model.strip(),
                        'evaluator_revision':request.evaluator_revision,'audit_input_fingerprints':snapshots,
                        'planned_target_calls':len(request.trials)*2*len(identity['case_ids'])}
            plan=BenchmarkPlanModel(id='CP'+uuid4().hex,created_at=datetime.now(timezone.utc),
                fingerprint_sha256=fingerprint(protocol),protocol=protocol,executions={})
            db.add(plan)
            db.commit()
            return self.view(db,plan.id)

    def run(self, db, plan_id, request):
        with database_stage_lock(db,'benchmark-plan:'+plan_id,'This benchmark plan is already running.'):
            db.expire_all()
            plan=checked_plan(db,plan_id)
            if request.trial_id not in {t['trial_id'] for t in plan.protocol['trials']}:
                raise ValueError('Choose a trial in the saved plan.')
            if request.trial_id in plan.executions:
                raise HTTPException(409,'This trial already has an execution receipt; it cannot be silently rerun. Preserve missing evidence in the report.')
            if benchmark_identity(request.benchmark)!=plan.protocol['benchmark']:
                raise ValueError('The source, settings, adapter or software no longer match the frozen plan.')
            for run_id in plan.protocol['audit_input_fingerprints']:
                run=db.get(AuditRunModel,run_id)
                if run is None:
                    raise ValueError('A planned audit is missing; preserve this incomplete trial.')
                assert_benchmark_plan_inputs_frozen(db,run)
            state={'status':'RUNNING','started_at':datetime.now(timezone.utc).isoformat()}
            plan.executions={**plan.executions,request.trial_id:state}
            db.commit()
            try:
                result=LiveBenchmarkRunner().run(request.benchmark)
                state={**state,'status':'COMPLETED','completed_at':datetime.now(timezone.utc).isoformat(),
                       'benchmark_run_id':result.run_id,'evidence_fingerprint_sha256':fingerprint(result.model_dump(mode='json'))}
            except Exception as exc:
                plan.executions={**plan.executions,request.trial_id:{**state,'status':'FAILED','error_code':type(exc).__name__}}
                db.commit()
                raise
            plan.executions={**plan.executions,request.trial_id:state}
            db.commit()
            return result

    def analyse(self,db,plan_id,request):
        plan=checked_plan(db,plan_id)
        expected={t['trial_id']:t for t in plan.protocol['trials']}
        if request.analysis.planned_trial_ids!=list(expected):
            raise ValueError('Analysis must retain every trial in the frozen plan and its original order.')
        for trial in request.analysis.trials:
            comparison=trial.comparison
            if comparison is None:
                continue
            spec=expected[trial.trial_id]
            if (comparison.reference_run_id,comparison.candidate_run_id)!=(spec['reference_run_id'],spec['candidate_run_id']):
                raise ValueError('The supplied audit execution IDs differ from the frozen trial.')
            receipt=plan.executions.get(trial.trial_id,{})
            if receipt.get('status')!='COMPLETED':
                raise ValueError('Benchmark evidence needs a completed server execution receipt for this frozen trial.')
            for assessment in (comparison.reference_benchmark,comparison.candidate_benchmark):
                if not assessment.source_authorised:
                    raise ValueError('Confirm benchmark source authorisation before analysing it.')
                if (fingerprint(assessment.evidence.model_dump(mode='json'))!=receipt['evidence_fingerprint_sha256']
                    or assessment.evaluator_revision!=plan.protocol['evaluator_revision']
                    or any(row.autoeval_label.model!=plan.protocol['evaluator_model'] for row in assessment.rows)):
                    raise ValueError('Evidence or the evaluation standard differs from the frozen plan and server receipt.')
            for run_id in (spec['reference_run_id'],spec['candidate_run_id']):
                assert_benchmark_plan_inputs_frozen(db,db.get(AuditRunModel,run_id))
        report=RepeatedRankingService().analyse(db,request.analysis)
        report.plan_provenance='server_frozen_preexecution_plan'
        report.plan_fingerprint_sha256=plan.fingerprint_sha256
        report.notice=NOTICE+' '+report.notice.replace('The plan is caller-declared at analysis time, not a verified pre-registration or server freeze.','This analysis uses a plan saved by this server before the declared executions.')
        # Include persisted non-success states even when the caller omits their files.
        for trial in report.trials:
            if trial.status=='missing' and trial.trial_id in plan.executions:
                trial.reason='Saved benchmark execution state: '+plan.executions[trial.trial_id]['status']+'. Full evidence was not supplied.'
        return report
