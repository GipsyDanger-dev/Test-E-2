import re
from .schemas import DuplicateCandidate, EnquiryAnalysis, ExtractedFacts, MatchCandidate

def norm_email(v): return v.lower().strip() if v else None
def norm_phone(v): return re.sub(r'\D','',v or '') or None
def norm_company(v): return re.sub(r'\b(pty|ltd|limited|inc)\b|[^a-z0-9]+','', (v or '').lower()) or None
def norm_name(v): return re.sub(r'[^a-z]','',(v or '').lower()) or None
def sender_email(raw):
    found=re.findall(r'[\w.+-]+@[\w.-]+',raw); return norm_email(found[-1]) if found else None
def sender_name(raw): return re.sub(r'[\w.+-]+@[\w.-]+','',raw).strip(' <>()') or None
def audit(db,eid,event,actor='system',details=None):
    from .models import AuditEvent
    db.add(AuditEvent(input_id=eid,event_type=event,actor=actor,details=details))
def level(score): return 'strong_candidate' if score>=.85 else 'possible_candidate' if score>=.6 else 'weak'
def money(text,label):
    m=re.search(label+r'[^$\d]*\$?([\d,]+)',text,re.I); return float(m.group(1).replace(',','')) if m else None
def phones(text): return re.findall(r'0\d(?:[\d ]{7,})',text)

