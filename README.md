# Placement Analytics and Career Insights System

An MCA major project for analyzing college placement data using database management, Python data analysis, business intelligence exports, and machine learning based placement prediction.

## Project Modules

- Student, company, placement, and skill records stored in SQLite.
- Python analytics pipeline using pandas and NumPy.
- Dashboard-ready CSV exports for Power BI and Tableau.
- Placement probability model implemented with NumPy logistic regression.
- Company-wise selection probability using student profile, company criteria, skill match, openings, package, and difficulty.
- OTP-based mobile login/signup demo.
- Student and company data entry screens.
- Admin dashboard with user records, saved recommendations, and activity logs.
- Python web dashboard served from `app.py`.
- SQL schema that can be adapted for MySQL.

## Folder Structure

```text
Placement_Analytics/
  app.py
  database/schema.sql
  database/placement_analytics.db
  data/*.csv
  exports/*.csv
  models/placement_model.json
  reports/model_metrics.txt
  scripts/generate_sample_data.py
  scripts/build_database.py
  scripts/run_analytics.py
  scripts/train_model.py
```

## Run the Project

Create sample data and database:

```bash
python3 scripts/generate_sample_data.py
python3 scripts/build_database.py
```

Run analytics and create BI exports:

```bash
python3 scripts/run_analytics.py
```

Train placement prediction model:

```bash
python3 scripts/train_model.py
```

Start the dashboard:

```bash
python3 app.py
```

Open:

```text
http://127.0.0.1:5000
```

If port `5000` is busy, the app automatically tries the next free port and prints the correct URL. You can also choose a port manually:

```bash
python3 app.py 5010
```

## Login / Signup Demo

Open `/login`, enter a mobile number, name, and role. The project shows a demo OTP on screen. Enter that OTP to login.

Default sample users:

- Admin: `9999999999`
- Student: `8888888888`
- Placement Officer: `7777777777`

New users can also sign up through the OTP form.

## Improved Machine Learning Prediction

The `/predict` page recommends which company a student should apply to first.

The prediction considers:

- Student CGPA
- Internship months
- Certifications
- Projects
- Aptitude score
- Communication score
- Company minimum CGPA
- Company aptitude and communication cutoffs
- Required skill match
- Preferred branch
- Package level
- Number of openings
- Selection difficulty

The system shows:

- Ranked companies
- Probability of selection in each company
- Skill match percentage
- Reason for the recommendation
- Option to save the top recommendations as application records

## Admin Dashboard

Open `/admin` after logging in as an admin.

The admin can see:

- All users who signed up or logged in
- Saved company recommendations
- Student/company data activity
- OTP login activity
- Timestamped activity logs

## Power BI and Tableau

Use the files inside `exports/`:

- `exports/kpi_summary.csv`
- `exports/department_summary.csv`
- `exports/yearly_trend.csv`
- `exports/company_summary.csv`
- `exports/skill_demand.csv`
- `exports/package_distribution.csv`
- `exports/student_readiness.csv`

Recommended dashboards:

- Placement Overview: placement rate, placed students, average package, highest package.
- Department Analysis: placement percentage by department.
- Company Analytics: top recruiters, hiring count, average package.
- Package Analytics: salary distribution and package band comparison.
- Skill Analytics: most demanded skills and student skill gap.
- Prediction View: student placement probability and readiness category.

## Technology Stack

- Frontend: HTML5, CSS3
- Backend: Python standard library HTTP server
- Database: SQLite, schema portable to MySQL
- Analytics: pandas, NumPy
- Visualization: Power BI or Tableau using exported CSV files
- Machine Learning: NumPy logistic regression
