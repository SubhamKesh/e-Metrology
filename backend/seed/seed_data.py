"""
backend/seed/seed_data.py

Static, readable seed data consumed by seed.py. IDs here are human-readable
strings ("usr_owner_001") — seed.py rewrites them into real MongoDB
ObjectIds when it inserts each document, and remaps every foreign key
(owner_id, instrument_id, assigned_officer_id, ...) to match.

Passwords are plaintext here on purpose — seed.py hashes them through
app/utils/security.py before insert. Never insert this data directly.
"""

USERS = [
    {
        "id": "usr_owner_001",
        "name": "Rahul Sharma",
        "email": "rahul.sharma@example.com",
        "password": "seed-pass-001",
        "role": "owner",
        "org_type": None,
        "org_name": "Sharma General Store",
        "contact": "9830012345",
    },
    {
        "id": "usr_owner_002",
        "name": "Priya Das",
        "email": "priya.das@example.com",
        "password": "seed-pass-002",
        "role": "owner",
        "org_type": None,
        "org_name": "Das Fuel Station",
        "contact": "9830023456",
    },
    {
        "id": "usr_owner_003",
        "name": "Manoj Verma",
        "email": "manoj.verma@example.com",
        "password": "seed-pass-003",
        "role": "owner",
        "org_type": None,
        "org_name": "Verma Traders",
        "contact": "9830034567",
    },
    {
        "id": "usr_lmo_001",
        "name": "Inspector Anjali Roy",
        "email": "anjali.roy@legalmetrology.gov.in",
        "password": "seed-pass-004",
        "role": "lmo",
        "org_type": "LMO",
        "org_name": "West Bengal Legal Metrology Office",
        "contact": "9830045678",
    },
    {
        "id": "usr_gatc_001",
        "name": "GATC Officer Sanjay Ghosh",
        "email": "sanjay.ghosh@gatc-kolkata.in",
        "password": "seed-pass-005",
        "role": "gatc",
        "org_type": "GATC",
        "org_name": "Kolkata Government Approved Test Centre",
        "contact": "9830056789",
    },
    {
        "id": "usr_admin_001",
        "name": "Admin Sourav Banerjee",
        "email": "admin@legalmetrology.gov.in",
        "password": "seed-pass-006",
        "role": "admin",
        "org_type": None,
        "org_name": "Directorate of Legal Metrology",
        "contact": "9830067890",
    },
]

INSTRUMENTS = [
    {
        "id": "inst_001",
        "owner_id": "usr_owner_001",
        "type": "Electronic Weighing Machine",
        "manufacturer": "Avery",
        "model": "AWS-200",
        "capacity": "30 kg",
        "serial_no": "AWS200-2024-0001",
        "location": "Baharampur, West Bengal",
    },
    {
        "id": "inst_002",
        "owner_id": "usr_owner_001",
        "type": "Electronic Weighing Machine",
        "manufacturer": "Avery",
        "model": "AWS-100",
        "capacity": "10 kg",
        "serial_no": "AWS100-2024-0002",
        "location": "Baharampur, West Bengal",
    },
    {
        "id": "inst_003",
        "owner_id": "usr_owner_002",
        "type": "Fuel Dispensing Unit",
        "manufacturer": "Gilbarco",
        "model": "GX-500",
        "capacity": "N/A",
        "serial_no": "GX500-2023-0451",
        "location": "Murshidabad, West Bengal",
    },
    {
        "id": "inst_004",
        "owner_id": "usr_owner_003",
        "type": "Platform Scale",
        "manufacturer": "Essae",
        "model": "PS-500",
        "capacity": "500 kg",
        "serial_no": "PS500-2022-0812",
        "location": "Kolkata, West Bengal",
    },
]

APPLICATIONS = [
    {
        "id": "app_001",
        "instrument_id": "inst_001",
        "owner_id": "usr_owner_001",
        "status": "certified",
        "assigned_officer_id": "usr_lmo_001",
        "submitted_at": "2025-08-01T10:00:00Z",
    },
    {
        "id": "app_002",
        "instrument_id": "inst_002",
        "owner_id": "usr_owner_001",
        "status": "scheduled",
        "assigned_officer_id": "usr_lmo_001",
        "submitted_at": "2026-08-20T09:30:00Z",
    },
    {
        "id": "app_003",
        "instrument_id": "inst_003",
        "owner_id": "usr_owner_002",
        "status": "submitted",
        "assigned_officer_id": None,
        "submitted_at": "2026-09-01T11:15:00Z",
    },
    {
        "id": "app_004",
        "instrument_id": "inst_004",
        "owner_id": "usr_owner_003",
        "status": "expiring",
        "assigned_officer_id": "usr_gatc_001",
        "submitted_at": "2025-09-10T08:00:00Z",
    },
]

INSPECTIONS = [
    {
        "id": "insp_001",
        "application_id": "app_001",
        "officer_id": "usr_lmo_001",
        "observations": "Weighing accuracy within tolerance across all test loads.",
        "result": "pass",
        "photos": [],
        "inspected_at": "2025-08-05T13:00:00Z",
    },
    {
        "id": "insp_002",
        "application_id": "app_004",
        "officer_id": "usr_gatc_001",
        "observations": "Platform scale calibrated and verified against standard weights.",
        "result": "pass",
        "photos": [],
        "inspected_at": "2025-09-15T14:30:00Z",
    },
]

CERTIFICATES = [
    {
        "id": "LM-2025-0001A",
        "application_id": "app_001",
        "instrument_id": "inst_001",
        "verified_on": "2025-08-05T13:00:00Z",
        "valid_until": "2026-08-05T13:00:00Z",
    },
    {
        "id": "LM-2025-0004A",
        "application_id": "app_004",
        "instrument_id": "inst_004",
        "verified_on": "2025-09-15T14:30:00Z",
        "valid_until": "2026-09-15T14:30:00Z",
    },
]

ALERTS = [
    {
        "certificate_id": "LM-2025-0004A",
        "owner_id": "usr_owner_003",
        "type": "expiry_reminder",
        "message": "Your Platform Scale (PS500-2022-0812) verification expires in 9 days.",
        "sent_at": "2026-09-06T06:00:00Z",
    },
]
