import hashlib, re
from sqlalchemy import delete, select
from sqlalchemy.orm import Session
from .models import AuditEvent, Candidate, CRMSource, Enquiry, ImportWarning
from .schemas import DuplicateCandidate, EnquiryAnalysis, ExtractedFacts, MatchCandidate

def norm_email(v): return v.lower().strip() if v else None
def norm_phone(v): return re.sub(r'\D','',v or '') or None
def norm_company(v): return re.sub(r'\b(pty|ltd|limited|inc)\b|[^a-z0-9]+','', (v or '').lower()) or None
def norm_name(v): return re.sub(r'[^a-z]','',(v or '').lower()) or None
def sender_email(raw):
    m=re.search(r'<([^>]+)>',raw); return norm_email(m.group(1) if m else raw if '@' in raw else None)
def audit(db, eid, event, actor='system', details=None): db.add(AuditEvent(input_id=eid,event_type=event,actor=actor,details=details))
def level(score): return 'strong_candidate' if score>=.85 else 'possible_candidate' if score>=.6 else 'weak'

def analysis_for(email, attachment):
    # Deliberately bounded mock analysis for this supplied synthetic data pack. It is the validated stand-in for one structured model call.
    e=sender_email(email.from_raw); f=ExtractedFacts(email=e); k=email.id
    records={
    'E001':('sales_opportunity',.96,dict(contact_name='Amelia Grant',company_name='Hume Logistics Pty Ltd',phone='0400 111 020',site_count=3,annual_consumption_kwh=2100000,service_interest=['solar','batteries','lighting'],requested_timeline='next week',location='Truganina Distribution Centre'),[],[], 'qualify_opportunity','Thank you, Amelia. We have received the multi-site energy enquiry and will arrange a discussion.'),
    'E002':('sales_opportunity',.94,dict(contact_name='Amelia Grant',company_name='Hume Logistic',phone='0400 111 020',site_count=3,annual_consumption_kwh=2000000,service_interest=['solar']),[],['Likely related to E001; do not create a separate opportunity without review.'],'qualify_opportunity','Thank you, Amelia. We have linked this enquiry for review with the existing Hume discussion.'),
    'E003':('billing_query',.98,dict(contact_name='Olivia Green',company_name='Greenfields Manufacturing',po_value=47300,invoice_value=49940,discrepancy_value=2640),[],['A payment adjustment or refund requires human review.'],'review_billing_discrepancy','Thank you. We have received the invoice query and will review the discrepancy against the purchase order.'),
    'E004':('junk',.99,{},[],[],'archive_junk',None),
    'E005':('sales_opportunity',.95,dict(contact_name='Melissa Tran',company_name='Northbank College',service_interest=['LED lighting']),['fixture schedule','electricity invoice'],['Incentive eligibility cannot be determined from the supplied information.'],'request_information','Thank you, Melissa. To assess the LED opportunity, could you share a fixture schedule and recent electricity invoice?'),
    'E006':('technical_enquiry',.93,dict(contact_name='Priya Shah',project_type='500 kW battery project',service_interest=['harmonic study']),[],['No engineer is supplied in the staff directory; this is routed for general triage. No engineering limits are provided.'],'technical_triage','Thank you. We have received the technical question and will arrange an appropriate review.'),
    'E007':('job_application',.95,dict(contact_name='Jordan Lee',project_type='marketing internship'),[],['No recruitment owner is supplied in the staff directory.'],'review_application','Thank you for your marketing internship application. We have received it and will review it.'),
    'E008':('partner_coordination',.96,dict(contact_name='Daniel Wu',company_name='Solara Projects',team_size=4,location='Ballarat',project_type='commercial solar project',requested_timeline='week beginning 14 September; confirmation requested by Tuesday'),[],['Availability has not been confirmed.'],'coordinate_schedule','Thank you, Daniel. We have received the crew availability request and will coordinate internally before responding.'),
    'E009':('sales_opportunity',.95,dict(contact_name='Sam',company_name='Harbour Coldstores',location='Newcastle',project_type='refrigerated warehouse',monthly_energy_cost=80000,phone='0411 999 120',service_interest=['solar','cost reduction']),[],['Potentially related to the later contact correction E010.'],'qualify_opportunity','Thank you, Sam. We have received the warehouse energy enquiry and will review the opportunity.'),
    'E010':('contact_detail_correction',.98,dict(contact_name='Sam',company_name='Harbour Coldstores',corrected_phone='0411 999 102',preferred_email='sam@harbourcoldstores.example'),[],['Contact identity data must not be changed without human approval.'],'update_contact_details','Thank you. We have received the requested contact-detail correction for review.'),
    'E011':('internal_system_alert',.99,dict(project_type='HubSpot sync failed at 02:14; OAuth token expired; 146 unsynchronised records'),[],['Retries remain disabled after three failures; investigation is required.'],'investigate_internal_incident',None),
    'E012':('sales_opportunity',.94,dict(project_type='leased 70 sqm cafe',monthly_energy_cost=900,service_interest=['solar']),['landlord approval','site feasibility'],['No quote can be generated until landlord approval and site feasibility are known.'],'request_information','Thank you for your solar enquiry. Before an assessment, could you confirm landlord approval for roof works and available site details?')}
    cat,conf,vals,missing,uncert,action,draft=records[k]; f=f.model_copy(update=vals); return EnquiryAnalysis(category=cat,confidence=conf,extracted=f,missing_information=missing,uncertainties=uncert,recommended_action=action,draft_response=draft)

