from sqlmodel import select
from loguru import logger
from app.models.school import School
from app.models.department import Department
from app.models.academic import Programme, Specialization # ✅ New Models
from app.models.user import User, UserRole
from app.services.auth_service import get_user_by_email, create_user
from app.core.database import AsyncSessionLocal
from app.core.config import settings

# ----------------------------------------------------------------
# 1. DEFINE STATIC DATA
# ----------------------------------------------------------------

SCHOOLS_DATA = [
    {"name": "School of Information & Communication Technology", "code": "SOICT"},
    {"name": "School of Engineering", "code": "SOE"},
    {"name": "School of Management", "code": "SOM"},
    {"name": "School of Biotechnology", "code": "SOBT"},
    {"name": "School of Vocational Studies & Applied Sciences", "code": "SOVSAS"},
    {"name": "School of Law, Justice & Governance", "code": "SOLJ"},
    {"name": "School of Humanities & Social Sciences", "code": "SOHSS"},
    {"name": "School of Architecture & Planning", "code": "SOAP"},
]

# Map Departments to their Parent School Code
ACADEMIC_MAPPING = {
    "SOICT":  ["CSE", "IT", "ECE", "AI", "CA"], # ✅ Added CA (Computer Applications)
    "SOE":    ["ME", "CE", "EE"],
    "SOBT":   ["BT"],
    "SOM":    ["MGMT"],
    "SOLJ":   ["LAW"],
    "SOHSS":  ["HSS", "POL"],
    "SOAP":   ["AP"],
    "SOVSAS": ["MATH", "PHY"]
}

DEPARTMENTS_DATA = [
    # Phase 1: Academic
    {"name": "Computer Science & Engineering", "code": "CSE", "phase_number": 1},
    {"name": "Information Technology", "code": "IT", "phase_number": 1},
    {"name": "Electronics & Communication", "code": "ECE", "phase_number": 1},
    {"name": "Computer Applications", "code": "CA", "phase_number": 1}, # ✅ Added for BCA/MCA
    
    {"name": "Mechanical Engineering", "code": "ME", "phase_number": 1},
    {"name": "Civil Engineering", "code": "CE", "phase_number": 1},
    {"name": "Electrical Engineering", "code": "EE", "phase_number": 1},
    {"name": "Artificial Intelligence", "code": "AI", "phase_number": 1},
    {"name": "Biotechnology", "code": "BT", "phase_number": 1},
    {"name": "Management Studies", "code": "MGMT", "phase_number": 1},
    {"name": "Law & Justice", "code": "LAW", "phase_number": 1},
    {"name": "Humanities & Social Sciences", "code": "HSS", "phase_number": 1},
    {"name": "Architecture & Planning", "code": "AP", "phase_number": 1},
    {"name": "Applied Mathematics", "code": "MATH", "phase_number": 1},
    {"name": "Applied Physics", "code": "PHY", "phase_number": 1},
    {"name": "Political Science", "code": "POL", "phase_number": 1},
    
    # Phase 2: Administrative (Parallel)
    {"name": "University Library", "code": "LIB", "phase_number": 2},
    {"name": "Hostel Administration", "code": "HST", "phase_number": 2},
    {"name": "Sports Department", "code": "SPT", "phase_number": 2},
    {"name": "Laboratories", "code": "LAB", "phase_number": 2},
    {"name": "Corporate Relations Cell", "code": "CRC", "phase_number": 2},
    {"name": "Exam", "code": "EX", "phase_number": 2},
    
    # Phase 3: Final
    {"name": "Finance & Accounts", "code": "ACC", "phase_number": 3},
]

