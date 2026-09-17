"""Run one prepared Metal job with sampled process-tree RSS and time limits.

macOS/Linux `ps` is required. RSS sums can double-count shared pages; sampling
can miss short peaks. This is a practical bound, not a peak-memory guarantee.
"""
import argparse
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('job_directory',type=Path)
    parser.add_argument('--backend',choices=['hornlab-metal-f32','hornlab-metal'],default='hornlab-metal-f32')
    parser.add_argument('--rss-limit-gib',type=float,default=22.)
    parser.add_argument('--timeout-seconds',type=float,default=600.)
    args=parser.parse_args()
    if not 0<args.rss_limit_gib<10000 or not 0<args.timeout_seconds<86400:
        parser.error('Resource limits must be positive and finite')
    out=args.job_directory.resolve()
    if not (out/'bem-job.json').is_file():parser.error('Run prepare-bem first')
    if (out/'resource-check.json').exists() or (out/'solve.log').exists():parser.error('Guarded attempt already exists; use a new job directory')
    command=[sys.executable,'-m','concord.cli','solve',str(out/'bem-job.json'),'--backend',args.backend]
    start=time.monotonic();peak=0;reason=None
    with (out/'solve.log').open('w') as log:
        p=subprocess.Popen(command,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
        try:
            while p.poll() is None:
                rows=[tuple(map(int,line.split())) for line in subprocess.check_output(
                    ['ps','-axo','pid=,ppid=,rss='],text=True).splitlines() if line.strip()]
                family={p.pid}
                while True:
                    new=family|{pid for pid,parent,rss in rows if parent in family}
                    if new==family:break
                    family=new
                rss=sum(rss*1024 for pid,parent,rss in rows if pid in family);peak=max(peak,rss)
                if rss>args.rss_limit_gib*2**30 or time.monotonic()-start>args.timeout_seconds:
                    reason='RSS limit' if rss>args.rss_limit_gib*2**30 else 'time limit'
                    break
                time.sleep(2)
        except BaseException as exc:
            reason=f'Interrupted: {type(exc).__name__}'
            raise
        finally:
            if p.poll() is None:
                os.killpg(p.pid,signal.SIGTERM)
                try:p.wait(timeout=10)
                except subprocess.TimeoutExpired:os.killpg(p.pid,signal.SIGKILL)
            code=p.wait()
            report=dict(exit_code=code,stopped_reason=reason,peak_sampled_process_tree_rss_gib=peak/2**30,
                seconds=time.monotonic()-start,rss_limit_gib=args.rss_limit_gib,timeout_seconds=args.timeout_seconds,
                measurement='2-second sampled sum of process-tree RSS; shared pages can be counted more than once')
            (out/'resource-check.json').write_text(json.dumps(report,indent=2)+'\n')
            print(json.dumps(report),flush=True)
    return 0 if code==0 and reason is None else 2


if __name__=='__main__':sys.exit(main())
