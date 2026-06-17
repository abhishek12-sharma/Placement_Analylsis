from pathlib import Path
import sqlite3

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "database" / "placement_analytics.db"
EXPORT_DIR = ROOT / "exports"
EXPORT_DIR.mkdir(exist_ok=True)


def read_sql(conn: sqlite3.Connection, query: str) -> pd.DataFrame:
    return pd.read_sql_query(query, conn)


def main() -> None:
    conn = sqlite3.connect(DB_PATH)

    students = read_sql(conn, "SELECT * FROM students")
    placements = read_sql(conn, "SELECT * FROM placements")
    companies = read_sql(conn, "SELECT * FROM companies")
    skills = read_sql(conn, "SELECT * FROM student_skills")

    joined = students.merge(placements, on=["student_id", "placement_year"], how="left")
    placed = joined[joined["status"] == "Placed"]

    kpi_summary = pd.DataFrame(
        [
            {
                "total_students": len(students),
                "placed_students": len(placed),
                "placement_rate": round(len(placed) / len(students) * 100, 2),
                "average_package_lpa": round(placed["package_lpa"].mean(), 2),
                "highest_package_lpa": round(placed["package_lpa"].max(), 2),
                "active_recruiters": companies["company_id"].nunique(),
            }
        ]
    )

    department_summary = (
        joined.groupby("branch")
        .agg(
            total_students=("student_id", "count"),
            placed_students=("status", lambda values: (values == "Placed").sum()),
            average_cgpa=("cgpa", "mean"),
            average_package_lpa=("package_lpa", "mean"),
        )
        .reset_index()
    )
    department_summary["placement_rate"] = (
        department_summary["placed_students"] / department_summary["total_students"] * 100
    ).round(2)
    department_summary["average_cgpa"] = department_summary["average_cgpa"].round(2)
    department_summary["average_package_lpa"] = department_summary["average_package_lpa"].round(2)

    yearly_trend = (
        joined.groupby("placement_year")
        .agg(
            total_students=("student_id", "count"),
            placed_students=("status", lambda values: (values == "Placed").sum()),
            average_package_lpa=("package_lpa", "mean"),
        )
        .reset_index()
    )
    yearly_trend["placement_rate"] = (
        yearly_trend["placed_students"] / yearly_trend["total_students"] * 100
    ).round(2)
    yearly_trend["average_package_lpa"] = yearly_trend["average_package_lpa"].round(2)

    company_summary = (
        placements[placements["status"] == "Placed"]
        .merge(companies, on="company_id", how="left", suffixes=("_actual", "_offered"))
        .groupby(["company_name", "industry", "role_offered"])
        .agg(
            hires=("student_id", "count"),
            average_package_lpa=("package_lpa_actual", "mean"),
            highest_package_lpa=("package_lpa_actual", "max"),
        )
        .reset_index()
        .sort_values(["hires", "average_package_lpa"], ascending=False)
    )
    company_summary["average_package_lpa"] = company_summary["average_package_lpa"].round(2)
    company_summary["highest_package_lpa"] = company_summary["highest_package_lpa"].round(2)

    skill_demand = (
        skills.groupby("skill_name")
        .agg(
            students_with_skill=("student_id", "nunique"),
            average_proficiency=("proficiency", "mean"),
            recruiter_demand=("recruiter_demand", "mean"),
        )
        .reset_index()
        .sort_values("recruiter_demand", ascending=False)
    )
    skill_demand["average_proficiency"] = skill_demand["average_proficiency"].round(2)
    skill_demand["recruiter_demand"] = skill_demand["recruiter_demand"].round(2)
    skill_demand["skill_gap"] = (
        skill_demand["recruiter_demand"] - skill_demand["average_proficiency"]
    ).round(2)

    package_distribution = placed.copy()
    package_distribution["package_band"] = pd.cut(
        package_distribution["package_lpa"],
        bins=[0, 5, 8, 12, 20, 100],
        labels=["Below 5 LPA", "5-8 LPA", "8-12 LPA", "12-20 LPA", "20+ LPA"],
    )
    package_distribution = (
        package_distribution.groupby("package_band", observed=False)
        .agg(students=("student_id", "count"), average_package_lpa=("package_lpa", "mean"))
        .reset_index()
    )
    package_distribution["average_package_lpa"] = package_distribution["average_package_lpa"].round(2)

    student_readiness = joined[
        [
            "student_id",
            "name",
            "branch",
            "cgpa",
            "internship_months",
            "certifications",
            "projects",
            "aptitude_score",
            "communication_score",
            "status",
            "package_lpa",
        ]
    ].copy()
    student_readiness["readiness_score"] = (
        student_readiness["cgpa"] * 7
        + student_readiness["internship_months"] * 5
        + student_readiness["certifications"] * 4
        + student_readiness["projects"] * 4
        + student_readiness["aptitude_score"] * 0.18
        + student_readiness["communication_score"] * 0.16
    ).round(2)
    student_readiness["readiness_category"] = pd.cut(
        student_readiness["readiness_score"],
        bins=[0, 90, 110, 200],
        labels=["Needs Training", "Placement Ready", "High Potential"],
    )

    outputs = {
        "kpi_summary.csv": kpi_summary,
        "department_summary.csv": department_summary,
        "yearly_trend.csv": yearly_trend,
        "company_summary.csv": company_summary,
        "skill_demand.csv": skill_demand,
        "package_distribution.csv": package_distribution,
        "student_readiness.csv": student_readiness,
    }

    for file_name, frame in outputs.items():
        frame.to_csv(EXPORT_DIR / file_name, index=False)

    conn.close()
    print("Analytics exports created in exports/")


if __name__ == "__main__":
    main()
