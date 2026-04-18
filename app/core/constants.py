# app/core/constants.py

from app.models.user import UserRole

# ==========================================================
# DEPARTMENT CODES (Must match 'code' column in DB)
# ==========================================================
DEPT_CODE_LIBRARY = "LIB"
DEPT_CODE_HOSTEL = "HST"
DEPT_CODE_SPORTS = "SPT"
DEPT_CODE_ACCOUNTS = "ACC"
DEPT_CODE_LABS = "LAB"
DEPT_CODE_CRC = "CRC"

# ==========================================================
# ROLE PERMISSIONS
# ==========================================================
DEPARTMENT_ROLE_MAP = {
    # --- CORE ROLES ---
    UserRole.Admin: "ALL",
    UserRole.Student: [],
    
    # --- ACADEMIC FLOW ---
    UserRole.Dean: "SCHOOL_LEVEL",  # Uses school_id
    UserRole.HOD: "ASSIGNED",       # Uses department_id (Academic)

    # --- ADMINISTRATIVE FLOW (New Architecture) ---
    # In Flow B, all Dept Authorities (Library, Sports, Office, Accounts)
    # share the 'Staff' role and are distinguished by department_id/school_id.
    UserRole.Staff: "ASSIGNED", 

    # --- LEGACY ROLES (Deprecated but kept for backward compatibility) ---
    # These are effectively dead for new users, but kept if old users exist.
    UserRole.Library: [DEPT_CODE_LIBRARY],
    UserRole.Hostel: [DEPT_CODE_HOSTEL],
    UserRole.Account: [DEPT_CODE_ACCOUNTS],
    UserRole.Sports: [DEPT_CODE_SPORTS],
    UserRole.Lab: [DEPT_CODE_LABS],
    UserRole.CRC: [DEPT_CODE_CRC],
}