# NEW: Define Programmes & Specializations Mapping
PROGRAMME_DATA = {
    "CSE": [
        {"name": "B.Tech (CSE)", "code": "BTECH_CSE", "specs": [
            {"name": "Core / General", "code": "CSE_CORE"}
        ]},
        {"name": "B.Tech (CSE) Specialization", "code": "BTECH_CSE_SPEC", "specs": [
            {"name": "Artificial Intelligence (AI)", "code": "CSE_AI"},
            {"name": "Cyber Security (CS)", "code": "CSE_CYBER"},
            {"name": "Data Science (DS)", "code": "CSE_DS"}
        ]},
        {"name": "Integrated B.Tech + M.Tech", "code": "INT_BTECH_MTECH", "specs": [
            {"name": "Core / General", "code": "INT_CSE_CORE"}
        ]},
        {"name": "M.Tech (Specialization)", "code": "MTECH_CSE_SPEC", "specs": [
            {"name": "AI and Robotics", "code": "MTECH_AI_ROBO"},
            {"name": "Software Engineering (SE)", "code": "MTECH_SE"},
            {"name": "Data Science (DS)", "code": "MTECH_DS"}
        ]},
        {"name": "M.Tech (Working Professional)", "code": "MTECH_CSE_WP", "specs": [
            {"name": "Working Professional", "code": "MTECH_WP_GEN"}
        ]},
        {"name": "Doctoral (PhD)", "code": "PHD_CSE", "specs": [
            {"name": "Research Scholar", "code": "PHD_CSE_GEN"}
        ]}
    ],
    "ECE": [
        {"name": "B.Tech (ECE)", "code": "BTECH_ECE", "specs": [
            {"name": "Core / General", "code": "ECE_CORE"}
        ]},
        {"name": "B.Tech (ECE) Specialization", "code": "BTECH_ECE_SPEC", "specs": [
            {"name": "AI and Machine Learning", "code": "ECE_AI_ML"},
            {"name": "VLSI and Embedded Systems", "code": "ECE_VLSI_ES"}
        ]},
        {"name": "Integrated B.Tech (ECE)", "code": "INT_ECE", "specs": [
            {"name": "Core / General", "code": "INT_ECE_CORE"}
        ]},
        {"name": "M.Tech (Specialization)", "code": "MTECH_ECE_SPEC", "specs": [
            {"name": "AI and Robotics", "code": "MTECH_ECE_AI_ROBO"},
            {"name": "VLSI Design", "code": "MTECH_ECE_VLSI"},
            {"name": "Wireless Comm. & Networks (WCN)", "code": "MTECH_ECE_WCN"}
        ]},
        {"name": "Doctoral (PhD)", "code": "PHD_ECE", "specs": [
            {"name": "Research Scholar", "code": "PHD_ECE_GEN"}
        ]}
    ],
    "IT": [
        {"name": "B.Tech (IT)", "code": "BTECH_IT", "specs": [
            {"name": "Core / General", "code": "IT_CORE"}
        ]},
        {"name": "B.Tech (IT) Specialization", "code": "BTECH_IT_SPEC", "specs": [
            {"name": "Data Science and ML", "code": "IT_DS_ML"}
        ]},
        {"name": "M.Tech (Specialization)", "code": "MTECH_IT_SPEC", "specs": [
            {"name": "Data Science and ML", "code": "MTECH_IT_DS_ML"}
        ]},
        {"name": "Doctoral (PhD)", "code": "PHD_IT", "specs": [
            {"name": "Research Scholar", "code": "PHD_IT_GEN"}
        ]}
    ],
    "CA": [
        {"name": "Bachelor of Computer Applications (BCA)", "code": "BCA", "specs": [
            {"name": "Core / General", "code": "BCA_CORE"}
        ]},
        {"name": "BCA (Specialization)", "code": "BCA_SPEC", "specs": [
            {"name": "AI and Machine Learning", "code": "BCA_AI_ML"}
        ]},
        {"name": "Master of Computer Applications (MCA)", "code": "MCA", "specs": [
            {"name": "Core / General", "code": "MCA_CORE"}
        ]},
        {"name": "MCA (Specialization)", "code": "MCA_SPEC", "specs": [
            {"name": "Data Science and ML", "code": "MCA_DS_ML"}
        ]},
        {"name": "Doctoral (PhD)", "code": "PHD_CA", "specs": [
            {"name": "Research Scholar", "code": "PHD_CA_GEN"}
        ]}
    ]
}


# ----------------------------------------------------------------
# 2. SEEDING FUNCTIONS
# ----------------------------------------------------------------

