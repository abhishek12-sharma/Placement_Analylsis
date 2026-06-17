from pathlib import Path
import html
import json
import math
import random
import sqlite3
import sys
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse


ROOT = Path(__file__).resolve().parent
DB_PATH = ROOT / "database" / "placement_analytics.db"
MODEL_PATH = ROOT / "models" / "placement_model.json"


def db_execute(sql, params=()):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.execute(sql, params)
    conn.commit()
    last_id = cursor.lastrowid
    conn.close()
    return last_id


def query_all(sql, params=()):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = [dict(row) for row in conn.execute(sql, params).fetchall()]
    conn.close()
    return rows


def query_one(sql, params=()):
    rows = query_all(sql, params)
    return rows[0] if rows else None


def esc(value):
    return html.escape("" if value is None else str(value))


def load_model():
    if not MODEL_PATH.exists():
        return None
    return json.loads(MODEL_PATH.read_text(encoding="utf-8"))


def log_activity(user, action, details):
    db_execute(
        "INSERT INTO activity_logs (user_id, actor_name, action, details) VALUES (?, ?, ?, ?)",
        (
            user.get("user_id") if user else None,
            user.get("name") if user else "Guest",
            action,
            details,
        ),
    )


def parse_cookie(headers):
    cookie = SimpleCookie(headers.get("Cookie", ""))
    return {key: morsel.value for key, morsel in cookie.items()}


def current_user(headers):
    cookies = parse_cookie(headers)
    user_id = cookies.get("user_id")
    if not user_id:
        return None
    return query_one("SELECT * FROM users WHERE user_id = ?", (user_id,))


def student_skill_set(student_id):
    rows = query_all("SELECT skill_name FROM student_skills WHERE student_id = ?", (student_id,))
    return {row["skill_name"] for row in rows}


def required_skill_set(company_id):
    rows = query_all("SELECT skill_name FROM company_required_skills WHERE company_id = ?", (company_id,))
    return {row["skill_name"] for row in rows}


def company_fit_features(student, company):
    student_skills = student_skill_set(student["student_id"])
    required_skills = required_skill_set(company["company_id"])
    skill_match = len(student_skills & required_skills) / len(required_skills) if required_skills else 0
    branch_match = 1 if company["preferred_branch"] in ("Any", student["branch"]) else 0
    return {
        "cgpa": student["cgpa"],
        "internship_months": student["internship_months"],
        "certifications": student["certifications"],
        "projects": student["projects"],
        "aptitude_score": student["aptitude_score"],
        "communication_score": student["communication_score"],
        "min_cgpa": company["min_cgpa"],
        "cgpa_gap": student["cgpa"] - company["min_cgpa"],
        "aptitude_gap": student["aptitude_score"] - company["aptitude_cutoff"],
        "communication_gap": student["communication_score"] - company["communication_cutoff"],
        "skill_match": skill_match,
        "company_package_lpa": company["package_lpa"],
        "selection_difficulty": company["selection_difficulty"],
        "openings": company["openings"],
        "branch_match": branch_match,
    }


def predict_company_probability(student, company):
    model = load_model()
    features = company_fit_features(student, company)
    if not model:
        base = 45
        base += max(min(features["cgpa_gap"] * 9, 18), -25)
        base += max(min(features["aptitude_gap"] * 0.35, 12), -18)
        base += max(min(features["communication_gap"] * 0.25, 10), -15)
        base += features["skill_match"] * 24
        base += 8 if features["branch_match"] else -10
        base += min(features["openings"] / 4, 12)
        base -= features["selection_difficulty"] * 0.25
        return round(max(2, min(98, base)), 2)

    values = []
    for feature in model["features"]:
        value = features[feature]
        index = model["features"].index(feature)
        values.append((value - model["means"][index]) / model["stds"][index])
    score = sum(value * weight for value, weight in zip(values, model["weights"])) + model["bias"]
    probability = 1 / (1 + math.exp(-score)) * 100

    # Blend ML score with transparent rule-based eligibility so the recommendation is easier to explain.
    rule_score = 35
    rule_score += max(min(features["cgpa_gap"] * 8, 18), -24)
    rule_score += max(min(features["aptitude_gap"] * 0.25, 10), -14)
    rule_score += max(min(features["communication_gap"] * 0.22, 10), -14)
    rule_score += features["skill_match"] * 24
    rule_score += 8 if features["branch_match"] else -12
    rule_score += min(features["openings"] / 5, 10)
    rule_score -= features["selection_difficulty"] * 0.18
    return round(max(1, min(99, probability * 0.55 + rule_score * 0.45)), 2)