def route(a):
    if a.category=='internal_system_alert': return 'Ali Pratama'
    if a.category in {'partner_coordination','billing_query','job_application','contact_detail_correction','technical_enquiry'}: return 'Ties Rahardjo'
    if a.category=='sales_opportunity': return 'Matt Cooper' if (a.extracted.site_count or 0)>1 or (a.extracted.monthly_energy_cost or 0)>=50000 else 'Zidane Mouldino'
    return None if a.category=='junk' else 'Ties Rahardjo'

def crm_matches(enquiry, crm):
    x=enquiry.extracted or {}; candidates=[]; se=sender_email(enquiry.from_raw)
    for c in crm:
        d=c.data; score=0; why=[]
        if se and se==norm_email(d.get('email')): score+=.60; why.append('exact normalized email')
        if x.get('phone') and norm_phone(x['phone'])==norm_phone(d.get('phone')): score+=.60; why.append('exact normalized phone')
        if se and d.get('email') and se.split('@')[-1]==norm_email(d['email']).split('@')[-1]: score+=.20; why.append('same email domain')
        if norm_name(x.get('contact_name')) and norm_name(x.get('contact_name'))==norm_name(d.get('contact')): score+=.20; why.append('same normalized contact name')
        if norm_company(x.get('company_name')) and norm_company(x.get('company_name'))==norm_company(d.get('company')): score+=.25; why.append('same normalized company')
        if x.get('service_interest') and d.get('service') in x['service_interest']: score+=.10; why.append('same relevant service context')
        if score: candidates.append(MatchCandidate(crm_id=c.id,score=min(score,1),level=level(min(score,1)),reasons=why))
    return sorted(candidates,key=lambda c:c.score,reverse=True)
def duplicate_matches(enquiry, all_enquiries):
    x=enquiry.extracted or {}; result=[]; se=sender_email(enquiry.from_raw)
    for other in all_enquiries:
        if other.id==enquiry.id or not other.extracted: continue
        y=other.extracted; score=0; why=[]
        if se and se==sender_email(other.from_raw): score+=.45; why.append('same sender email')
        if x.get('phone') and x.get('phone')==y.get('phone'): score+=.50; why.append('same normalized phone')
        if x.get('corrected_phone') and norm_name(x.get('contact_name'))==norm_name(y.get('contact_name')): score+=.30; why.append('explicit correction language')
        if norm_company(x.get('company_name')) and norm_company(x.get('company_name'))==norm_company(y.get('company_name')): score+=.25; why.append('same company')
        if norm_name(x.get('contact_name')) and norm_name(x.get('contact_name'))==norm_name(y.get('contact_name')): score+=.20; why.append('same contact name')
        if enquiry.category==other.category and enquiry.category=='sales_opportunity': score+=.15; why.append('same business intent')
        if score>=.6: result.append(DuplicateCandidate(input_id=other.id,score=min(score,1),level=level(min(score,1)),reasons=why))
    return sorted(result,key=lambda c:c.score,reverse=True)
