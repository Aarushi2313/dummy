from pydantic import BaseModel
from typing import Literal
from datetime import datetime

class TimeWindow(BaseModel):
    start: datetime
    end: datetime

class ReportRequest(BaseModel):
    report_type: Literal["daily_brief", "weekly_summary", "approval_queue", "risk_digest"]
    user_role: Literal["founder", "admin", "manager", "viewer"]
    time_window: TimeWindow