def recommend_companies(student_id):
    student = query_one("SELECT * FROM students WHERE student_id = ?", (student_id,))
    if not student:
        return []
    companies = query_all("SELECT * FROM companies ORDER BY package_lpa DESC")
    recommendations = []
    for company in companies:
        features = company_fit_features(student, company)
        probability = predict_company_probability(student, company)
        missing = sorted(required_skill_set(company["company_id"]) - student_skill_set(student_id))
        reasons = []
        if features["cgpa_gap"] < 0:
            reasons.append(f"CGPA short by {abs(features['cgpa_gap']):.1f}")
        if missing:
            reasons.append("Improve " + ", ".join(missing[:2]))
        if features["branch_match"] == 0:
            reasons.append("Branch not preferred")
        if not reasons:
            reasons.append("Strong eligibility and skill fit")
        recommendations.append(
            {
                "company": company,
                "probability": probability,
                "skill_match": round(features["skill_match"] * 100, 1),
                "reasons": "; ".join(reasons),
            }
        )
    recommendations.sort(key=lambda item: item["probability"], reverse=True)
    return recommendations


def dashboard_data():
    kpi = query_one(
        """
        SELECT COUNT(*) AS total_students,
               COALESCE(SUM(CASE WHEN p.status = 'Placed' THEN 1 ELSE 0 END), 0) AS placed_students,
               ROUND(AVG(CASE WHEN p.status = 'Placed' THEN p.package_lpa END), 2) AS average_package,
               ROUND(MAX(p.package_lpa), 2) AS highest_package,
               COUNT(DISTINCT c.company_id) AS active_recruiters
        FROM students s
        LEFT JOIN placements p ON s.student_id = p.student_id
        LEFT JOIN companies c ON p.company_id = c.company_id
        """
    )
    total = kpi["total_students"] or 1
    kpi["placement_rate"] = round((kpi["placed_students"] or 0) / total * 100, 2)
    kpi["average_package"] = kpi["average_package"] or 0
    kpi["highest_package"] = kpi["highest_package"] or 0

    return {
        "kpi": kpi,
        "departments": query_all(
            """
            SELECT s.branch, COUNT(*) AS total_students,
                   COALESCE(SUM(CASE WHEN p.status = 'Placed' THEN 1 ELSE 0 END), 0) AS placed_students,
                   ROUND(COALESCE(SUM(CASE WHEN p.status = 'Placed' THEN 1 ELSE 0 END), 0) * 100.0 / COUNT(*), 2) AS placement_rate
            FROM students s LEFT JOIN placements p ON s.student_id = p.student_id
            GROUP BY s.branch ORDER BY placement_rate DESC
            """
        ),
        "companies": query_all(
            """
            SELECT c.*, COUNT(p.student_id) AS hires, ROUND(AVG(p.package_lpa), 2) AS average_package
            FROM companies c LEFT JOIN placements p ON c.company_id = p.company_id AND p.status = 'Placed'
            GROUP BY c.company_id ORDER BY hires DESC, c.package_lpa DESC LIMIT 8
            """
        ),
        "skills": query_all(
            """
            SELECT skill_name, ROUND(AVG(recruiter_demand), 1) AS demand, ROUND(AVG(proficiency), 1) AS proficiency
            FROM student_skills GROUP BY skill_name ORDER BY demand DESC LIMIT 10
            """
        ),
        "recent": query_all(
            """
            SELECT s.name, s.branch, s.cgpa, p.status, c.company_name, c.role_offered
            FROM students s LEFT JOIN placements p ON s.student_id = p.student_id
            LEFT JOIN companies c ON p.company_id = c.company_id
            ORDER BY s.student_id DESC LIMIT 6
            """
        ),
        "activity": query_all("SELECT * FROM activity_logs ORDER BY log_id DESC LIMIT 8"),
        "model": load_model(),
    }


