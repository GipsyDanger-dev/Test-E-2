from typing import Literal
from pydantic import BaseModel, Field

class StaffMember(BaseModel): name: str; role: str; owns: str
class EmailInput(BaseModel): id: str; from_raw: str; subject: str; body: str; attachment: str | None = None
class CRMSourceRecord(BaseModel):
    id: str; company: str | None = None; contact: str | None = None; email: str | None = None; phone: str | None = None; location: str | None = None; status: str | None = None; service: str | None = None; state: str | None = None; parse_warnings: list[str] = Field(default_factory=list)
class ExtractedFacts(BaseModel):
    contact_name: str | None = None; company_name: str | None = None; email: str | None = None; phone: str | None = None; location: str | None = None
    annual_consumption_kwh: float | None = None; monthly_energy_cost: float | None = None; project_type: str | None = None; service_interest: list[str] = Field(default_factory=list); site_count: int | None = None; team_size: int | None = None
    invoice_number: str | None = None; purchase_order: str | None = None; invoice_value: float | None = None; po_value: float | None = None; discrepancy_value: float | None = None; requested_timeline: str | None = None; corrected_phone: str | None = None; previous_phone: str | None = None; preferred_email: str | None = None
    billing_period: str | None = None; billing_period_consumption_kwh: float | None = None; max_demand_kw: float | None = None; total_bill: float | None = None; nmi: str | None = None
Category = Literal['sales_opportunity','existing_customer_support','billing_query','technical_enquiry','partner_coordination','job_application','internal_system_alert','contact_detail_correction','junk','unknown']
Action = Literal['qualify_opportunity','request_information','review_billing_discrepancy','technical_triage','coordinate_schedule','review_application','investigate_internal_incident','update_contact_details','archive_junk','human_review']
class EnquiryAnalysis(BaseModel):
    category: Category; confidence: float = Field(ge=0, le=1); extracted: ExtractedFacts; missing_information: list[str] = Field(default_factory=list); uncertainties: list[str] = Field(default_factory=list); recommended_action: Action; draft_response: str | None = None
class MatchCandidate(BaseModel): crm_id: str; score: float; level: str; reasons: list[str]
class DuplicateCandidate(BaseModel): input_id: str; score: float; level: str; reasons: list[str]
class ApprovalRequest(BaseModel): reviewer: str = Field(min_length=2, max_length=80)
