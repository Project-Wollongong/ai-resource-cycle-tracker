"""Ordered, neutral P03 F01-F08 event rules.

The order is the product delivery order: F04, F08, F06, F02, F01, F03,
F05, F07.  Rules require specific phrases; generic promotional words never
create events.
"""
from __future__ import annotations

import re
from typing import Any


FAMILY_NAMES = {
    "F01": "Exploration & Drilling",
    "F02": "Resource & Reserve",
    "F03": "Metallurgy & Processing",
    "F04": "Development & Study",
    "F05": "Permitting & Project Access",
    "F06": "Funding & Capital",
    "F07": "Commercial & Corporate Transaction",
    "F08": "Financial / Operating Periodic",
}
FAMILY_ORDER = ("F04", "F08", "F06", "F02", "F01", "F03", "F05", "F07")
GENERIC_WORDS = {"update", "results", "project", "positive", "significant", "strong", "successful", "progress", "activity", "announcement", "report", "review", "change"}


def detect_family_events(
    text: str,
    *,
    source_section: str,
    source_page: int | None,
    classification_source: str,
    base_status: str = "auto_classified",
    reported_on=None,
) -> list[dict[str, Any]]:
    normalized = _normalise(text)
    if not normalized:
        return []
    events: list[dict[str, Any]] = []

    def add(family: str, event_type: str, pattern: str, *, status: str = "reported", confidence: float = 0.86, reason: str | None = None, secondary: tuple[str, ...] = ()):
        match = re.search(pattern, normalized, re.I)
        if not match:
            return
        events.append({
            "event_family": family,
            "primary_family": family,
            "secondary_families_json": _json_list(secondary),
            "event_type": event_type,
            "event_title": event_type,
            "event_status": status,
            "classification_status": base_status,
            "classification_source": classification_source,
            "classification_confidence": confidence,
            "source_section": source_section,
            "source_page_start": source_page,
            "source_page_end": source_page,
            "source_excerpt": _excerpt(text, match.group(0)),
            "confidence": confidence,
            "classification_reason": reason or f"Specific {family} phrase matched in {source_section}: {match.group(0)}",
            "reported_on": reported_on,
        })

    # F04 Development & Study
    if re.search(r"\bdfs\b|definitive feasibility study|\bpfs\b|pre feasibility study|scoping study|feasibility study", normalized):
        study_status = "withdrawn" if re.search(r"withdrawn|withdrawal|retracted|retraction", normalized) else "completed" if re.search(r"(?:dfs|feasibility study).{0,45}(?:completed|released|finalised|finalized)", normalized) else "planned" if _future(normalized) else "ongoing"
        add("F04", "Definitive Feasibility Study / DFS" if re.search(r"\bdfs\b|definitive feasibility", normalized) else "Study Update / Revision", r"\bdfs\b|definitive feasibility study|\bpfs\b|pre feasibility study|scoping study|feasibility study", status=study_status)
    add("F04", "Project Delay", r"rescheduled|schedule delay|project delay|delayed|deferred|postponed", status="reported", confidence=0.95)
    if re.search(r"rescheduled|schedule delay|project delay|delayed|deferred|(?:completion|release|first ore|first production).{0,35}(?:timing|target|expected)|project schedule|development timeline", normalized):
        add("F04", "Project Schedule / Timeline Update", r"rescheduled|schedule delay|project delay|delayed|deferred|completion timing|release timing|project schedule|development timeline|first ore.{0,30}(?:expected|target)", status="planned" if _future(normalized) else "reported", confidence=0.94)
    add("F04", "Engineering / FEED Update", r"\bfeed\b|front end engineering|front end engineering design|engineering (?:work|works|update)", status="ongoing" if re.search(r"progress|ongoing|underway", normalized) else "reported")
    add("F04", "Construction Progress Update", r"construction (?:progress|update|commenced|underway)|development (?:progress|advance)[sd]?|development of .{0,45}(?:mine|project).{0,45}(?:underway|completed)", status="ongoing" if re.search(r"progress|underway", normalized) else "reported")
    add("F04", "First Ore Timing", r"first ore.{0,45}(?:expected|target|planned|schedule)|(?:expected|target|planned).{0,45}first ore", status="planned", confidence=0.93)
    add("F04", "FID Target", r"(?:final investment decision|\bfid\b).{0,45}(?:target|expected|planned)|(?:target|expected|planned).{0,45}(?:final investment decision|\bfid\b)", status="planned")
    add("F04", "CAPEX Review / Estimate Update", r"(?:capex|capital cost|capital estimate).{0,55}(?:review|estimate|update)|(?:review|update).{0,35}(?:capex|capital cost)", status="planned" if _future(normalized) else "reported")

    # F08 Financial / Operating Periodic
    add("F08", "Quarterly Activities", r"quarterly activities(?: report)?", status="reported", confidence=0.98)
    add("F08", "Periodic Cash Flow Update", r"appendix 5b|appendix 4c|quarterly cash ?flow|periodic cash ?flow", status="reported", confidence=0.98)
    add("F08", "Financial / Operating Periodic Report", r"annual report|half year(?:ly)? report|financial report|full year results|operating results", status="reported", confidence=0.96)
    add("F08", "Period-end Cash Position", r"cash and cash equivalents(?: at end of period)?|(?:cash balance|cash position|cash at bank|\$[0-9][0-9.,]*m cash)\b", confidence=0.94)
    add("F08", "Operating Cash Flow", r"net cash.{0,30}operating activities|operating cash ?flow", confidence=0.94)
    add("F08", "Investing Cash Flow", r"net cash.{0,30}investing activities|investing cash ?flow", confidence=0.94)
    add("F08", "Financing Cash Flow", r"net cash.{0,30}financing activities|financing cash ?flow", confidence=0.94)
    if not re.search(r"will fund all exploration expenditure|to fund exploration expenditure", normalized):
        add("F08", "Exploration Spend", r"exploration (?:and evaluation )?(?:expenditure|spend)", confidence=0.91)
    add("F08", "Production / Operational Periodic Update", r"quarterly production|production report|operating results|actual production|production volume", confidence=0.88)
    add("F08", "Reporting Period", r"quarter ended|reporting period|period ended", confidence=0.9)

    # F06 Funding & Capital
    add("F06", "Proposed Issue of Securities", r"proposed issue of securities|appendix 3b", status="proposed", confidence=0.98)
    add("F06", "Securities Quotation / Issue", r"application for quotation of securities|appendix 2a|notification regarding unquoted securities", status="proposed", confidence=0.98)
    add("F06", "Cessation of Securities", r"notification of cessation of securities|appendix 3h", status="reported", confidence=0.98)
    if re.search(r"\bplacement\b|institutional placement|share placement", normalized):
        status = "funds_received" if re.search(r"funds (?:received|settled)|proceeds (?:received|settled)", normalized) else "firm_commitments" if re.search(r"firm commitments?|committed to raise", normalized) else "completed" if re.search(r"placement (?:completed|settled)", normalized) else "proposed"
        add("F06", "Placement", r"institutional placement|share placement|\bplacement\b", status=status, confidence=0.96)
    if re.search(r"share purchase plan|\bspp\b", normalized):
        status = "completed" if re.search(r"(?:spp|share purchase plan).{0,35}(?:completed|closed)", normalized) else "planned" if re.search(r"launched|proposed|offer|will", normalized) else "reported"
        add("F06", "Share Purchase Plan / SPP", r"share purchase plan|\bspp\b", status=status, confidence=0.96)
    add("F06", "Rights Issue", r"rights issue|rights offer", status="proposed" if _future(normalized) else "reported")
    add("F06", "Entitlement Offer", r"entitlement offer|entitlement issue", status="proposed" if _future(normalized) else "reported")
    add("F06", "Debt Facility", r"debt facility|loan facility|credit facility|facility agreement", status="proposed" if re.search(r"proposed|term sheet|subject to", normalized) else "reported")
    add("F06", "Convertible Note", r"convertible notes?|convertible loan|convertible funding", status="proposed" if _future(normalized) else "reported")
    if re.search(r"capital raising|capital raise|raise[sd]?\s+(?:a?\$)?[0-9]", normalized):
        status = "funds_received" if re.search(r"funds received|proceeds received", normalized) else "firm_commitments" if re.search(r"firm commitments?", normalized) else "proposed"
        add("F06", "Capital Raising", r"capital raising|capital raise|raise[sd]?\s+(?:a?\$)?[0-9]", status=status)
    add("F06", "Issue Price", r"issue price|\$[0-9.]+ per share", status="proposed" if _future(normalized) else "reported")

    # F02 Resource & Reserve -- formal updates only; resource drilling and
    # historical/contextual resource references are intentionally excluded.
    historical_resource = bool(re.search(r"historical|previously reported|existing resource|current resource|resource drilling|future resource|upcoming resource|supports?.{0,20}resource", normalized))
    if re.search(r"mineral resource (?:withdrawn|withdrawal)|withdrawal of (?:the )?mineral resource", normalized):
        add("F02", "Mineral Resource Withdrawal", r"mineral resource (?:withdrawn|withdrawal)|withdrawal of (?:the )?mineral resource", status="withdrawn", confidence=0.98)
    elif re.search(r"maiden mineral resource|maiden mre", normalized):
        if not _future(normalized):
            add("F02", "Maiden Mineral Resource", r"maiden mineral resource|maiden mre", confidence=0.97)
    elif re.search(r"mineral resource (?:estimate|update|upgrade|reclassification|restatement)|updated mineral resource|\bmre (?:update|estimate)\b|resource (?:grows?|growth|increase[sd]?|expanded)", normalized) and not historical_resource:
        add("F02", "Mineral Resource Update", r"mineral resource (?:estimate|update|upgrade|reclassification|restatement)|updated mineral resource|\bmre (?:update|estimate)\b|resource (?:grows?|growth|increase[sd]?|expanded)", confidence=0.95)
    if re.search(r"ore reserve (?:withdrawn|withdrawal)|withdrawal of (?:the )?ore reserve", normalized):
        add("F02", "Ore Reserve Withdrawal", r"ore reserve (?:withdrawn|withdrawal)|withdrawal of (?:the )?ore reserve", status="withdrawn", confidence=0.98)
    elif re.search(r"maiden ore reserve|maiden reserve", normalized):
        add("F02", "Maiden Ore Reserve", r"maiden ore reserve|maiden reserve", confidence=0.97)
    elif re.search(r"ore reserve (?:estimate|update|upgrade|reclassification|restatement)|updated ore reserve|reserve (?:has )?(?:grows?|grown|growth|increase[sd]?|expanded)", normalized):
        add("F02", "Ore Reserve Update", r"ore reserve (?:estimate|update|upgrade|reclassification|restatement)|updated ore reserve|reserve (?:has )?(?:grows?|grown|growth|increase[sd]?|expanded)", confidence=0.97)

    # F01 Exploration & Drilling
    add("F01", "Drilling Results / Assay Results", r"drill(?:ing)? results|assay results|reported intersections?|[0-9.]+m\s*@\s*[0-9.]", confidence=0.95)
    add("F01", "Drilling Completed", r"(?:rc|diamond|aircore|resource)?\s*drilling (?:is )?complete[sd]?|drill(?:ing)? program(?:me)? completed", confidence=0.94)
    if re.search(r"drill(?:ing)? program(?:me)?|rc drilling|diamond drilling|aircore drilling", normalized) and not re.search(r"complete[sd]?|results?|assay", normalized):
        add("F01", "Drill Programme", r"drill(?:ing)? program(?:me)?|rc drilling|diamond drilling|aircore drilling", status="planned" if _future(normalized) else "ongoing")

    # F03 Metallurgy & Processing
    if re.search(r"metallurgical test(?:work| work)|metallurgy test(?:work| work)|process testwork", normalized):
        planned_testwork = bool(re.search(r"(?:further|planned|will).{0,80}(?:metallurgical|process) test(?:work| work)|(?:metallurgical|process) test(?:work| work).{0,80}\bwill\b", normalized))
        status = "planned" if planned_testwork else "reported"
        event_type = "Metallurgical Testwork Planned / Commenced" if status == "planned" else "Metallurgical Test Results" if re.search(r"results?|generated|achieved|average recovery|product grade", normalized) else "Metallurgical Testwork Update"
        add("F03", event_type, r"metallurgical test(?:work| work)|metallurgy test(?:work| work)|process testwork", status=status, confidence=0.95)
    add("F03", "Recovery / Product Grade", r"(?:testwork|composite|sample).{0,100}(?:recovery|product grade)|(?:recovery|product grade).{0,100}(?:testwork|composite|sample)", confidence=0.94)
    add("F03", "Processing Route", r"whole of ore flotation|processing route|process flowsheet|beneficiation route", confidence=0.91)
    add("F03", "Pilot Plant", r"pilot plant|pilot scale|demonstration plant", status="planned" if _future(normalized) else "reported")

    # F05 Permitting & Project Access
    add("F05", "Mining Lease Application", r"mining lease application(?: has been)? (?:submitted|lodged)|submitted.{0,35}mining lease application", status="submitted", confidence=0.98)
    add("F05", "Mining Lease Grant", r"mining lease (?:has been )?(?:granted|approved)|grant of (?:the )?mining lease", status="granted", confidence=0.98)
    if re.search(r"clearing permit|vegetation clearing permit", normalized):
        status = "granted" if re.search(r"(?:approved|granted|in force|no appeal)", normalized) else "pending" if _future(normalized) else "reported"
        add("F05", "Clearing Permit Status", r"vegetation clearing permit|clearing permit", status=status, confidence=0.94)
    if re.search(r"groundwater licen[cs]e|water licen[cs]e", normalized):
        status = "technical_support" if re.search(r"technical support|support for the grant", normalized) else "granted" if re.search(r"licen[cs]e (?:secured|granted|approved|issued)", normalized) else "application" if re.search(r"application|applied", normalized) else "pending"
        add("F05", "Groundwater Licence Status", r"groundwater licen[cs]e|water licen[cs]e", status=status, confidence=0.94)
    if re.search(r"environmental approval|environmental review document|\berd\b|works approval", normalized):
        status = "granted" if re.search(r"approval (?:granted|received)|approved", normalized) and not _future(normalized) else "pending" if _future(normalized) else "submitted" if re.search(r"submitted|lodged", normalized) else "pending"
        event_type = "Environmental Approval Granted" if status == "granted" else "Environmental Approval Status"
        add("F05", event_type, r"environmental approval|environmental review document|\berd\b|works approval", status=status, confidence=0.91)
    add("F05", "Land Access / Native Title", r"land access agreement|native title agreement|access agreement", status="reported")

    # F07 Commercial & Corporate Transaction
    if re.search(r"farm[- ]in|farm[- ]out|earn[- ]in", normalized):
        add("F07", "Farm-in / Farm-out", r"farm[- ]in|farm[- ]out|earn[- ]in", status="proposed" if re.search(r"non binding|proposed|option", normalized) else "reported", confidence=0.96)
    if re.search(r"earn[- ]in", normalized):
        add("F07", "Earn-in", r"earn[- ]in", status="conditional" if re.search(r"up to|can acquire|subject to|phase", normalized) else "reported", confidence=0.96)
    if re.search(r"joint venture|\bjv agreement\b", normalized) and not re.search(r"joint venture partnering|potential joint venture|future joint venture", normalized):
        add("F07", "Joint Venture", r"joint venture|\bjv agreement\b", status="reported", confidence=0.94)
    if re.search(r"project acquisition|asset acquisition|acquisition of|acquired .{0,35}(?:project|asset|rights?)", normalized):
        add("F07", "Project / Asset Acquisition", r"project acquisition|asset acquisition|acquisition of|acquired .{0,35}(?:project|asset|rights?)", status="completed" if re.search(r"completed|completion|has acquired|wildcat acquired", normalized) else "proposed")
    add("F07", "Asset Sale / Disposal", r"asset sale|project sale|asset disposal|project disposal|divestment", status="completed" if re.search(r"completed|completion", normalized) else "proposed")
    add("F07", "Option Agreement", r"option agreement", status="reported")
    add("F07", "Binding Agreement", r"binding agreement|binding term sheet", status="reported")
    add("F07", "Transaction Completion", r"transaction (?:completed|completion)|completion of (?:the )?(?:acquisition|sale)", status="completed")

    return events


def _normalise(text: str) -> str:
    value = (text or "").casefold().replace("–", "-").replace("—", "-")
    value = re.sub(r"pre-feasibility", "pre feasibility", value)
    return re.sub(r"\s+", " ", value).strip()


def _future(text: str) -> bool:
    return bool(re.search(r"\bwill\b|\bplanned\b|\bproposed\b|\btarget(?:ed)?\b|\bexpected\b|\bforecast\b|to be|intends? to|launched", text))


def _excerpt(text: str, phrase: str) -> str:
    match = re.search(re.escape(phrase), text, re.I)
    if not match:
        return text.strip()[:1500]
    start = max(0, text.rfind("\n", 0, max(0, match.start() - 450)) + 1)
    end = text.find("\n", min(len(text), match.end() + 850))
    return text[start:(end if end >= 0 else min(len(text), match.end() + 850))].strip()[:1500]


def _json_list(values: tuple[str, ...]) -> str:
    import json
    return json.dumps(list(values), ensure_ascii=False)