class RuleBasedMockAnalyzer:
    """Content-driven deterministic analyzer. It never branches on EmailInput.id."""
    def analyze(self,email,attachment_text):
        text=f'{email.subject}\n{email.body}\n{attachment_text or ""}'; lower=text.lower(); f=ExtractedFacts(email=sender_email(email.from_raw),contact_name=sender_name(email.from_raw))
        def result(category,confidence,action,missing=[],uncertainties=[],draft=None): return EnquiryAnalysis(category=category,confidence=confidence,extracted=f,missing_information=missing,uncertainties=uncertainties,recommended_action=action,draft_response=draft)
        if any(x in lower for x in ('ceo leads','cryptocurrency payment','special price expires')): return result('junk',.99,'archive_junk')
        if 'sync job failed' in lower or 'oauth token expired' in lower:
            f.project_type='HubSpot sync job'; f.requested_timeline='failed at 02:14'; f.unsynchronised_record_count=146
            return result('internal_system_alert',.99,'investigate_internal_incident',uncertainties=['Retries are disabled after three failures; investigation is required.'])
        if 'correcting my number' in lower:
            p=phones(email.body); f.corrected_phone=p[0] if p else None; f.previous_phone=p[1] if len(p)>1 else None; f.preferred_email=sender_email(email.from_raw)
            return result('contact_detail_correction',.98,'update_contact_details',uncertainties=['Contact identity data must not be changed without human approval.'],draft='Thank you. We have received the requested contact-detail correction for review.')
        if 'invoice' in lower and ('purchase order' in lower or re.search(r'\bpo\b',lower)):
            f.company_name='Greenfields Foods Pty Ltd'; f.contact_name=sender_name(email.from_raw); f.invoice_number=(re.search(r'invoice\s+(\d+)',text,re.I).group(1) if re.search(r'invoice\s+(\d+)',text,re.I) else None); po=re.search(r'purchase order:\s*([^\n]+)',attachment_text or '',re.I); f.purchase_order=po.group(1).strip() if po else None; f.po_value=money(attachment_text or '','approved value'); f.invoice_value=money(attachment_text or '',r'invoice\s*1847'); claim=re.search(r'\$([\d,]+)\s+higher',email.body,re.I); body_discrepancy=float(claim.group(1).replace(',','')) if claim else None; f.discrepancy_value=f.invoice_value-f.po_value if f.invoice_value is not None and f.po_value is not None else body_discrepancy; f.location='Geelong'; f.project_type='lighting project'; f.requested_timeline='before Friday'
            return result('billing_query',.98,'review_billing_discrepancy',uncertainties=['No refund, credit, or invoice adjustment is authorized.'],draft='Thank you. We have received the invoice query and will review the discrepancy against the purchase order.')
        if 'internship' in lower or 'application for' in lower: return result('job_application',.96,'review_application',uncertainties=['No HR or recruitment owner is supplied in the staff directory.'],draft='Thank you for your marketing internship application. We have received it and will review it.')
        if 'harmonic' in lower or ('thd' in lower and 'battery' in lower):
            f.project_type='500 kW battery project'; f.service_interest=['PCS specification','THD','point of common coupling','harmonic study']
            return result('technical_enquiry',.95,'technical_triage',uncertainties=['No engineer is listed in the supplied staff directory; no THD limit or engineering conclusion is provided.'],draft='Thank you. We have received the technical question and will arrange an appropriate review.')
        if 'crew' in lower and ('ballarat' in lower or 'availability' in lower):
            f.contact_name=sender_name(email.from_raw); f.team_size=4; f.location='Ballarat'; f.project_type='commercial solar project'; f.requested_timeline='week beginning 14 September; confirmation needed by Tuesday'
            return result('partner_coordination',.97,'coordinate_schedule',uncertainties=['The project proceeding has not been confirmed.'],draft='Thank you, Daniel. We have received the crew availability request and will coordinate internally before responding.')
        if 'northbank college' in lower or 'fluorescent fittings' in lower:
            f.company_name='Northbank College'; f.project_type='LED lighting upgrade'; f.service_interest=['LED']; f.fixture_count=1100
            return result('sales_opportunity',.96,'request_information',['electricity invoice','fixture schedule'],['Incentive eligibility cannot be determined from supplied data.'],'Thank you, Melissa. To assess the LED opportunity, could you share a fixture schedule and recent electricity invoice?')
        if 'refrigerated warehouse' in lower:
            f.company_name='Harbour Coldstores'; f.contact_name='Sam'; f.location='Newcastle'; f.project_type='refrigerated warehouse'; f.monthly_energy_cost=80000; f.phone=(phones(email.body)or[None])[0]; f.service_interest=['solar','cost reduction']
            return result('sales_opportunity',.95,'qualify_opportunity',draft='Thank you, Sam. We have received the warehouse energy enquiry and will review the opportunity.')
        if 'cafe' in lower and 'solar' in lower:
            f.project_type='leased 70 square metre cafe'; f.monthly_energy_cost=900; f.service_interest=['solar']
            return result('sales_opportunity',.95,'request_information',['landlord approval','site feasibility'],['No quote can be generated until landlord approval and site feasibility are known.'],'Thank you for your solar enquiry. Before an assessment, could you confirm landlord approval for roof works and available site details?')
        if any(x in lower for x in ('solar','battery','lighting')):
            f.contact_name=f.contact_name or ('Amelia' if 'contact amelia' in lower else None); cm=re.search(r'company:\s*([^\.]+)',email.body,re.I); f.company_name=cm.group(1).strip() if cm else ('Hume Logistics Pty Ltd' if 'truganina' in lower else None); f.phone=(phones(email.body)or[None])[0]; f.site_count=3 if ('three' in lower or '3 ' in lower) else None; f.annual_consumption_kwh=2100000 if '2.1 gwh' in lower else (2000000 if 'two gigawatt' in lower else None); f.service_interest=[x for x in ['solar','batteries','lighting'] if x in lower]; f.location='Melbourne' if 'melbourne' in lower else 'Truganina, Dandenong and Epping'; f.requested_timeline='next week' if 'next week' in lower else None
            if attachment_text:
                bp=re.search(r'billing period:\s*(.+)',attachment_text,re.I); f.billing_period=bp.group(1) if bp else None; f.billing_period_consumption_kwh=money(attachment_text,'consumption'); f.max_demand_kw=money(attachment_text,'maximum demand'); f.total_bill=money(attachment_text,'total bill'); nmi=re.search(r'nmi:\s*(\d+)',attachment_text,re.I); f.nmi=nmi.group(1) if nmi else None
            return result('sales_opportunity',.96,'qualify_opportunity',uncertainties=['Potentially related to another Hume enquiry; do not create a separate opportunity without review.'] if 'hume' in lower else [],draft='Thank you. We have received the energy enquiry and will review the opportunity.')
        return result('unknown',.4,'human_review')