async def seed_all():
    """Master function to run all seeding logic."""
    async with AsyncSessionLocal() as session:
        try:
            await seed_schools(session)
            await seed_departments(session)
            await link_departments_to_schools(session)
            await seed_academic_hierarchy(session) # ✅ NEW STEP
            await seed_admin_user(session)
            
            await session.commit()
            logger.success("✨ Seeding & Linking Complete.")
        except Exception as e:
            logger.error(f"❌ Seeding Failed: {e}")
            await session.rollback()

async def seed_schools(session):
    for s in SCHOOLS_DATA:
        stmt = select(School).where(School.code == s["code"])
        result = await session.execute(stmt)
        if not result.scalar_one_or_none():
            logger.info(f"🌱 Creating School: {s['name']}")
            session.add(School(name=s["name"], code=s["code"]))
    await session.flush() 

async def seed_departments(session):
    for d in DEPARTMENTS_DATA:
        stmt = select(Department).where(Department.code == d["code"])
        result = await session.execute(stmt)
        dept_obj = result.scalar_one_or_none()
        
        if not dept_obj:
            logger.info(f"🌱 Creating Department: {d['name']}")
            session.add(Department(name=d["name"], code=d["code"], phase_number=d["phase_number"]))
        else:
            if dept_obj.phase_number != d["phase_number"]:
                logger.warning(f"🔧 Fixing Phase for {d['code']}")
                dept_obj.phase_number = d["phase_number"]
                session.add(dept_obj)
    await session.flush()

async def link_departments_to_schools(session):
    """Links Academic Departments to their parent Schools."""
    for school_code, dept_codes in ACADEMIC_MAPPING.items():
        school = (await session.execute(select(School).where(School.code == school_code))).scalar_one_or_none()
        if not school:
            continue

        stmt = select(Department).where(Department.code.in_(dept_codes))
        results = await session.execute(stmt)
        depts = results.scalars().all()

        for dept in depts:
            if dept.school_id != school.id:
                dept.school_id = school.id
                session.add(dept)
                logger.info(f"🔗 Linked {dept.code} -> {school.code}")
    await session.flush()

# NEW: SEED PROGRAMMES & SPECIALIZATIONS
async def seed_academic_hierarchy(session):
    for dept_code, programmes in PROGRAMME_DATA.items():
        # 1. Find the Department
        dept_res = await session.execute(select(Department).where(Department.code == dept_code))
        department = dept_res.scalar_one_or_none()
        
        if not department:
            logger.warning(f"⚠️ Dept {dept_code} not found. Skipping academic seeding.")
            continue

        for prog_data in programmes:
            # 2. Find or Create Programme
            p_res = await session.execute(select(Programme).where(Programme.code == prog_data["code"]))
            programme = p_res.scalar_one_or_none()

            if not programme:
                logger.info(f"📘 Creating Programme: {prog_data['name']} ({dept_code})")
                programme = Programme(
                    name=prog_data["name"],
                    code=prog_data["code"],
                    department_id=department.id
                )
                session.add(programme)
                await session.flush() # Need ID for Specialization
            
            # 3. Find or Create Specializations
            for spec_data in prog_data["specs"]:
                s_res = await session.execute(select(Specialization).where(Specialization.code == spec_data["code"]))
                specialization = s_res.scalar_one_or_none()

                if not specialization:
                    logger.info(f"   ↳ Creating Specialization: {spec_data['name']}")
                    session.add(Specialization(
                        name=spec_data["name"],
                        code=spec_data["code"],
                        programme_id=programme.id
                    ))

async def seed_admin_user(session):
    if settings.ADMIN_EMAIL and settings.ADMIN_PASSWORD:
        existing = await get_user_by_email(session, settings.ADMIN_EMAIL)
        if not existing:
            await create_user(
                session=session,
                name=settings.ADMIN_NAME or "System Admin",
                email=settings.ADMIN_EMAIL,
                password=settings.ADMIN_PASSWORD,
                role=UserRole.Admin, 
            )
            logger.success("👤 System Admin Created.")