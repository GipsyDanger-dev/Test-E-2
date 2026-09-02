from fastapi.testclient import TestClient
from app.database import Base, engine
from app.loaders import DataPack, load_data_pack
from app.main import app
from app.ai import TemporaryModelError
from app.schemas import EmailInput, EnquiryAnalysis, ExtractedFacts

def client():
    Base.metadata.drop_all(engine); Base.metadata.create_all(engine)
    return TestClient(app)

def import_data(c): assert c.post('/api/import').status_code==200
def one_email_pack(payload):
    email=EmailInput.model_validate(payload)
    return DataPack(staff=[],crm_records=[],emails=[email],documents={},warnings=[],raw_rows={})

def test_exact_input_fidelity_and_safe_c002_recovery():
    pack=load_data_pack(); c002=next(x for x in pack.crm_records if x.id=='C002')
    assert pack.staff[0].role=='Founder'
    assert next(x for x in pack.emails if x.id=='E003').from_raw=='Rohan Lee rohan@greenfieldsfoods.example'
    assert next(x for x in pack.emails if x.id=='E007').from_raw=='priya.dev@examplemail.test'
    assert next(x for x in pack.crm_records if x.id=='C003').company=='Greenfields Foods Pty Ltd'
    assert c002.phone is None and c002.location=='Melbourne VIC' and c002.status=='Lead' and c002.service=='Solar' and c002.state=='New'
    assert '1 July to 31 July 2026' in pack.documents['01_hume_energy_bill.txt']
    assert '"from"' in open('data/emails.json',encoding='utf-8').read() and '"from_raw"' not in open('data/emails.json',encoding='utf-8').read()

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
        assert e5['assigned_staff']=='Zidane Mouldino' and e5['crm_candidates'][0]['id']=='C004' and set(e5['missing_information'])=={'electricity invoice','fixture schedule'} and e5['extracted']['fixture_count']==1100 and e5['extracted']['team_size'] is None
        assert e6['assigned_staff']=='Ties Rahardjo' and 'No engineer' in e6['uncertainties'][0] and 'THD' in e6['extracted']['service_interest']
        assert e7['assigned_staff']=='Ties Rahardjo' and 'HR' in e7['uncertainties'][0]
        assert e8['assigned_staff']=='Ties Rahardjo' and e8['extracted']['contact_name']=='Daniel Wu' and e8['extracted']['company_name'] is None and e8['crm_candidates'][0]['id']=='C005' and 'not been confirmed' in e8['uncertainties'][0]
        assert e11['assigned_staff']=='Ali Pratama' and e11['draft_response'] is None and e11['extracted']['unsynchronised_record_count']==146 and e11['extracted']['team_size'] is None
        assert e12['assigned_staff']=='Zidane Mouldino' and 'landlord approval' in e12['missing_information'] and 'quote' in e12['uncertainties'][0].lower()

def test_continuation_and_approval_gate():
    with client() as c:
        import_data(c)
        e9=c.get('/api/enquiries/E009').json(); e10=c.get('/api/enquiries/E010').json()
        assert next(x for x in e9['duplicate_candidates'] if x['id']=='E010')['level']=='strong_candidate'
        assert e10['extracted']['corrected_phone']=='0411 999 102' and e10['extracted']['previous_phone']=='0411 999 120' and e10['extracted']['preferred_email']=='sam@harbourcoldstores.example' and e10['extracted']['company_name'] is None and e10['extracted']['contact_name'] is None and e10['requires_human_approval'] is True
        assert c.post('/api/enquiries/E010/approve',json={'reviewer':'Reviewer'}).status_code==200
        assert c.post('/api/enquiries/E010/approve',json={'reviewer':'Reviewer'}).status_code==409

def test_legal_rule_bypasses_model_and_government_incentives_do_not_false_positive(monkeypatch):
    calls=0
    class MustNotRun:
        def analyze(self,*_):
            nonlocal calls; calls+=1; raise AssertionError('model must not run for clear legal case')
    monkeypatch.setattr('app.main.get_analyzer',lambda:MustNotRun())
    monkeypatch.setattr('app.main.load_data_pack',lambda:one_email_pack({'id':'XLEGAL001','from':'partner@example.test','subject':'Contract and regulatory approval question','body':'Before signing the proposed agreement, can you confirm whether this arrangement complies with current regulatory requirements and whether the contract creates any liability for us?','attachment':None}))
    with client() as c:
        c.post('/api/import'); e=c.get('/api/enquiries/XLEGAL001').json()
        assert calls==0 and e['category']=='legal_compliance' and e['recommended_action']=='review_legal_compliance' and e['assigned_staff']=='Ties Rahardjo' and e['requires_human_approval'] is True
        events=[a['event_type'] for a in c.get('/api/enquiries/XLEGAL001/audit').json()]
        assert 'deterministic_rule_matched' in events and 'model_analysis_started' not in events

