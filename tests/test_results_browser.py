import importlib.util
import json
from pathlib import Path
from threading import Thread
from urllib.error import HTTPError
from urllib.request import urlopen
import pytest

spec=importlib.util.spec_from_file_location('results_browser',Path(__file__).parents[1]/'scripts/results_browser.py')
browser=importlib.util.module_from_spec(spec);spec.loader.exec_module(browser)


def write(path,value):
    path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(value))


def test_scan_refresh_partial_and_cache_exclusion(tmp_path):
    write(tmp_path/'run/response.json',dict(analysis_status='mesh_converged',frequencies_hz=[500,2000]))
    write(tmp_path/'.concord-cache/entry/response.json',{})
    write(tmp_path/'run/reference/reference-check.json',{'passed':True})
    c=browser.Catalogue(tmp_path);rows=c.scan()['rows']
    assert len(rows)==2
    r=next(r for r in rows if r['path']=='run');assert r['completed_at'] and r['status']=='mesh_converged'
    (tmp_path/'run/response.json').write_text('{')
    r=next(r for r in c.scan()['rows'] if r['path']=='run');assert r['errors'] and not r['completed_at']
    write(tmp_path/'run/response.json',{'analysis_status':'reference_validated'})
    r=next(r for r in c.scan()['rows'] if r['path']=='run');assert r['status']=='reference_validated'


def test_ranks_stay_separate(tmp_path):
    write(tmp_path/'campaign/campaign.json',{'generations':[{'index':0,'candidates':[{'id':'c0','parameters':{'a':1},'screening_rank':1,'screening':{'response':'c0/screening/response.json','score':{'objective':2}}}]}]})
    write(tmp_path/'campaign/c0/screening/response.json',{'analysis_status':'reference_validated'})
    row=next(r for r in browser.Catalogue(tmp_path).scan()['rows'] if r['path'].endswith('screening'))
    assert row['ranking']['stage']=='screening' and row['ranking']['rank']==1
    assert row['kind']=='screening' and row['status']=='reference_validated'


def test_safe_paths(tmp_path):
    c=browser.Catalogue(tmp_path)
    for name in ['../secret','/etc/passwd','.concord-cache/key']:
        with pytest.raises(ValueError):c.safe(name)
    (tmp_path/'link').symlink_to('/etc')
    with pytest.raises(ValueError):c.safe('link/passwd')


def test_http_readonly_and_confined(tmp_path):
    write(tmp_path/'run/response.json',{'analysis_status':'mesh_converged'})
    (tmp_path/'run/viewer.html').write_text('<h1>saved viewer</h1>')
    with browser.server(tmp_path,0) as server:
        worker=Thread(target=server.serve_forever,daemon=True);worker.start()
        base=f'http://127.0.0.1:{server.server_port}'
        try:
            assert b'Follow latest completed solve' in urlopen(base+'/?follow=1').read()
            assert len(json.load(urlopen(base+'/api/index'))['rows'])==1
            assert 'response.json' in json.load(urlopen(base+'/api/detail?path=run'))['documents']
            assert b'saved viewer' in urlopen(base+'/files/run/viewer.html').read()
            with pytest.raises(HTTPError):urlopen(base+'/files/%2e%2e/secret')
            with pytest.raises(HTTPError):urlopen(base+'/api/index',data=b'write')
        finally:server.shutdown();worker.join()
