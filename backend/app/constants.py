"""Exact workbook vocabularies. Do not rename these values - they mirror the workbook dropdowns."""

DEMO_SHEET = "Demos_and_Pipelines"
REVENUE_SHEET = "League_Revenue"

# The 13 tracked demo fields, in the workbook's actual column order (Demo Type sits before Demo On).
DEMO_HEADERS = [
    "Sl No", "BD", "Customer Name", "Domain", "Country", "Demo Type", "Demo On", "Demo Date",
    "Demo Time", "Time Zone", "Time Remaining", "Status", "Qualified Demo",
]
# Columns present in the live workbook that the administrator chose not to track (2026-11-03).
DEMO_IGNORED_HEADERS = ["Links", "Discovery", "Customer Asks", "Comments", "Follow Up On", "Follow Up In"]

REVENUE_HEADERS = [
    "Sl No", "BD", "Customer Name", "Country", "Domain", "Opportunity Name", "Contract Status",
    "Currency", "Contract Value", "Contract Signed Date", "Amount Credited Date",
    "Customer Onboarding Date", "Remarks",
]

DEMO_TYPES = ["F2F", "Virtual"]

DEMO_STATUSES = [
    "Scheduled", "Completed", "No Show", "Rescheduled", "Cancelled", "Awaiting Demo Date",
    "Pipeline", "POC Initiated", "POC In Progress", "POC Completed", "POC Paused",
]
POC_STATUSES = ["POC Initiated", "POC In Progress", "POC Completed", "POC Paused"]
QUALIFIED_VALUES = ["Yes", "No"]

CONTRACT_STATUSES = ["Signed", "Amount Credited"]

# Dropdown lists found in the workbook - offered as suggestions in the UI (free text still allowed
# because the workbook already contains values outside them).
DEMO_ON_OPTIONS = [
    "Application KT", "POC Delivery", "Product Demo", "Followup call", "POC Discussion",
    "Next Step Discussion", "Initial Discussion & Discovery", "Commercials Discussion", "Channel Partnership",
]
OPPORTUNITY_OPTIONS = ["Accessibility Testing", "Device Farm", "FireFlink License", "Performance Testing", "Resources"]
CURRENCY_OPTIONS = ["INR", "USD"]

DAILY_STATUS = [
    "Not Started", "In Progress", "Target Pending Today", "Target Achieved", "Target Missed",
    "Carry-Forward Pending",
]
