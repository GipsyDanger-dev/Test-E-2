from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select
from sqlalchemy.orm import Session
from .database import Base, engine, get_db
from .loaders import load_data_pack
from .models import AuditEvent, Candidate, CRMSource, Enquiry, ImportWarning
from .schemas import ApprovalRequest
from .services import audit, crm_matches, duplicate_matches, route
from .ai import TemporaryModelError, get_analyzer
from .config import MAX_MODEL_RETRIES
import os

@asynccontextmanager
async def lifespan(app):
    Base.metadata.create_all(engine); yield
app=FastAPI(title='BEDA Test 2 — Controlled Build',version='1.0.0',lifespan=lifespan)
app.mount('/static',StaticFiles(directory=Path(__file__).parent/'static'),name='static')
@app.get('/',include_in_schema=False)
def index(): return FileResponse(Path(__file__).parent/'static'/'index.html')
def candidates(db,eid,kind): return [{'id':x.target_id,'score':x.score,'level':x.level,'reasons':x.reasons} for x in db.scalars(select(Candidate).where(Candidate.enquiry_id==eid,Candidate.kind==kind).order_by(Candidate.score.desc()))]
def serial(db,e):
    return {'id':e.id,'from_raw':e.from_raw,'subject':e.subject,'body':e.body,'attachment':e.attachment,'attachment_text':e.attachment_text,'status':e.status,'category':e.category,'confidence':e.confidence,'recommended_action':e.recommended_action,'assigned_staff':e.assigned_staff,'requires_human_approval':e.requires_human_approval,'extracted':e.extracted or {},'missing_information':e.missing_information or [],'uncertainties':e.uncertainties or [],'draft_response':e.draft_response,'analysis_error':e.analysis_error,'crm_candidates':candidates(db,e.id,'crm'),'duplicate_candidates':candidates(db,e.id,'duplicate')}
@app.post('/api/import')
def import_pack(db:Session=Depends(get_db)):
    if db.scalar(select(Enquiry.id).limit(1)):
        return {'emails_loaded':db.query(Enquiry).count(),'crm_records_loaded':db.query(CRMSource).count(),'documents_loaded':3,'warnings':db.query(ImportWarning).count(),'idempotent':True}
    pack=load_data_pack()
    for c in pack.crm_records: db.add(CRMSource(id=c.id,raw_row=pack.raw_rows[c.id],data=c.model_dump()))
    for w in pack.warnings: db.add(ImportWarning(**w)); audit(db,w['record_id'],'parse_warning',details={'type':w['type'],'message':w['message']})
    db.commit()
    for mail in pack.emails:
        attachment=pack.documents.get(mail.attachment) if mail.attachment else None
        e=Enquiry(id=mail.id,from_raw=mail.from_raw,subject=mail.subject,body=mail.body,attachment=mail.attachment,attachment_text=attachment,status='processing')
        db.add(e); db.flush(); audit(db,e.id,'email_ingested',details={'source':'synthetic_data_pack'}); audit(db,e.id,'attachment_loaded' if attachment else ('attachment_missing' if mail.attachment else 'attachment_not_applicable'),details={'attachment':mail.attachment} if mail.attachment else None); audit(db,e.id,'analysis_started',actor='ai_pipeline')
        try:
            analyzer=get_analyzer(); a=None
            for attempt in range(MAX_MODEL_RETRIES+1):
                try:
                    a=analyzer.analyze(mail,attachment); break
                except TemporaryModelError as exc:
                    if attempt==MAX_MODEL_RETRIES: raise
                    audit(db,e.id,'analysis_retry','ai_pipeline',{'attempt':attempt+1,'error':str(exc)})
            if a is None: raise RuntimeError('Analyzer returned no analysis')
            e.category=a.category; e.confidence=a.confidence; e.recommended_action=a.recommended_action; e.extracted=a.extracted.model_dump(); e.missing_information=a.missing_information; e.uncertainties=a.uncertainties; e.draft_response=a.draft_response; e.assigned_staff=route(a); e.requires_human_approval=a.category!='junk'; e.status='closed_as_junk' if a.category=='junk' else 'needs_human_review'
            audit(db,e.id,'analysis_completed','ai_pipeline',{'category':a.category,'confidence':a.confidence,'recommended_action':a.recommended_action}); audit(db,e.id,'routing_decided',details={'assigned_staff':e.assigned_staff});
            if a.draft_response: audit(db,e.id,'draft_created','ai_pipeline')
            if e.requires_human_approval: audit(db,e.id,'approval_required',details={'reason':'recommendations and any consequential action require human approval'})
            audit(db,e.id,'processing_completed',details={'status':e.status})
        except Exception as exc:
            e.status='ai_failed'; e.analysis_error=str(exc); e.requires_human_approval=True; audit(db,e.id,'analysis_failed',details={'error':str(exc)}); audit(db,e.id,'approval_required',details={'reason':'analysis failure'}); audit(db,e.id,'processing_completed',details={'status':'ai_failed'})
    db.commit()
    all_e=list(db.scalars(select(Enquiry))); crm=list(db.scalars(select(CRMSource)))
    for e in all_e:
        for m in crm_matches(e,crm): db.add(Candidate(enquiry_id=e.id,kind='crm',target_id=m.crm_id,score=m.score,level=m.level,reasons=m.reasons)); audit(db,e.id,'crm_match_candidate_found',details=m.model_dump())
        for d in duplicate_matches(e,all_e): db.add(Candidate(enquiry_id=e.id,kind='duplicate',target_id=d.input_id,score=d.score,level=d.level,reasons=d.reasons)); audit(db,e.id,'duplicate_candidate_found',details=d.model_dump())
    audit(db,None,'dataset_loaded',details={'emails':len(pack.emails),'crm':len(pack.crm_records),'documents':len(pack.documents)}); db.commit()
    return {'emails_loaded':12,'crm_records_loaded':5,'documents_loaded':3,'warnings':len(pack.warnings)}