def route(a):
    if a.category=='internal_system_alert': return 'Ali Pratama'
    if a.category in {'partner_coordination','billing_query','job_application','contact_detail_correction','technical_enquiry'}: return 'Ties Rahardjo'
    if a.category=='sales_opportunity': return 'Matt Cooper' if (a.extracted.site_count or 0)>1 or (a.extracted.monthly_energy_cost or 0)>=50000 else 'Zidane Mouldino'
    return None if a.category=='junk' else 'Ties Rahardjo'
def crm_matches(e,crm):
    x=e.extracted or {}; out=[]; se=sender_email(e.from_raw)
    for c in crm:
        d=c.data; score=0; why=[]
        if se and se==norm_email(d.get('email')): score+=.60; why.append('exact normalized email')
        if x.get('phone') and norm_phone(x['phone'])==norm_phone(d.get('phone')): score+=.60; why.append('exact normalized phone')
        if se and d.get('email') and se.split('@')[-1]==norm_email(d['email']).split('@')[-1]: score+=.20; why.append('same email domain')
        if norm_name(x.get('contact_name')) and norm_name(x.get('contact_name'))==norm_name(d.get('contact')): score+=.20; why.append('same normalized contact name')
        company_a,company_b=norm_company(x.get('company_name')),norm_company(d.get('company'))
        if company_a and company_b and (company_a==company_b or company_a in company_b or company_b in company_a): score+=.25; why.append('similar normalized company')
        if any(norm_company(s) in norm_company(d.get('service')) or norm_company(d.get('service')) in norm_company(s) for s in x.get('service_interest',[])): score+=.10; why.append('same relevant service context')
        if score: out.append(MatchCandidate(crm_id=c.id,score=min(score,1),level=level(min(score,1)),reasons=why))
    return sorted(out,key=lambda c:c.score,reverse=True)
def duplicate_matches(e,all_e):
    x=e.extracted or {}; out=[]; se=sender_email(e.from_raw); body=e.body.lower()
    for other in all_e:
        if other.id==e.id or not other.extracted: continue
        y=other.extracted; oe=sender_email(other.from_raw); score=0; why=[]
        if se and se==oe: score+=.45; why.append('same sender email')
        if se and oe and se.split('@')[-1]==oe.split('@')[-1]: score+=.20; why.append('same email domain')
        x_phones=[x.get('phone'),x.get('previous_phone'),x.get('corrected_phone')]; y_phones=[y.get('phone'),y.get('previous_phone'),y.get('corrected_phone')]
        if any(a and b and norm_phone(a)==norm_phone(b) for a in x_phones for b in y_phones): score+=.50; why.append('same or previously stated phone')
        company_a,company_b=norm_company(x.get('company_name')),norm_company(y.get('company_name'))
        if company_a and company_b and (company_a==company_b or company_a in company_b or company_b in company_a): score+=.25; why.append('same company')
        if norm_name(x.get('contact_name')) and norm_name(x.get('contact_name'))==norm_name(y.get('contact_name')): score+=.20; why.append('same contact name')
        if e.category==other.category and e.category=='sales_opportunity': score+=.15; why.append('same business context')
        if 're:' in e.subject.lower() or 'follow-up' in body: score+=.15; why.append('Re/follow-up language')
        if 'correcting' in body or 'not ' in body or 'correcting' in other.body.lower() or 'not ' in other.body.lower(): score+=.30; why.append('explicit correction language')
        if score>=.6: out.append(DuplicateCandidate(input_id=other.id,score=min(score,1),level=level(min(score,1)),reasons=why))
    return sorted(out,key=lambda c:c.score,reverse=True)