def test_model_outage_preserves_ambiguous_raw_input_without_classification(monkeypatch):
    class Broken:
        def analyze(self,*_): raise ValueError('invalid structured output')
    monkeypatch.setattr('app.main.get_analyzer',lambda:Broken())
    monkeypatch.setattr('app.main.load_data_pack',lambda:one_email_pack({'id':'XAMB001','from':'alex@example.test','subject':'Question about proposed arrangement','body':'Could someone review this situation and advise who should handle it? I am not sure which team this belongs to.','attachment':None}))
    with client() as c:
        c.post('/api/import'); e=c.get('/api/enquiries/XAMB001').json(); events=[a['event_type'] for a in c.get('/api/enquiries/XAMB001/audit').json()]
        assert e['status']=='needs_human_review' and e['category'] is None and e['confidence'] is None and e['extracted']=={} and e['draft_response'] is None and e['recommended_action']=='human_review' and e['assigned_staff']=='Ties Rahardjo' and e['requires_human_approval'] and e['body'].startswith('Could someone')
        assert {'deterministic_rules_evaluated','no_deterministic_match','model_analysis_started','model_unavailable','manual_review_required'} <= set(events)

def test_temporary_retry_succeeds_within_bound(monkeypatch):
    class Flaky:
        calls={}
        def analyze(self,email,attachment):
            self.calls[email.id]=self.calls.get(email.id,0)+1
            if email.id=='XAMB001' and self.calls[email.id]<3: raise TemporaryModelError('temporary')
            return EnquiryAnalysis(category='junk',confidence=.99,extracted=ExtractedFacts(),recommended_action='archive_junk')
    flaky=Flaky(); monkeypatch.setattr('app.main.get_analyzer',lambda:flaky)
    monkeypatch.setattr('app.main.load_data_pack',lambda:one_email_pack({'id':'XAMB001','from':'alex@example.test','subject':'Question about proposed arrangement','body':'Could someone review this situation and advise who should handle it? I am not sure which team this belongs to.','attachment':None}))
    with client() as c:
        c.post('/api/import'); e=c.get('/api/enquiries/XAMB001').json(); audit=c.get('/api/enquiries/XAMB001/audit').json()
        assert flaky.calls['XAMB001']==3
        assert e['status']=='closed_as_junk' and len([x for x in audit if x['event_type']=='analysis_retry'])==2

def test_temporary_retry_exhaustion_is_safe(monkeypatch):
    class AlwaysTemporary:
        calls={}
        def analyze(self,email,*_):
            self.calls[email.id]=self.calls.get(email.id,0)+1
            if email.id=='XAMB001': raise TemporaryModelError('temporary')
            return EnquiryAnalysis(category='junk',confidence=.99,extracted=ExtractedFacts(),recommended_action='archive_junk')
    analyzer=AlwaysTemporary(); monkeypatch.setattr('app.main.get_analyzer',lambda:analyzer)
    monkeypatch.setattr('app.main.load_data_pack',lambda:one_email_pack({'id':'XAMB001','from':'alex@example.test','subject':'Question about proposed arrangement','body':'Could someone review this situation and advise who should handle it? I am not sure which team this belongs to.','attachment':None}))
    with client() as c:
        c.post('/api/import'); e=c.get('/api/enquiries/XAMB001').json(); audit=c.get('/api/enquiries/XAMB001/audit').json()
        assert analyzer.calls['XAMB001']==3 and e['status']=='needs_human_review' and e['category'] is None and e['extracted']=={} and any(x['event_type']=='model_unavailable' for x in audit)

def test_health_reflects_configured_provider(monkeypatch):
    monkeypatch.setenv('AI_PROVIDER','gemini')
    with client() as c: assert c.get('/health').json()=={'status':'ok','ai_provider':'gemini'}
