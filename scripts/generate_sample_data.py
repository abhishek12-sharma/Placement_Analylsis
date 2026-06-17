from pathlib import Path
import random

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
DATA_DIR.mkdir(exist_ok=True)

random.seed(42)

branches = ["MCA", "BCA", "B.Tech CSE", "B.Tech IT", "B.Sc CS"]
first_names = [
    "Aarav", "Priya", "Rahul", "Sneha", "Karan", "Nisha", "Rohan", "Ananya",
    "Vikas", "Meera", "Aditya", "Pooja", "Sahil", "Kavya", "Mohit", "Isha",
    "Arjun", "Simran", "Dev", "Tanvi", "Yash", "Riya", "Nikhil", "Neha"
]
last_names = [
    "Sharma", "Verma", "Mehta", "Gupta", "Patel", "Singh", "Kumar", "Jain",
    "Reddy", "Nair", "Mishra", "Bansal", "Joshi", "Kapoor", "Malhotra"
]
skills = {
    "Python": 88,
    "SQL": 84,
    "Power BI": 72,
    "Tableau": 65,
    "Java": 61,
    "React": 56,
    "Machine Learning": 59,
    "Excel": 74,
    "Cloud Basics": 52,
    "Communication": 80,
}

companies = [
    (1, "Infosys", "IT Services", "Software Engineer", 6.5, "January", 6.5, "Any", 40, 45, 58, 55),
    (2, "TCS", "Consulting", "System Analyst", 5.8, "February", 6.0, "Any", 55, 40, 55, 55),
    (3, "Accenture", "Technology", "Data Analyst", 7.2, "February", 7.0, "MCA", 28, 58, 65, 62),
    (4, "Wipro", "IT Services", "Cloud Associate", 6.8, "March", 6.4, "Any", 35, 50, 60, 58),
    (5, "Deloitte", "Consulting", "Business Analyst", 8.5, "March", 7.2, "Any", 18, 67, 70, 72),
    (6, "Capgemini", "Technology", "Developer Analyst", 6.2, "April", 6.2, "Any", 38, 44, 55, 56),
    (7, "Cognizant", "IT Services", "Programmer Analyst", 5.9, "April", 6.0, "Any", 45, 42, 54, 54),
    (8, "Amazon", "E-Commerce", "Data Engineer Intern", 14.0, "May", 8.0, "B.Tech CSE", 8, 88, 82, 78),
    (9, "HCLTech", "IT Services", "Software Trainee", 5.4, "May", 6.0, "Any", 32, 38, 52, 52),
    (10, "Tech Mahindra", "Telecom IT", "Associate Engineer", 5.6, "June", 6.0, "Any", 30, 41, 52, 54),
]

company_skill_map = {
    1: ["Java", "SQL", "Communication"],
    2: ["Java", "SQL", "Excel"],
    3: ["Python", "SQL", "Power BI"],
    4: ["Cloud Basics", "Python", "Communication"],
    5: ["Excel", "Power BI", "Communication"],
    6: ["Java", "React", "SQL"],
    7: ["Java", "SQL", "Communication"],
    8: ["Python", "SQL", "Machine Learning"],
    9: ["Java", "SQL", "Cloud Basics"],
    10: ["Java", "Cloud Basics", "Communication"],
}

student_rows = []
placement_rows = []
skill_rows = []
placement_id = 1
skill_id = 1

for student_id in range(1, 181):
    name = f"{random.choice(first_names)} {random.choice(last_names)}"
    branch = random.choice(branches)
    year = random.choice([2022, 2023, 2024, 2025, 2026])
    cgpa = round(random.uniform(6.0, 9.8), 2)
    internship_months = random.choice([0, 1, 2, 3, 4, 6])
    certifications = random.randint(0, 5)
    projects = random.randint(1, 6)
    aptitude_score = random.randint(45, 96)
    communication_score = random.randint(45, 96)

    readiness = (
        (cgpa - 6) * 12
        + internship_months * 5
        + certifications * 4
        + projects * 4
        + aptitude_score * 0.28
        + communication_score * 0.22
        + random.uniform(-16, 12)
    )
    placed = readiness >= 76
    company = random.choice(companies) if placed else None
    package = None
    company_id = None
    joining_status = "Preparing"

    if placed and company:
        company_id = company[0]
        package = round(max(3.5, company[4] + random.uniform(-1.2, 2.6)), 2)
        joining_status = random.choice(["Joined", "Offer Accepted", "Awaiting Joining"])

    student_rows.append(
        {
            "student_id": student_id,
            "name": name,
            "branch": branch,
            "cgpa": cgpa,
            "internship_months": internship_months,
            "certifications": certifications,
            "projects": projects,
            "aptitude_score": aptitude_score,
            "communication_score": communication_score,
            "placement_year": year,
        }
    )

    placement_rows.append(
        {
            "placement_id": placement_id,
            "student_id": student_id,
            "company_id": company_id,
            "placement_year": year,
            "package_lpa": package,
            "status": "Placed" if placed else "Not Placed",
            "joining_status": joining_status,
        }
    )
    placement_id += 1

    selected_skills = random.sample(list(skills.items()), random.randint(3, 6))
    for skill_name, demand in selected_skills:
        skill_rows.append(
            {
                "skill_id": skill_id,
                "student_id": student_id,
                "skill_name": skill_name,
                "proficiency": random.randint(45, 95),
                "recruiter_demand": demand,
            }
        )
        skill_id += 1

pd.DataFrame(student_rows).to_csv(DATA_DIR / "students.csv", index=False)
pd.DataFrame(
    companies,
    columns=[
        "company_id",
        "company_name",
        "industry",
        "role_offered",
        "package_lpa",
        "drive_month",
        "min_cgpa",
        "preferred_branch",
        "openings",
        "selection_difficulty",
        "aptitude_cutoff",
        "communication_cutoff",
    ],
).to_csv(DATA_DIR / "companies.csv", index=False)
pd.DataFrame(placement_rows).to_csv(DATA_DIR / "placements.csv", index=False)
pd.DataFrame(skill_rows).to_csv(DATA_DIR / "student_skills.csv", index=False)

requirement_rows = []
requirement_id = 1
for company_id, required_skills in company_skill_map.items():
    for skill_name in required_skills:
        requirement_rows.append(
            {
                "requirement_id": requirement_id,
                "company_id": company_id,
                "skill_name": skill_name,
                "importance": skills[skill_name],
            }
        )
        requirement_id += 1
pd.DataFrame(requirement_rows).to_csv(DATA_DIR / "company_required_skills.csv", index=False)

pd.DataFrame(
    [
        {"user_id": 1, "name": "Admin User", "mobile": "9999999999", "role": "admin", "linked_student_id": ""},
        {"user_id": 2, "name": "Demo Student", "mobile": "8888888888", "role": "student", "linked_student_id": 1},
        {"user_id": 3, "name": "Placement Officer", "mobile": "7777777777", "role": "placement_officer", "linked_student_id": ""},
    ]
).to_csv(DATA_DIR / "users.csv", index=False)

print("Sample placement data generated in data/")
