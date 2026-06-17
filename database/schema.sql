DROP TABLE IF EXISTS activity_logs;
DROP TABLE IF EXISTS otp_codes;
DROP TABLE IF EXISTS applications;
DROP TABLE IF EXISTS placements;
DROP TABLE IF EXISTS student_skills;
DROP TABLE IF EXISTS company_required_skills;
DROP TABLE IF EXISTS companies;
DROP TABLE IF EXISTS students;
DROP TABLE IF EXISTS users;

CREATE TABLE users (
  user_id INTEGER PRIMARY KEY,
  name TEXT NOT NULL,
  mobile TEXT NOT NULL UNIQUE,
  role TEXT NOT NULL CHECK (role IN ('admin', 'student', 'placement_officer')),
  linked_student_id INTEGER,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (linked_student_id) REFERENCES students(student_id)
);

CREATE TABLE students (
  student_id INTEGER PRIMARY KEY,
  name TEXT NOT NULL,
  branch TEXT NOT NULL,
  cgpa REAL NOT NULL,
  internship_months INTEGER NOT NULL,
  certifications INTEGER NOT NULL,
  projects INTEGER NOT NULL,
  aptitude_score INTEGER NOT NULL,
  communication_score INTEGER NOT NULL,
  placement_year INTEGER NOT NULL
);

CREATE TABLE companies (
  company_id INTEGER PRIMARY KEY,
  company_name TEXT NOT NULL,
  industry TEXT NOT NULL,
  role_offered TEXT NOT NULL,
  package_lpa REAL NOT NULL,
  drive_month TEXT NOT NULL,
  min_cgpa REAL NOT NULL DEFAULT 6.0,
  preferred_branch TEXT NOT NULL DEFAULT 'Any',
  openings INTEGER NOT NULL DEFAULT 10,
  selection_difficulty INTEGER NOT NULL DEFAULT 50,
  aptitude_cutoff INTEGER NOT NULL DEFAULT 60,
  communication_cutoff INTEGER NOT NULL DEFAULT 60
);

CREATE TABLE company_required_skills (
  requirement_id INTEGER PRIMARY KEY,
  company_id INTEGER NOT NULL,
  skill_name TEXT NOT NULL,
  importance INTEGER NOT NULL,
  FOREIGN KEY (company_id) REFERENCES companies(company_id)
);

CREATE TABLE placements (
  placement_id INTEGER PRIMARY KEY,
  student_id INTEGER NOT NULL,
  company_id INTEGER,
  placement_year INTEGER NOT NULL,
  package_lpa REAL,
  status TEXT NOT NULL CHECK (status IN ('Placed', 'Not Placed')),
  joining_status TEXT NOT NULL,
  FOREIGN KEY (student_id) REFERENCES students(student_id),
  FOREIGN KEY (company_id) REFERENCES companies(company_id)
);

CREATE TABLE student_skills (
  skill_id INTEGER PRIMARY KEY,
  student_id INTEGER NOT NULL,
  skill_name TEXT NOT NULL,
  proficiency INTEGER NOT NULL,
  recruiter_demand INTEGER NOT NULL,
  FOREIGN KEY (student_id) REFERENCES students(student_id)
);

CREATE TABLE applications (
  application_id INTEGER PRIMARY KEY,
  student_id INTEGER NOT NULL,
  company_id INTEGER NOT NULL,
  probability REAL NOT NULL,
  recommendation_rank INTEGER NOT NULL,
  status TEXT NOT NULL DEFAULT 'Recommended',
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (student_id) REFERENCES students(student_id),
  FOREIGN KEY (company_id) REFERENCES companies(company_id)
);

CREATE TABLE otp_codes (
  otp_id INTEGER PRIMARY KEY,
  mobile TEXT NOT NULL,
  otp_code TEXT NOT NULL,
  purpose TEXT NOT NULL,
  is_used INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE activity_logs (
  log_id INTEGER PRIMARY KEY,
  user_id INTEGER,
  actor_name TEXT NOT NULL,
  action TEXT NOT NULL,
  details TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (user_id) REFERENCES users(user_id)
);

CREATE INDEX idx_students_branch ON students(branch);
CREATE INDEX idx_placements_year ON placements(placement_year);
CREATE INDEX idx_student_skills_name ON student_skills(skill_name);
CREATE INDEX idx_users_mobile ON users(mobile);
CREATE INDEX idx_activity_created_at ON activity_logs(created_at);
CREATE INDEX idx_applications_student ON applications(student_id);
