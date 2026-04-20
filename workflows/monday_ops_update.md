# Monday Morning Ops Update — NA Coffee Book

## Objective
Produce the weekly operational update for the North American coffee import book. Read emails forwarded from Vidya Global Coffee, extract shipment data, generate an Excel report, and create a ClickUp task with the summary and Excel attached.

---

## Inputs
- Gmail inbox (thomasraad@gmail.com) — emails forwarded from Outlook by Outlook forwarding rules
- Previous week's data is described in the "Changes This Week" section (first run = baseline)

---

## Step 1: Fetch Emails via Gmail MCP

Search Gmail for emails from Vidya Global Coffee ops team from the past 14 days:

```
from:(rim@vidyaglobal.coffee OR traffic@vidyaglobal.coffee OR eleni.mulugeta@vidyaglobal.coffee OR carmen@vidyaglobal.coffee OR usa@vidyaglobal.coffee OR pho.luong@vidyaglobal.coffee) newer_than:14d
```

Read each email thread in full. Collect all bodies together.

---

## Step 2: Extract Structured Data (Claude parses directly)

From the email bodies, extract two categories:

### Active Shipments
For each vessel/BL reference found, extract all available fields:
- `vessel` — ship name
- `origin` — country of loading (Colombia, Ethiopia, Brazil, Guatemala, Peru, etc.)
- `grade` — coffee grade/description
- `quantity_mt` — metric tons (number only)
- `quantity_bags` — number of bags (number only)
- `bl_number` — bill of lading number
- `etd` — estimated departure date from origin port (YYYY-MM-DD or as stated)
- `eta_us` — estimated arrival at US port (YYYY-MM-DD or as stated)
- `dest_port` — US destination port (New York, Houston, New Orleans, etc.)
- `contract_ref` — contract or lot reference number
- `counterparty` — buyer/seller name if mentioned
- `status` — current status (e.g., "On the water", "Loading", "At discharge port", "Cleared customs")
- `last_update_date` — date of most recent email mentioning this shipment
- `source_email` — sender email address

Deduplicate by vessel name + BL number. If the same vessel appears in multiple emails, merge the data taking the most recent values.

### Pending Subjects
Unresolved contract obligations — price fixing deadlines, quality approvals, missing documents, shipping instruction deadlines:
- `reference` — contract/lot reference
- `subject_type` — type (e.g., "Price Fixing", "Quality Approval", "Shipping Docs", "L/C Amendment")
- `description` — brief description of what's needed
- `due_date` — deadline if mentioned
- `reported_by` — sender
- `urgency` — "HIGH" if deadline is within 3 days or marked urgent, otherwise "NORMAL"
- `source_email_date` — email date

### Email Log
For each email processed, record:
- `date`, `from`, `subject`, `vessel_found` (list), `bl_found` (list), `pending_subjects` (list)

---

## Step 3: Write Structured JSON

Write the extracted data to `.tmp/shipments.json`:

```json
{
  "active_shipments": [...],
  "pending_subjects": [...],
  "email_log": [...],
  "email_count": 5,
  "generated_at": "2026-04-21T07:00:00"
}
```

Write `.tmp/changes.json`. On first run, write:

```json
{
  "baseline": true,
  "note": "First run — no previous data to compare against.",
  "new_shipments": [],
  "removed_shipments": [],
  "updated_shipments": [],
  "resolved_subjects": []
}
```

---

## Step 4: Generate Excel Report

Run the report generator:

```bash
python3 tools/generate_excel.py
```

This produces `.tmp/ops_report_YYYY-MM-DD.xlsx` with 5 tabs:
- **Active Shipments** — all vessels sorted by ETA, red = overdue, yellow = arriving this week
- **By Origin** — grouped by country with MT/bags subtotals per origin
- **Changes This Week** — new, updated, removed vs last week
- **Pending Subjects** — sorted by urgency
- **Email Log** — all emails processed

---

## Step 5: Create ClickUp Task with Excel Attached

Use the ClickUp MCP to:

1. **Create task** in list `901713076750`:
   - Name: `☕ Ops Report — [Day] [Month DD, YYYY]` (e.g., `☕ Ops Report — Mon Apr 21, 2026`)
   - Priority: High (2)
   - Description: structured markdown summary (see format below)

2. **Attach the Excel file** to the task using `clickup_attach_task_file` with the path to `.tmp/ops_report_YYYY-MM-DD.xlsx`

### ClickUp Task Description Format

```markdown
## 📦 Active Shipments (N vessels)

| Vessel | Origin | Grade | Qty MT | BL # | ETD | ETA US | Port | Status |
|---|---|---|---|---|---|---|---|---|
[one row per shipment, sorted by ETA]

---

## 🔄 Changes This Week

[new shipments, removed, ETA/status changes vs last week — or "First run — baseline week" if no prior data]

---

## ⚠️ Pending Subjects (N items)

| Urgency | Reference | Subject | Due | Contact |
|---|---|---|---|---|
[🔴 HIGH or NORMAL]

---

## 📋 Summary

Processed N emails from Vidya Global Coffee ops team ([date range]).
```

---

## Edge Cases

- **No emails found**: Write baseline JSON, generate empty report, create ClickUp task noting "No ops emails received this week."
- **Missing fields**: Leave as null — the Excel generator handles nulls gracefully.
- **Duplicate vessels**: Merge by vessel + BL reference, keep most recent values.

---

## Output

- `.tmp/shipments.json` — structured data
- `.tmp/changes.json` — week-over-week diff
- `.tmp/ops_report_YYYY-MM-DD.xlsx` — Excel report
- ClickUp task in list 901713076750 with Excel attached