@app.get('/api/overview')
def overview(db:Session=Depends(get_db)):
    es=list(db.scalars(select(Enquiry))); return {'total':len(es),'review_queue':sum(e.status=='needs_human_review' for e in es),'approved':sum(e.status=='approved' for e in es),'junk':sum(e.status=='closed_as_junk' for e in es),'warnings':db.query(ImportWarning).count(),'categories':{c:sum(e.category==c for e in es) for c in sorted({e.category for e in es if e.category})}}
@app.get('/api/enquiries')
def enquiries(db:Session=Depends(get_db)): return [serial(db,e) for e in db.scalars(select(Enquiry).order_by(Enquiry.id))]
@app.get('/api/enquiries/{eid}')
def enquiry(eid:str,db:Session=Depends(get_db)):
    e=db.get(Enquiry,eid)
    if not e: raise HTTPException(404,'Enquiry not found')
    return serial(db,e)
@app.get('/api/enquiries/{eid}/audit')
def enquiry_audit(eid:str,db:Session=Depends(get_db)):
    if not db.get(Enquiry,eid): raise HTTPException(404,'Enquiry not found')
    return [{'event_type':a.event_type,'actor':a.actor,'details':a.details,'created_at':a.created_at} for a in db.scalars(select(AuditEvent).where(AuditEvent.input_id==eid).order_by(AuditEvent.created_at,AuditEvent.id))]
@app.get('/api/review-queue')
def review_queue(db:Session=Depends(get_db)): return [serial(db,e) for e in db.scalars(select(Enquiry).where(Enquiry.status=='needs_human_review').order_by(Enquiry.id))]
@app.get('/api/import-warnings')
def warnings(db:Session=Depends(get_db)): return [{'record_id':w.record_id,'type':w.type,'severity':w.severity,'message':w.message,'raw_row':w.raw_row} for w in db.scalars(select(ImportWarning))]
@app.post('/api/enquiries/{eid}/approve')
def approve(eid:str,payload:ApprovalRequest,db:Session=Depends(get_db)):
    e=db.get(Enquiry,eid)
    if not e: raise HTTPException(404,'Enquiry not found')
    if e.status!='needs_human_review': raise HTTPException(409,'Only enquiries awaiting review may be approved.')
    e.status='approved'; audit(db,eid,'human_approved',payload.reviewer,{'local_prototype_only':True,'note':'no external message or CRM mutation occurred'}); db.commit(); return serial(db,e)
@app.post('/api/enquiries/{eid}/reject')
def reject(eid:str,payload:ApprovalRequest,db:Session=Depends(get_db)):
    e=db.get(Enquiry,eid)
    if not e: raise HTTPException(404,'Enquiry not found')
    if e.status!='needs_human_review': raise HTTPException(409,'Only enquiries awaiting review may be rejected.')
    e.status='rejected'; audit(db,eid,'human_rejected',payload.reviewer,{'no external action taken':True}); db.commit(); return serial(db,e)
@app.get('/health')
def health(): return {'status':'ok','ai_provider':os.getenv('AI_PROVIDER','mock').lower().strip()}
