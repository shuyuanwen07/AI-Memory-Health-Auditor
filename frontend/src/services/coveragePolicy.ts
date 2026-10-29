import type { TargetProvider, TestSuiteMode } from '../types/domain';
export type CoveragePolicy = 'strict_full_v1' | 'evidence_supported_only_v1';
export function effectiveCoveragePolicy(selected: CoveragePolicy, provider: TargetProvider, compareAuditors: boolean, suiteMode: TestSuiteMode): CoveragePolicy {
  return provider !== 'rule_based' && !compareAuditors && suiteMode === 'behavioural' ? selected : 'strict_full_v1';
}
