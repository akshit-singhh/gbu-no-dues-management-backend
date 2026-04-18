# app/core/department_roles.py

from app.models.user import UserRole

# ==========================================================
# DEPARTMENT ID MAPPING
# (MATCHED TO YOUR DB DUMP)
# ==========================================================
# Depts start from ID 14 in your database
DEPT_ID_LIBRARY = 14
DEPT_ID_HOSTEL = 15
DEPT_ID_SPORTS = 16
DEPT_ID_LABS = 17
DEPT_ID_CRC = 18
DEPT_ID_ACCOUNTS = 19

# ==========================================================
# ROLE PERMISSIONS
# ==========================================================
DEPARTMENT_ROLE_MAP = {
    # Super User
    UserRole.Admin: "ALL",

    # Flow B: High Level Approvers
    UserRole.Dean: "SCHOOL_LEVEL", 
    
    # HODs are linked to Academic Depts (IDs 1-13)
    UserRole.HOD: "ASSIGNED",       

    # Flow B: Parallel Approvers (Administrative)
    # Generic Staff Role (The main one used now)
    UserRole.Staff: "ASSIGNED",

    # Legacy Role Support (If any old users still have these roles)
    UserRole.Library: [DEPT_ID_LIBRARY],
    UserRole.Hostel: [DEPT_ID_HOSTEL],
    UserRole.Sports: [DEPT_ID_SPORTS],
    UserRole.Lab: [DEPT_ID_LABS],
    UserRole.CRC: [DEPT_ID_CRC],
    UserRole.Account: [DEPT_ID_ACCOUNTS],

    # Students have no approval power
    UserRole.Student: [],
}

# ==========================================================
# UI LABELS (For Frontend / Notifications)
# ==========================================================
DEPARTMENT_LABELS = {
    DEPT_ID_LIBRARY: "University Library",
    DEPT_ID_HOSTEL: "Hostel Administration",
    DEPT_ID_SPORTS: "Sports Department",
    DEPT_ID_LABS: "Laboratories",
    DEPT_ID_CRC: "Corporate Relations Cell",
    DEPT_ID_ACCOUNTS: "Finance & Accounts",
}