def layout(title, body, user=None):
    role = user["role"] if user else "guest"
    auth_link = "<a href='/logout'>Logout</a>" if user else "<a href='/login'>Login / Signup</a>"
    admin_link = "<a href='/admin'>Admin</a>" if role == "admin" else ""
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{esc(title)}</title>
  <style>
    :root {{ --bg:#f4f7fb; --surface:#fff; --soft:#eef4f7; --text:#162033; --muted:#6a7485; --line:#dce3ec; --primary:#116d6e; --accent:#d97904; --success:#268a58; --danger:#b94735; }}
    * {{ box-sizing:border-box; }}
    body {{ margin:0; background:var(--bg); color:var(--text); font-family:Inter,Arial,sans-serif; }}
    a {{ color:inherit; }}
    .shell {{ display:grid; grid-template-columns:280px minmax(0,1fr); min-height:100vh; }}
    aside {{ position:sticky; top:0; height:100vh; padding:28px; background:#162033; color:#fff; display:flex; flex-direction:column; gap:24px; }}
    .brand {{ display:flex; gap:12px; align-items:center; }}
    .brand-mark {{ width:48px; height:48px; display:grid; place-items:center; border-radius:8px; background:var(--accent); font-weight:800; }}
    h1,h2,h3,p {{ margin:0; }}
    .brand h1 {{ font-size:18px; }}
    .brand p {{ color:#b8c3d3; font-size:13px; margin-top:3px; }}
    nav {{ display:grid; gap:8px; }}
    nav a {{ padding:12px 14px; border-radius:8px; text-decoration:none; color:#d8e0ea; }}
    nav a:hover {{ background:rgba(255,255,255,.12); color:#fff; }}
    main {{ padding:28px; min-width:0; }}
    .topbar {{ display:flex; justify-content:space-between; align-items:flex-start; gap:16px; margin-bottom:22px; }}
    .eyebrow {{ color:var(--primary); font-size:12px; font-weight:800; text-transform:uppercase; margin-bottom:6px; }}
    .grid {{ display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:16px; margin-bottom:22px; }}
    .two {{ display:grid; grid-template-columns:minmax(0,1.25fr) minmax(330px,.75fr); gap:18px; margin-bottom:22px; }}
    .three {{ display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:14px; }}
    .card,.panel {{ background:var(--surface); border:1px solid var(--line); border-radius:8px; padding:20px; box-shadow:0 8px 28px rgba(22,32,51,.05); }}
    .card span {{ color:var(--muted); font-weight:700; }}
    .card strong {{ display:block; margin:8px 0 4px; font-size:30px; }}
    .panel-head {{ display:flex; justify-content:space-between; align-items:flex-start; gap:12px; margin-bottom:18px; }}
    .hero {{ background:linear-gradient(135deg,rgba(17,109,110,.1),rgba(217,121,4,.08)),#fff; border:1px solid var(--line); border-radius:8px; padding:28px; margin-bottom:22px; }}
    .hero h2 {{ font-size:32px; max-width:820px; }}
    .muted {{ color:var(--muted); line-height:1.6; }}
    .progress-list {{ display:grid; gap:16px; }}
    .progress-row div:first-child {{ display:flex; justify-content:space-between; margin-bottom:7px; }}
    .track {{ height:10px; border-radius:999px; background:var(--soft); overflow:hidden; }}
    .track span {{ display:block; height:100%; background:linear-gradient(90deg,var(--primary),var(--accent)); }}
    table {{ width:100%; border-collapse:collapse; min-width:720px; }}
    th,td {{ padding:13px 10px; border-bottom:1px solid var(--line); text-align:left; white-space:nowrap; }}
    th {{ color:var(--muted); font-size:12px; text-transform:uppercase; }}
    .table-wrap {{ overflow-x:auto; }}
    .pill {{ display:inline-flex; border:1px solid #cbd9df; border-radius:999px; padding:9px 12px; margin:5px; background:#f8fbfd; font-weight:700; color:#244456; }}
    form {{ display:grid; gap:12px; }}
    .form-grid {{ display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:12px; }}
    label {{ display:grid; gap:6px; color:var(--muted); font-size:13px; font-weight:700; }}
    input,select {{ width:100%; border:1px solid var(--line); border-radius:8px; padding:11px; font:inherit; color:var(--text); background:#fff; }}
    button,.button {{ border:1px solid var(--primary); background:var(--primary); color:#fff; border-radius:8px; min-height:42px; padding:0 16px; font-weight:800; cursor:pointer; text-decoration:none; display:inline-flex; align-items:center; justify-content:center; }}
    .ghost {{ border-color:var(--line); background:#fff; color:var(--text); }}
    .notice {{ padding:12px 14px; border-radius:8px; background:#e5f4ed; color:var(--success); font-weight:800; }}
    .danger {{ background:#fff0ed; color:var(--danger); }}
    .result {{ background:var(--soft); border-radius:8px; padding:16px; }}
    .result strong {{ font-size:34px; color:var(--primary); }}
    .mobile-card {{ max-width:440px; margin:40px auto; }}
    @media (max-width:1000px) {{ .shell,.two {{ grid-template-columns:1fr; }} aside {{ position:static; height:auto; }} .grid,.three {{ grid-template-columns:repeat(2,minmax(0,1fr)); }} }}
    @media (max-width:640px) {{ main,aside {{ padding:18px; }} .grid,.three,.form-grid {{ grid-template-columns:1fr; }} .hero h2 {{ font-size:24px; }} .topbar {{ flex-direction:column; }} }}
  </style>
</head>
<body>
  <div class="shell">
    <aside>
      <div class="brand"><span class="brand-mark">PA</span><div><h1>Placement Analytics</h1><p>Career Insights System</p></div></div>
      <nav>
        <a href="/">Dashboard</a>
        <a href="/predict">Company Prediction</a>
        <a href="/students">Students</a>
        <a href="/companies">Companies</a>
        <a href="/exports">BI Exports</a>
        {admin_link}
        {auth_link}
      </nav>
      <div class="card" style="background:rgba(255,255,255,.08);border-color:rgba(255,255,255,.14);box-shadow:none">
        <span style="color:#b8c3d3">Logged in as</span>
        <strong style="font-size:20px">{esc(user['name']) if user else 'Guest'}</strong>
        <p class="muted" style="color:#c6d0df">Role: {esc(role)}</p>
      </div>
    </aside>
    <main>{body}</main>
  </div>
</body>
</html>"""


def dashboard_page(user):
    data = dashboard_data()
    kpi = data["kpi"]
    model_accuracy = "Not trained"
    if data["model"]:
        model_accuracy = f"{data['model']['metrics']['accuracy'] * 100:.1f}%"
    departments = "".join(
        f"<div class='progress-row'><div><strong>{esc(row['branch'])}</strong><span>{row['placement_rate']}%</span></div><div class='track'><span style='width:{row['placement_rate']}%'></span></div></div>"
        for row in data["departments"]
    )
    skills = "".join(f"<span class='pill'>{esc(row['skill_name'])} {row['demand']}%</span>" for row in data["skills"])
    companies = "".join(
        f"<tr><td>{esc(row['company_name'])}</td><td>{esc(row['role_offered'])}</td><td>{row['openings']}</td><td>{row['package_lpa']} LPA</td><td>{row['selection_difficulty']}/100</td></tr>"
        for row in data["companies"]
    )
    recent = "".join(
        f"<div class='card'><strong style='font-size:18px'>{esc(row['name'])}</strong><p class='muted'>{esc(row['branch'])} | CGPA {row['cgpa']}</p><p>{esc(row['status'] or 'Preparing')} {('at ' + esc(row['company_name'])) if row['company_name'] else ''}</p></div>"
        for row in data["recent"]
    )
    activity = "".join(
        f"<tr><td>{esc(row['created_at'])}</td><td>{esc(row['actor_name'])}</td><td>{esc(row['action'])}</td><td>{esc(row['details'])}</td></tr>"
        for row in data["activity"]
    )
    body = f"""
      <div class="topbar"><div><p class="eyebrow">Advanced MCA Project</p><h2>Placement Overview</h2></div><a class="button" href="/predict">Predict Company Selection</a></div>
      <section class="hero"><p class="eyebrow">Database + Python + BI + ML</p><h2>Predict placement chance, recommend companies, manage data, and track admin activity.</h2><p class="muted" style="margin-top:12px">The system now scores each student against company eligibility, required skills, openings, package level, and selection difficulty.</p></section>
      <section class="grid">
        <article class="card"><span>Total Students</span><strong>{kpi['total_students']}</strong><p class="muted">Student records</p></article>
        <article class="card"><span>Placed Students</span><strong>{kpi['placed_students']}</strong><p class="muted">{kpi['placement_rate']}% placement rate</p></article>
        <article class="card"><span>Average Package</span><strong>{kpi['average_package']} LPA</strong><p class="muted">Highest: {kpi['highest_package']} LPA</p></article>
        <article class="card"><span>ML Fit Accuracy</span><strong>{model_accuracy}</strong><p class="muted">Company-wise model</p></article>
      </section>
      <section class="two">
        <article class="panel"><div class="panel-head"><div><p class="eyebrow">Department Wise</p><h3>Placement Performance</h3></div></div><div class="progress-list">{departments}</div></article>
        <article class="panel"><div class="panel-head"><div><p class="eyebrow">Skill Demand</p><h3>Recruiter Requirements</h3></div></div>{skills}</article>
      </section>
      <section class="two">
        <article class="panel"><div class="panel-head"><div><p class="eyebrow">Company Details</p><h3>Recruiter Criteria</h3></div></div><div class="table-wrap"><table><thead><tr><th>Company</th><th>Role</th><th>Openings</th><th>Package</th><th>Difficulty</th></tr></thead><tbody>{companies}</tbody></table></div></article>
        <article class="panel"><div class="panel-head"><div><p class="eyebrow">Recent Activity</p><h3>System Usage</h3></div></div><div class="table-wrap"><table><tbody>{activity}</tbody></table></div></article>
      </section>
      <section class="panel"><div class="panel-head"><div><p class="eyebrow">Recent Students</p><h3>Placement Records</h3></div></div><div class="three">{recent}</div></section>
    """
    return layout("Placement Analytics Dashboard", body, user)


def login_page(message=""):
    body = f"""
    <section class="panel mobile-card">
      <p class="eyebrow">Mobile OTP Login</p>
      <h2>Login or Signup</h2>
      <p class="muted" style="margin:10px 0 18px">Enter your mobile number. For project demo, the OTP is shown on screen and stored in the database.</p>
      {f"<div class='notice'>{esc(message)}</div>" if message else ""}
      <form method="post" action="/send-otp">
        <label>Name<input name="name" placeholder="Your name"></label>
        <label>Mobile Number<input name="mobile" required maxlength="10" placeholder="9999999999"></label>
        <label>Role<select name="role"><option value="student">Student</option><option value="placement_officer">Placement Officer</option><option value="admin">Admin</option></select></label>
        <button type="submit">Send OTP</button>
      </form>
      <hr style="border:0;border-top:1px solid #dce3ec;margin:22px 0">
      <form method="post" action="/verify-otp">
        <label>Mobile Number<input name="mobile" required maxlength="10"></label>
        <label>OTP<input name="otp" required maxlength="6"></label>
        <button type="submit">Verify OTP</button>
      </form>
    </section>
    """
    return layout("Login", body)


def students_page(user, message=""):
    rows = query_all("SELECT * FROM students ORDER BY student_id DESC LIMIT 40")
    table_rows = "".join(
        f"<tr><td>{row['student_id']}</td><td>{esc(row['name'])}</td><td>{esc(row['branch'])}</td><td>{row['cgpa']}</td><td>{row['internship_months']}</td><td>{row['certifications']}</td><td>{row['projects']}</td></tr>"
        for row in rows
    )
    body = f"""
    <div class="topbar"><div><p class="eyebrow">Data Entry</p><h2>Student Details</h2></div></div>
    {f"<div class='notice'>{esc(message)}</div><br>" if message else ""}
    <section class="two">
      <article class="panel">
        <div class="panel-head"><div><p class="eyebrow">Add Student</p><h3>Academic and Readiness Data</h3></div></div>
        <form method="post" action="/students/add">
          <div class="form-grid">
            <label>Name<input name="name" required></label>
            <label>Branch<select name="branch"><option>MCA</option><option>BCA</option><option>B.Tech CSE</option><option>B.Tech IT</option><option>B.Sc CS</option></select></label>
            <label>CGPA<input type="number" step="0.01" name="cgpa" required></label>
            <label>Internship Months<input type="number" name="internship_months" required></label>
            <label>Certifications<input type="number" name="certifications" required></label>
            <label>Projects<input type="number" name="projects" required></label>
            <label>Aptitude Score<input type="number" name="aptitude_score" required></label>
            <label>Communication Score<input type="number" name="communication_score" required></label>
            <label>Placement Year<input type="number" name="placement_year" value="2026" required></label>
            <label>Skills, comma separated<input name="skills" placeholder="Python, SQL, Power BI"></label>
          </div>
          <button type="submit">Save Student</button>
        </form>
      </article>
      <article class="panel">
        <div class="panel-head"><div><p class="eyebrow">Latest Records</p><h3>Student Table</h3></div></div>
        <div class="table-wrap"><table><thead><tr><th>ID</th><th>Name</th><th>Branch</th><th>CGPA</th><th>Internship</th><th>Cert</th><th>Projects</th></tr></thead><tbody>{table_rows}</tbody></table></div>
      </article>
    </section>
    """
    return layout("Students", body, user)


def companies_page(user, message=""):
    rows = query_all("SELECT * FROM companies ORDER BY company_id DESC")
    table_rows = "".join(
        f"<tr><td>{row['company_id']}</td><td>{esc(row['company_name'])}</td><td>{esc(row['role_offered'])}</td><td>{row['package_lpa']} LPA</td><td>{row['min_cgpa']}</td><td>{row['openings']}</td><td>{row['selection_difficulty']}</td></tr>"
        for row in rows
    )
    body = f"""
    <div class="topbar"><div><p class="eyebrow">Data Entry</p><h2>Company Details</h2></div></div>
    {f"<div class='notice'>{esc(message)}</div><br>" if message else ""}
    <section class="two">
      <article class="panel">
        <div class="panel-head"><div><p class="eyebrow">Add Company</p><h3>Recruiter Criteria</h3></div></div>
        <form method="post" action="/companies/add">
          <div class="form-grid">
            <label>Company Name<input name="company_name" required></label>
            <label>Industry<input name="industry" required></label>
            <label>Role Offered<input name="role_offered" required></label>
            <label>Package LPA<input type="number" step="0.1" name="package_lpa" required></label>
            <label>Drive Month<input name="drive_month" required></label>
            <label>Minimum CGPA<input type="number" step="0.1" name="min_cgpa" required></label>
            <label>Preferred Branch<select name="preferred_branch"><option>Any</option><option>MCA</option><option>BCA</option><option>B.Tech CSE</option><option>B.Tech IT</option><option>B.Sc CS</option></select></label>
            <label>Openings<input type="number" name="openings" required></label>
            <label>Selection Difficulty 1-100<input type="number" name="selection_difficulty" required></label>
            <label>Aptitude Cutoff<input type="number" name="aptitude_cutoff" required></label>
            <label>Communication Cutoff<input type="number" name="communication_cutoff" required></label>
            <label>Required Skills<input name="skills" placeholder="Python, SQL, Communication"></label>
          </div>
          <button type="submit">Save Company</button>
        </form>
      </article>
      <article class="panel">
        <div class="panel-head"><div><p class="eyebrow">Recruiter List</p><h3>Company Table</h3></div></div>
        <div class="table-wrap"><table><thead><tr><th>ID</th><th>Company</th><th>Role</th><th>Package</th><th>Min CGPA</th><th>Openings</th><th>Difficulty</th></tr></thead><tbody>{table_rows}</tbody></table></div>
      </article>
    </section>
    """
    return layout("Companies", body, user)


def predict_page(user, student_id=None, saved=False):
    students = query_all("SELECT student_id, name, branch, cgpa FROM students ORDER BY name")
    selected = student_id or (user.get("linked_student_id") if user and user.get("linked_student_id") else students[0]["student_id"])
    options = "".join(
        f"<option value='{row['student_id']}' {'selected' if row['student_id'] == int(selected) else ''}>{esc(row['name'])} - {esc(row['branch'])} CGPA {row['cgpa']}</option>"
        for row in students
    )
    recs = recommend_companies(int(selected))
    rows = ""
    for index, item in enumerate(recs, start=1):
        company = item["company"]
        rows += f"""
        <tr>
          <td>{index}</td><td>{esc(company['company_name'])}</td><td>{esc(company['role_offered'])}</td>
          <td><strong>{item['probability']}%</strong></td><td>{item['skill_match']}%</td>
          <td>{company['package_lpa']} LPA</td><td>{company['openings']}</td><td>{esc(item['reasons'])}</td>
        </tr>
        """
    body = f"""
    <div class="topbar"><div><p class="eyebrow">Improved ML Prediction</p><h2>Company-wise Selection Probability</h2></div></div>
    {f"<div class='notice'>Recommendations saved as application records.</div><br>" if saved else ""}
    <section class="panel">
      <form method="get" action="/predict">
        <label>Select Student<select name="student_id">{options}</select></label>
        <button type="submit">Predict Best Companies</button>
      </form>
    </section>
    <section class="panel" style="margin-top:18px">
      <div class="panel-head"><div><p class="eyebrow">Apply First Recommendation</p><h3>Ranked Company Fit</h3></div><form method="post" action="/applications/save"><input type="hidden" name="student_id" value="{selected}"><button type="submit">Save Recommendations</button></form></div>
      <div class="table-wrap"><table><thead><tr><th>Rank</th><th>Company</th><th>Role</th><th>Selection Probability</th><th>Skill Match</th><th>Package</th><th>Openings</th><th>Reason</th></tr></thead><tbody>{rows}</tbody></table></div>
    </section>
    """
    return layout("Company Prediction", body, user)


def admin_page(user):
    if not user or user["role"] != "admin":
        return layout("Access Denied", "<section class='panel'><h2>Admin access required</h2></section>", user)
    users = query_all("SELECT * FROM users ORDER BY user_id DESC")
    logs = query_all("SELECT * FROM activity_logs ORDER BY log_id DESC LIMIT 100")
    apps = query_all(
        """
        SELECT a.*, s.name AS student_name, c.company_name
        FROM applications a JOIN students s ON a.student_id = s.student_id
        JOIN companies c ON a.company_id = c.company_id
        ORDER BY a.application_id DESC LIMIT 80
        """
    )
    user_rows = "".join(f"<tr><td>{row['user_id']}</td><td>{esc(row['name'])}</td><td>{esc(row['mobile'])}</td><td>{esc(row['role'])}</td><td>{esc(row['created_at'])}</td></tr>" for row in users)
    log_rows = "".join(f"<tr><td>{esc(row['created_at'])}</td><td>{esc(row['actor_name'])}</td><td>{esc(row['action'])}</td><td>{esc(row['details'])}</td></tr>" for row in logs)
    app_rows = "".join(f"<tr><td>{esc(row['student_name'])}</td><td>{esc(row['company_name'])}</td><td>{row['probability']}%</td><td>{row['recommendation_rank']}</td><td>{esc(row['created_at'])}</td></tr>" for row in apps)
    body = f"""
    <div class="topbar"><div><p class="eyebrow">Admin Dashboard</p><h2>Whole System Activity</h2></div></div>
    <section class="two">
      <article class="panel"><div class="panel-head"><div><p class="eyebrow">Users</p><h3>Login / Signup Records</h3></div></div><div class="table-wrap"><table><thead><tr><th>ID</th><th>Name</th><th>Mobile</th><th>Role</th><th>Created</th></tr></thead><tbody>{user_rows}</tbody></table></div></article>
      <article class="panel"><div class="panel-head"><div><p class="eyebrow">Applications</p><h3>Saved Recommendations</h3></div></div><div class="table-wrap"><table><thead><tr><th>Student</th><th>Company</th><th>Probability</th><th>Rank</th><th>Time</th></tr></thead><tbody>{app_rows}</tbody></table></div></article>
    </section>
    <section class="panel"><div class="panel-head"><div><p class="eyebrow">Activity Log</p><h3>User Actions</h3></div></div><div class="table-wrap"><table><thead><tr><th>Time</th><th>User</th><th>Action</th><th>Details</th></tr></thead><tbody>{log_rows}</tbody></table></div></section>
    """
    return layout("Admin Dashboard", body, user)


def exports_page(user):
    files = sorted((ROOT / "exports").glob("*.csv"))
    rows = "".join(f"<li><a href='/file/exports/{file.name}'>{file.name}</a></li>" for file in files)
    body = f"<section class='panel'><p class='eyebrow'>Business Intelligence</p><h2>Power BI / Tableau Export Files</h2><p class='muted' style='margin:10px 0 18px'>Import these CSV files into Power BI or Tableau.</p><ul>{rows}</ul></section>"
    return layout("BI Exports", body, user)


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        user = current_user(self.headers)
        path = urlparse(self.path).path
        params = parse_qs(urlparse(self.path).query)
        if path == "/":
            self.send_html(dashboard_page(user))
        elif path == "/login":
            self.send_html(login_page())
        elif path == "/logout":
            log_activity(user, "logout", "User logged out")
            self.send_response(302)
            self.send_header("Location", "/login")
            self.send_header("Set-Cookie", "user_id=; Path=/; Max-Age=0")
            self.end_headers()
        elif path == "/students":
            self.send_html(students_page(user))
        elif path == "/companies":
            self.send_html(companies_page(user))
        elif path == "/predict":
            self.send_html(predict_page(user, params.get("student_id", [None])[0]))
        elif path == "/admin":
            self.send_html(admin_page(user))
        elif path == "/exports":
            self.send_html(exports_page(user))
        elif path.startswith("/file/exports/"):
            file_path = ROOT / "exports" / Path(path).name
            if file_path.exists():
                self.send_response(200)
                self.send_header("Content-Type", "text/csv")
                self.end_headers()
                self.wfile.write(file_path.read_bytes())
            else:
                self.send_not_found()
        else:
            self.send_not_found()

    def do_POST(self):
        user = current_user(self.headers)
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length).decode("utf-8")
        params = {key: values[0] for key, values in parse_qs(body).items()}
        path = urlparse(self.path).path

        if path == "/send-otp":
            mobile = params["mobile"].strip()
            name = params.get("name", "").strip() or "New User"
            role = params.get("role", "student")
            otp = f"{random.randint(100000, 999999)}"
            existing = query_one("SELECT * FROM users WHERE mobile = ?", (mobile,))
            if not existing:
                db_execute("INSERT INTO users (name, mobile, role) VALUES (?, ?, ?)", (name, mobile, role))
            db_execute("INSERT INTO otp_codes (mobile, otp_code, purpose) VALUES (?, ?, ?)", (mobile, otp, "login"))
            log_activity(existing or {"name": name, "user_id": None}, "otp_requested", f"OTP generated for mobile {mobile}")
            self.send_html(login_page(f"Demo OTP for {mobile}: {otp}"))
        elif path == "/verify-otp":
            mobile = params["mobile"].strip()
            otp = params["otp"].strip()
            code = query_one(
                "SELECT * FROM otp_codes WHERE mobile = ? AND otp_code = ? AND is_used = 0 ORDER BY otp_id DESC LIMIT 1",
                (mobile, otp),
            )
            user_row = query_one("SELECT * FROM users WHERE mobile = ?", (mobile,))
            if code and user_row:
                db_execute("UPDATE otp_codes SET is_used = 1 WHERE otp_id = ?", (code["otp_id"],))
                log_activity(user_row, "login", "OTP verified successfully")
                self.send_response(302)
                self.send_header("Location", "/")
                self.send_header("Set-Cookie", f"user_id={user_row['user_id']}; Path=/; HttpOnly")
                self.end_headers()
            else:
                self.send_html(login_page("Invalid OTP. Please try again."))
        elif path == "/students/add":
            student_id = db_execute(
                """
                INSERT INTO students (name, branch, cgpa, internship_months, certifications, projects, aptitude_score, communication_score, placement_year)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    params["name"],
                    params["branch"],
                    float(params["cgpa"]),
                    int(params["internship_months"]),
                    int(params["certifications"]),
                    int(params["projects"]),
                    int(params["aptitude_score"]),
                    int(params["communication_score"]),
                    int(params["placement_year"]),
                ),
            )
            db_execute("INSERT INTO placements (student_id, placement_year, status, joining_status) VALUES (?, ?, 'Not Placed', 'Preparing')", (student_id, int(params["placement_year"])))
            for skill in [item.strip() for item in params.get("skills", "").split(",") if item.strip()]:
                db_execute("INSERT INTO student_skills (student_id, skill_name, proficiency, recruiter_demand) VALUES (?, ?, 70, 70)", (student_id, skill))
            log_activity(user, "student_added", f"Added student {params['name']}")
            self.redirect("/students")
        elif path == "/companies/add":
            company_id = db_execute(
                """
                INSERT INTO companies (company_name, industry, role_offered, package_lpa, drive_month, min_cgpa, preferred_branch, openings, selection_difficulty, aptitude_cutoff, communication_cutoff)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    params["company_name"],
                    params["industry"],
                    params["role_offered"],
                    float(params["package_lpa"]),
                    params["drive_month"],
                    float(params["min_cgpa"]),
                    params["preferred_branch"],
                    int(params["openings"]),
                    int(params["selection_difficulty"]),
                    int(params["aptitude_cutoff"]),
                    int(params["communication_cutoff"]),
                ),
            )
            for skill in [item.strip() for item in params.get("skills", "").split(",") if item.strip()]:
                db_execute("INSERT INTO company_required_skills (company_id, skill_name, importance) VALUES (?, ?, 75)", (company_id, skill))
            log_activity(user, "company_added", f"Added company {params['company_name']}")
            self.redirect("/companies")
        elif path == "/applications/save":
            student_id = int(params["student_id"])
            db_execute("DELETE FROM applications WHERE student_id = ? AND status = 'Recommended'", (student_id,))
            for rank, item in enumerate(recommend_companies(student_id)[:5], start=1):
                db_execute(
                    "INSERT INTO applications (student_id, company_id, probability, recommendation_rank) VALUES (?, ?, ?, ?)",
                    (student_id, item["company"]["company_id"], item["probability"], rank),
                )
            log_activity(user, "recommendations_saved", f"Saved top company recommendations for student {student_id}")
            self.send_html(predict_page(user, student_id, saved=True))
        else:
            self.send_not_found()

    def redirect(self, location):
        self.send_response(302)
        self.send_header("Location", location)
        self.end_headers()

    def send_html(self, content):
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(content.encode("utf-8"))

    def send_not_found(self):
        self.send_response(404)
        self.end_headers()
        self.wfile.write(b"Not found")


def main():
    if not DB_PATH.exists():
        raise SystemExit("Database not found. Run: python3 scripts/generate_sample_data.py && python3 scripts/build_database.py")

    preferred_port = int(sys.argv[1]) if len(sys.argv) > 1 else 5000
    server = None
    selected_port = None
    for port in range(preferred_port, preferred_port + 20):
        try:
            server = HTTPServer(("127.0.0.1", port), Handler)
            selected_port = port
            break
        except OSError as error:
            if error.errno != 48:
                raise

    if server is None or selected_port is None:
        raise SystemExit(f"No free local port found from {preferred_port} to {preferred_port + 19}.")
    print(f"Placement Analytics dashboard running at http://127.0.0.1:{selected_port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
