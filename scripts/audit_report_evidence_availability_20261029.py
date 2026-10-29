"""Inventory report links and selected public archives without extracting them."""
from pathlib import Path
import json
import hashlib
import re
import subprocess
import tarfile

ROOT=Path(__file__).resolve().parents[1]
REPORT=ROOT/'docs/EXPERIMENT_REPORT_2026-10-28.md'
ARCHIVES=ROOT/'research/full-project-backup-20261029'

def main():
    links=list(dict.fromkeys(re.findall(r'\]\((\.\./output/[^)]+)\)',REPORT.read_text())))
    tracked=set(subprocess.check_output(['git','ls-files'],cwd=ROOT,text=True).splitlines())
    contents={}
    for path in sorted(ARCHIVES.glob('*.tar.gz')):
        with tarfile.open(path,'r:gz') as archive:
            for member in archive:
                name=member.name.removeprefix('./').rstrip('/')
                if name.startswith('output/'):
                    contents.setdefault(name,[]).append(path.name)
    rows=[]
    for link in links:
        rel=link.removeprefix('../').split('#')[0].rstrip('/')
        archives=set(contents.get(rel,[]))
        if not archives:
            for name,names in contents.items():
                if name.startswith(rel+'/'):archives.update(names)
        rows.append({'report_link':link,'local_exists':(ROOT/rel).exists(),'git_tracked':rel in tracked,
                     'selected_archives':sorted(archives)})
    out={'report':str(REPORT.relative_to(ROOT)), 'report_sha256':hashlib.sha256(REPORT.read_bytes()).hexdigest(), 'distinct_output_links':len(rows),
         'covered_by_tracked_file_or_selected_archive':sum(bool(r['git_tracked'] or r['selected_archives']) for r in rows),
         'not_found_in_selected_archives':[r for r in rows if not r['git_tracked'] and not r['selected_archives']],
         'note':'Archive membership does not make report links clickable in a fresh checkout; extract selected evidence into an empty directory. Directory coverage means at least one archived descendant, not all contents.',
         'links':rows}
    target=ARCHIVES/'report-evidence-availability.json';target.write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n')
    checksum_file = ARCHIVES/'SHA256SUMS'
    if checksum_file.exists():
        lines = checksum_file.read_text().splitlines()
        suffix = '  ' + target.name
        positions = [index for index, line in enumerate(lines) if line.endswith(suffix)]
        if len(positions) != 1:
            raise ValueError('Expected exactly one checksum entry for the evidence index')
        lines[positions[0]] = hashlib.sha256(target.read_bytes()).hexdigest() + suffix
        checksum_file.write_text('\n'.join(lines) + '\n')
    print(json.dumps({k:out[k] for k in ('distinct_output_links','covered_by_tracked_file_or_selected_archive')},indent=2))
    for row in out['not_found_in_selected_archives']:print('MISSING',row['report_link'])

if __name__=='__main__':main()
