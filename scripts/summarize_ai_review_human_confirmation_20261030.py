"""Bind subsequent user-reported human checks to the preserved AI return."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT/'output/proposal-delivery/ai-review-return-20261030-v1'


def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    original, analysis_path = RUN/'original.zip', RUN/'analysis.json'
    confirmation_path, independence_path = RUN/'human-confirmation.json', RUN/'human-independence-confirmation.json'
    analysis, confirmation, independence = (json.loads(p.read_text()) for p in (analysis_path,confirmation_path,independence_path))
    assert analysis['original_zip_sha256'] == confirmation['original_zip_sha256'] == independence['original_zip_sha256'] == sha(original)
    assert confirmation['source_analysis_sha256'] == sha(analysis_path)
    assert independence['prior_human_confirmation_sha256'] == sha(confirmation_path)
    assert confirmation['user_statement'] == '全部人工都逐一确认过'
    assert independence['user_statement'] == '分别有两名审核者独立审核'
    out = {'original_zip_sha256':sha(original), 'analysis_sha256':sha(analysis_path),
           'human_confirmation_sha256':sha(confirmation_path), 'human_independence_confirmation_sha256':sha(independence_path),
           'groups':analysis['groups'], 'differences_from_earlier_ai_consensus':analysis['ac2_differences_from_prior_ai_consensus'],
           'human_review_provenance':'User reports two human reviewers independently checked each of the 58 items in the submitted AI review archive. The original files remain explicitly AI-completed; the human checks are reported separately and identities are not independently authenticated. AI assistance is known; blindness to automated scoring or other AI suggestions is not established.',
           'limitations':'Three related development samples. The ten-item wording recheck is separate. The later confirmations do not alter earlier AI opinions, prove generalisation, or provide evidence that the two people generated independent judgments without viewing AI suggestions.'}
    (RUN/'human-confirmed-summary.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(out['groups'],ensure_ascii=False,indent=2))


if __name__=='__main__': main()
