from pathlib import Path
import json
import sqlite3

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "database" / "placement_analytics.db"
MODEL_DIR = ROOT / "models"
REPORT_DIR = ROOT / "reports"
MODEL_DIR.mkdir(exist_ok=True)
REPORT_DIR.mkdir(exist_ok=True)


FEATURES = [
    "cgpa",
    "internship_months",
    "certifications",
    "projects",
    "aptitude_score",
    "communication_score",
    "min_cgpa",
    "cgpa_gap",
    "aptitude_gap",
    "communication_gap",
    "skill_match",
    "company_package_lpa",
    "selection_difficulty",
    "openings",
    "branch_match",
]


def sigmoid(values: np.ndarray) -> np.ndarray:
    return 1 / (1 + np.exp(-values))


def main() -> None:
    conn = sqlite3.connect(DB_PATH)
    students = pd.read_sql_query(
        """
        SELECT s.student_id, s.branch, s.cgpa, s.internship_months, s.certifications,
               s.projects, s.aptitude_score, s.communication_score,
               p.company_id AS placed_company_id
        FROM students s
        JOIN placements p ON s.student_id = p.student_id
        """,
        conn,
    )
    companies = pd.read_sql_query("SELECT * FROM companies", conn)
    student_skills = pd.read_sql_query("SELECT student_id, skill_name FROM student_skills", conn)
    requirements = pd.read_sql_query("SELECT company_id, skill_name FROM company_required_skills", conn)
    conn.close()

    student_skill_map = student_skills.groupby("student_id")["skill_name"].apply(set).to_dict()
    requirement_map = requirements.groupby("company_id")["skill_name"].apply(set).to_dict()

    rows = []
    for _, student in students.iterrows():
        student_rows = []
        for _, company in companies.iterrows():
            student_skill_set = student_skill_map.get(student["student_id"], set())
            required_skill_set = requirement_map.get(company["company_id"], set())
            skill_match = (
                len(student_skill_set.intersection(required_skill_set)) / len(required_skill_set)
                if required_skill_set
                else 0
            )
            branch_match = 1 if company["preferred_branch"] in ("Any", student["branch"]) else 0
            student_rows.append(
                {
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
                    "selected": 1 if student["placed_company_id"] == company["company_id"] else 0,
                }
            )
        positive_rows = [row for row in student_rows if row["selected"] == 1]
        negative_rows = [row for row in student_rows if row["selected"] == 0]
        rows.extend(positive_rows)
        rows.extend(pd.DataFrame(negative_rows).sample(n=min(3, len(negative_rows)), random_state=int(student["student_id"])).to_dict("records"))

    frame = pd.DataFrame(rows)

    rng = np.random.default_rng(7)
    shuffled = frame.sample(frac=1, random_state=7).reset_index(drop=True)
    split_index = int(len(shuffled) * 0.8)
    train = shuffled.iloc[:split_index]
    test = shuffled.iloc[split_index:]

    x_train = train[FEATURES].to_numpy(dtype=float)
    y_train = train["selected"].to_numpy(dtype=float)
    x_test = test[FEATURES].to_numpy(dtype=float)
    y_test = test["selected"].to_numpy(dtype=float)

    means = x_train.mean(axis=0)
    stds = x_train.std(axis=0)
    stds[stds == 0] = 1
    x_train = (x_train - means) / stds
    x_test = (x_test - means) / stds

    weights = rng.normal(0, 0.01, size=x_train.shape[1])
    bias = 0.0
    learning_rate = 0.08
    epochs = 3000

    for _ in range(epochs):
        predictions = sigmoid(x_train @ weights + bias)
        error = predictions - y_train
        weights -= learning_rate * (x_train.T @ error / len(x_train))
        bias -= learning_rate * error.mean()

    probabilities = sigmoid(x_test @ weights + bias)
    predicted = (probabilities >= 0.5).astype(int)
    accuracy = float((predicted == y_test).mean())
    precision = float(((predicted == 1) & (y_test == 1)).sum() / max((predicted == 1).sum(), 1))
    recall = float(((predicted == 1) & (y_test == 1)).sum() / max((y_test == 1).sum(), 1))

    model = {
        "model_type": "NumPy Logistic Regression - Student Company Fit",
        "features": FEATURES,
        "means": means.round(6).tolist(),
        "stds": stds.round(6).tolist(),
        "weights": weights.round(6).tolist(),
        "bias": round(float(bias), 6),
        "threshold": 0.5,
        "metrics": {
            "accuracy": round(accuracy, 4),
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "test_records": int(len(test)),
        },
    }

    with open(MODEL_DIR / "placement_model.json", "w", encoding="utf-8") as model_file:
        json.dump(model, model_file, indent=2)

    with open(REPORT_DIR / "model_metrics.txt", "w", encoding="utf-8") as report_file:
        report_file.write("Company-wise Placement Prediction Model Report\n")
        report_file.write("==============================================\n")
        report_file.write(f"Model: {model['model_type']}\n")
        report_file.write(f"Features: {', '.join(FEATURES)}\n")
        report_file.write(f"Accuracy: {model['metrics']['accuracy']}\n")
        report_file.write(f"Precision: {model['metrics']['precision']}\n")
        report_file.write(f"Recall: {model['metrics']['recall']}\n")
        report_file.write(f"Test Records: {model['metrics']['test_records']}\n")

    print("Model trained and saved in models/placement_model.json")


if __name__ == "__main__":
    main()
