from pydantic import BaseModel
from typing import List, Optional

class Evidence(BaseModel):
    reference_id: str
    link: Optional[str]

class ApprovalItem(BaseModel):
    item: str
    urgency: str
    impact: str
    evidence: List[Evidence]

class RiskItem(BaseModel):
    issue: str
    severity: str
    evidence: List[Evidence]

class ReportOutput(BaseModel):
    report_type: str
    generated_at: str
    summary: dict
    approvals_needed: List[ApprovalItem]
    risks: List[RiskItem]
    data_completeness: str
