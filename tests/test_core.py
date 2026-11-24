import json
import numpy as np
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateTable
from spectraseek.dataset import simulate, validate
from spectraseek.planning import greedy, coverage, oracle
from spectraseek.experiment import evaluate
from spectraseek.collector import parse_scan
from spectraseek.storage import metadata, SurveyRepository
from spectraseek.api import app
from spectraseek.cli import main

@pytest.fixture(scope='module')
def data(): return simulate(sessions=12,sites=6,targets=8)

def test_reproducible(data):
    assert data.equals(simulate(sessions=12,sites=6,targets=8))
    assert len(data)==576

def test_invalid_duplicate(data):
    import pandas as pd
    with pytest.raises(ValueError,match='Duplicate'): validate(pd.concat([data,data.iloc[:1]]))

def test_missing_negative(data):
    with pytest.raises(ValueError,match='every site'): validate(data.iloc[1:])

def test_invalid_label(data):
    bad=data.copy(); bad.loc[0,'detected']=2
    with pytest.raises(ValueError,match='0 or 1'): validate(bad)

def test_inconsistent_coordinates(data):
    bad=data.copy(); bad.loc[0,'x']+=1
    with pytest.raises(ValueError,match='coordinates'): validate(bad)

def test_greedy():
    outcomes=np.array([[1,1,0],[1,0,0],[0,0,1]])
    assert greedy(outcomes,2)==[0,2]
    assert coverage(outcomes,[0,2])==oracle(outcomes,2)==3
    with pytest.raises(ValueError): greedy(outcomes,0)
    assert oracle(np.zeros((20,2)),10) is None

def test_holdout(data):
    result=evaluate(data,2)
    assert not set(result['train_sessions']) & set(result['test_sessions'])
    assert max(result['train_sessions']) < min(result['test_sessions'])
    assert all(len(v)==2 and len(set(v))==2 for v in result['recommendations'].values())
    assert all(0<=m['accuracy']<=1 for m in result['models'].values())
    json.dumps(result,allow_nan=False)
    results={s['strategy']:s['mean_found'] for s in result['strategies']}
    assert max(results.values())==results['offline_oracle']

def test_no_test_label_leakage(data):
    result=evaluate(data,2); modified=data.copy(); ix=modified.session.isin(result['test_sessions']); modified.loc[ix,'detected']=1-modified.loc[ix,'detected']
    assert evaluate(modified,2)['recommendations']==result['recommendations']

def test_scanner_parser():
    assert parse_scan(r'02\:00\:00\:00\:00\:01:65') == {'02:00:00:00:00:01':65}
    with pytest.raises(ValueError): parse_scan(r'02\:00\:00\:00\:00\:01:101')
    assert parse_scan('') == {}

def test_postgres_schema():
    for table in metadata.sorted_tables: assert 'CREATE TABLE' in str(CreateTable(table).compile(dialect=postgresql.dialect()))
    with pytest.raises(ValueError): SurveyRepository('sqlite:///local.db')

def test_api():
    client=TestClient(app); assert client.get('/health').json()['status']=='ok'; assert client.get('/demo/evaluation?budget=0').status_code==422

def test_cli(tmp_path):
    path=tmp_path/'demo.csv'; out=tmp_path/'result.json'
    assert main(['demo','--sessions','8','--output',str(path)])==0
    assert main(['evaluate',str(path),'--budget','2','--output',str(out)])==0
    assert json.loads(out.read_text())['source']=='synthetic'

def test_next_site(data):
    from spectraseek.experiment import recommend
    result = recommend(data,visited=['S01'],found=['AP01'],strategy='empirical_greedy')
    assert result['site'] != 'S01'
    assert all(r['site'] != 'S01' for r in result['ranked_sites'])
    assert 0 <= result['expected_new_targets'] <= 7
    assert recommend(data,visited=data.site.unique())['site'] is None
    with pytest.raises(ValueError): recommend(data,visited=['unknown'])


def test_scan_failure_not_negative(monkeypatch):
    from spectraseek import collector
    monkeypatch.setattr(collector, '_networkmanager_interfaces', lambda: ['wlan0'])
    def fail(*args): raise RuntimeError('scan unavailable')
    monkeypatch.setattr(collector,'_nmcli',fail)
    with pytest.raises(RuntimeError): collector._networkmanager_scan('wlan0')
