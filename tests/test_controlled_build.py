from fastapi.testclient import TestClient
from app.database import Base, engine
from app.loaders import load_data_pack
from app.main import app

def client():
    Base.metadata.drop_all(engine); Base.metadata.create_all(engine)
    return TestClient(app)

def import_data(c): assert c.post('/api/import').status_code==200

def test_exact_input_fidelity_and_safe_c002_recovery():
    pack=load_data_pack(); c002=next(x for x in pack.crm_records if x.id=='C002')
    assert pack.staff[0].role=='Founder'
    assert next(x for x in pack.emails if x.id=='E003').from_raw=='Rohan Lee rohan@greenfieldsfoods.example'
    assert next(x for x in pack.emails if x.id=='E007').from_raw=='priya.dev@examplemail.test'
    assert next(x for x in pack.crm_records if x.id=='C003').company=='Greenfields Foods Pty Ltd'
    assert c002.phone is None and c002.location=='Melbourne VIC' and c002.status=='Lead' and c002.service=='Solar' and c002.state=='New'
    assert '1 July to 31 July 2026' in pack.documents['01_hume_energy_bill.txt']

def test_import_idempotency_warning_and_health():
    with client() as c:
        assert c.post('/api/import').json()=={'emails_loaded':12,'crm_records_loaded':5,'documents_loaded':3,'warnings':1}
        assert c.post('/api/import').json()['idempotent'] is True
        warning=c.get('/api/import-warnings').json()[0]
        assert warning['record_id']=='C002' and 'missing the phone field' in warning['message'] and 'a.grant@humelogistics.example' in warning['raw_row']
        assert c.get('/health').json()['ai_provider']=='mock'

def test_sales_and_matching_evidence():
    with client() as c:
        import_data(c)
        e1=c.get('/api/enquiries/E001').json(); e2=c.get('/api/enquiries/E002').json()
        assert e1['category']=='sales_opportunity' and e1['assigned_staff']=='Matt Cooper'
        assert e1['crm_candidates'][0]['id']=='C001' and any(x['id']=='C002' for x in e1['crm_candidates'])
        assert any(x['id']=='E002' for x in e1['duplicate_candidates'])
        assert e1['extracted']['billing_period_consumption_kwh']==68420 and e1['extracted']['annual_consumption_kwh']==2100000
        assert e1['extracted']['nmi']=='63051234567' and e1['extracted']['max_demand_kw']==172
        assert any(x['id']=='E001' for x in e2['duplicate_candidates']) and {x['id'] for x in e2['crm_candidates']}>={'C001','C002'}

def test_billing_junk_and_other_required_routes():
    with client() as c:
        import_data(c)
        e3=c.get('/api/enquiries/E003').json(); e4=c.get('/api/enquiries/E004').json(); e5=c.get('/api/enquiries/E005').json(); e6=c.get('/api/enquiries/E006').json(); e7=c.get('/api/enquiries/E007').json(); e8=c.get('/api/enquiries/E008').json(); e11=c.get('/api/enquiries/E011').json(); e12=c.get('/api/enquiries/E012').json()
        assert e3['extracted']['contact_name']=='Rohan Lee' and e3['extracted']['purchase_order']=='GF PO 8821' and e3['extracted']['discrepancy_value']==2640 and e3['crm_candidates'][0]['id']=='C003'
        assert e4['category']=='junk' and e4['draft_response'] is None
        assert e5['assigned_staff']=='Zidane Mouldino' and e5['crm_candidates'][0]['id']=='C004' and set(e5['missing_information'])=={'electricity invoice','fixture schedule'}
        assert e6['assigned_staff']=='Ties Rahardjo' and 'No engineer' in e6['uncertainties'][0] and 'THD' in e6['extracted']['service_interest']
        assert e7['assigned_staff']=='Ties Rahardjo' and 'HR' in e7['uncertainties'][0]
        assert e8['assigned_staff']=='Ties Rahardjo' and e8['crm_candidates'][0]['id']=='C005' and 'not been confirmed' in e8['uncertainties'][0]
        assert e11['assigned_staff']=='Ali Pratama' and e11['draft_response'] is None and e11['extracted']['team_size']==146
        assert e12['assigned_staff']=='Zidane Mouldino' and 'landlord approval' in e12['missing_information'] and 'quote' in e12['uncertainties'][0].lower()

def test_continuation_and_approval_gate():
    with client() as c:
        import_data(c)
        e9=c.get('/api/enquiries/E009').json(); e10=c.get('/api/enquiries/E010').json()
        assert next(x for x in e9['duplicate_candidates'] if x['id']=='E010')['level']=='strong_candidate'
        assert e10['extracted']['corrected_phone']=='0411 999 102' and e10['extracted']['previous_phone']=='0411 999 120' and e10['requires_human_approval'] is True
        assert c.post('/api/enquiries/E010/approve',json={'reviewer':'Reviewer'}).status_code==200
        assert c.post('/api/enquiries/E010/approve',json={'reviewer':'Reviewer'}).status_code==409

def test_provider_failure_preserves_raw_input(monkeypatch):
    class Broken:
        def analyze(self,*_): raise ValueError('invalid structured output')
    monkeypatch.setattr('app.main.get_analyzer',lambda:Broken())
    with client() as c:
        c.post('/api/import'); e=c.get('/api/enquiries/E001').json()
        assert e['status']=='ai_failed' and 'Truganina' in e['body'] and e['attachment_text'] and e['requires_human_approval']
        assert any(a['event_type']=='analysis_failed' for a in c.get('/api/enquiries/E001/audit').json())
