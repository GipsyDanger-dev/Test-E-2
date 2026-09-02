from fastapi.testclient import TestClient
from app.database import Base, engine
from app.main import app

def client():
    Base.metadata.drop_all(engine); Base.metadata.create_all(engine)
    return TestClient(app)

def test_import_is_complete_and_idempotent():
    with client() as c:
        assert c.post('/api/import').json() == {'emails_loaded':12,'crm_records_loaded':5,'documents_loaded':3,'warnings':1}
        assert c.post('/api/import').json()['idempotent'] is True

def test_hume_match_duplicate_and_route():
    with client() as c:
        c.post('/api/import'); e=c.get('/api/enquiries/E001').json()
        assert e['category']=='sales_opportunity' and e['assigned_staff']=='Matt Cooper'
        assert e['crm_candidates'][0]['id']=='C001' and any(x['id']=='E002' for x in e['duplicate_candidates'])

def test_billing_junk_and_safe_approval_gate():
    with client() as c:
        c.post('/api/import'); bill=c.get('/api/enquiries/E003').json(); junk=c.get('/api/enquiries/E004').json()
        assert bill['extracted']['discrepancy_value']==2640 and bill['assigned_staff']=='Ties Rahardjo'
        assert junk['category']=='junk' and junk['draft_response'] is None
        assert c.post('/api/enquiries/E010/approve',json={'reviewer':'Reviewer'}).status_code==200
        assert c.post('/api/enquiries/E010/approve',json={'reviewer':'Reviewer'}).status_code==409

def test_required_special_cases():
    with client() as c:
        c.post('/api/import')
        e5=c.get('/api/enquiries/E005').json(); e6=c.get('/api/enquiries/E006').json(); e8=c.get('/api/enquiries/E008').json(); e11=c.get('/api/enquiries/E011').json(); e12=c.get('/api/enquiries/E012').json()
        assert 'electricity invoice' in e5['missing_information']
        assert e6['assigned_staff']=='Ties Rahardjo' and 'No engineer' in e6['uncertainties'][0]
        assert e8['crm_candidates'][0]['id']=='C005'
        assert e11['assigned_staff']=='Ali Pratama' and e11['draft_response'] is None
        assert 'landlord approval' in e12['missing_information']
