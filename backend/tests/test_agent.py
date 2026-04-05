import pytest
from app.schemas.input import ReportRequest, TimeWindow
from datetime import datetime

def test_report_request_validation():
    # Valid schema
    window = TimeWindow(start=datetime.now(), end=datetime.now())
    req = ReportRequest(
        report_type="daily_brief",
        user_role="admin",
        time_window=window
    )
    assert req.report_type == "daily_brief"
    assert req.user_role == "admin"

def test_invalid_report_request():
    # Invalid literal
    window = TimeWindow(start=datetime.now(), end=datetime.now())
    with pytest.raises(ValueError):
        ReportRequest(
            report_type="daily_brief",
            user_role="hacker",  # Should trigger pydantic validation error
            time_window=window
        )
