def extract_signals(events):
    approvals = []
    risks = []

    for e in events:
        if e.get("category") == "approval":
            approvals.append(e)
        if e.get("category") == "risk":
            risks.append(e)

    return approvals, risks
