from pathlib import Path
import hashlib,json
DEFAULT_FREEZE_PATH=Path('configs/kxbtcd_candidate_e_continuous_convergence_reentry_v1_implementation_freeze.json')
EXPECTED_IMPLEMENTATION_FINGERPRINT='cf93bbdd7704ae46954feba8ce73e15a734f117a1791837d87a130e50a15764f'
class ContinuousImplementationFreezeError(RuntimeError):pass
def _fail(m):raise ContinuousImplementationFreezeError(m)
def _sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def canonical_fingerprint(d):
 b=dict(d);b.pop('implementation_fingerprint',None);return hashlib.sha256(json.dumps(b,sort_keys=True,separators=(',',':')).encode()).hexdigest()
def validate_freeze(repo_root='.'):
 repo=Path(repo_root);d=json.loads((repo/DEFAULT_FREEZE_PATH).read_text())
 if d.get('implementation_fingerprint')!=EXPECTED_IMPLEMENTATION_FINGERPRINT or canonical_fingerprint(d)!=EXPECTED_IMPLEMENTATION_FINGERPRINT:_fail('implementation fingerprint mismatch')
 for rel,h in d['implementation_files'].items():
  p=repo/rel
  if not p.is_file() or _sha(p)!=h:_fail(f'implementation file changed: {rel}')
 if not d.get('source_binding_required_before_path_run') or d.get('continuous_real_july10_paths_run_before_freeze') is not False or d.get('settlement_outcomes_accessed') is not False:_fail('freeze safety mismatch')
 return d
