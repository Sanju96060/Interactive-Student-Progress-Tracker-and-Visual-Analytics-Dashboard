from flask import Flask, render_template, request, redirect, url_for, flash, session, send_from_directory
import random
import sqlite3
import pandas as pd
import os
from werkzeug.utils import secure_filename
import urllib.parse
from datetime import datetime

app = Flask(__name__)
app.secret_key = "tracker_secret_key"

# ---------------- DATA/UPLOAD CONFIG ----------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "eduboard.db")
UPLOAD_FOLDER = os.path.join(BASE_DIR, "uploads")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
ALLOWED_EXTENSIONS = {"xls", "xlsx", "csv"}

def ensure_final_total_column(df):
    """Ensure dataframe has final_total100 column, handle transition from final_total150"""
    if 'final_total150' in df.columns and 'final_total100' not in df.columns:
        df = df.rename(columns={'final_total150': 'final_total100'})
    return df

# ---------------- DB INIT ----------------
def get_db_path(sem_number: int) -> str:
    return os.path.join(BASE_DIR, f"eduboard_sem{sem_number}.db")

def init_db():
    for sem in (1, 2, 3, 4):
        conn = sqlite3.connect(get_db_path(sem))
        c = conn.cursor()
        # Create table if it doesn't exist
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS students(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                usn TEXT,
                name TEXT,
                subject TEXT,
                cie1 REAL,
                cie2 REAL,
                cie_total50 REAL,
                assignment1marks REAL,
                assignment2marks REAL,
                ass_total50 REAL,
                see REAL,
                see_total50 REAL,
                final_total150 REAL,
                final_total100 REAL,
                grade TEXT
            )
            """
        )
        # Add final_total100 column if it doesn't exist
        c.execute("PRAGMA table_info(students)")
        columns = [column[1] for column in c.fetchall()]
        if 'final_total100' not in columns:
            c.execute("ALTER TABLE students ADD COLUMN final_total100 REAL")
        conn.commit()
        conn.close()

init_db()

# ---------------- UTIL ----------------
def compute_grade(final_total):
    try:
        percent = float(final_total)
    except Exception:
        percent = 0.0
    if percent >= 90:
        return "O"
    if percent >= 75:
        return "A"
    if percent >= 55:
        return "B"
    if percent >= 35:
        return "C"
    return "F"

def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS



# ---------------- HOME PAGE ----------------
@app.route('/')
def index():
    return render_template('index.html')


# ---------------- STUDENT LOGIN ----------------
@app.route('/student_login', methods=['GET', 'POST'])
def student_login():
    if request.method == 'POST':
        usn = request.form.get('usn', '').strip().upper()
        semester = request.form.get('semester', '').strip()
        
        if not usn or not semester:
            flash('USN and Semester are required', 'danger')
            return redirect(url_for('student_login'))

        try:
            sem = int(semester)
            if sem not in [1, 2, 3, 4]:
                flash('Invalid semester selected', 'danger')
                return redirect(url_for('student_login'))

            conn = sqlite3.connect(get_db_path(sem))
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM students 
                WHERE UPPER(usn) = ? 
                LIMIT 1
            """, (usn,))
            student_data = cursor.fetchone()
            conn.close()
            
            if student_data:
                session['logged_in'] = True
                session['usn'] = usn
                session['sem'] = sem
                return redirect(url_for('student_biodata', sem=sem, usn=usn))
            else:
                flash('No records found for this USN in the selected semester', 'danger')
                
        except Exception as e:
            flash(f"Error: {str(e)}", "danger")

    return render_template('student_login.html')




# ---------------- STUDENT DASHBOARD ----------------
@app.route('/student/dashboard')
def student_dashboard():
    if 'logged_in' not in session or 'usn' not in session or 'sem' not in session:
        flash('Please log in to access the dashboard', 'warning')
        return redirect(url_for('student_login'))
    
    usn = session['usn']
    sem = session['sem']
    
    try:
        conn = sqlite3.connect(get_db_path(sem))
        df = pd.read_sql_query("""
            SELECT * FROM students 
            WHERE UPPER(usn) = ? 
            ORDER BY subject ASC
        """, conn, params=(usn,))
        conn.close()
        
        if df.empty:
            flash('No records found for this student', 'warning')
            return redirect(url_for('student_login'))
            
        # Get student name from the first record
        student_name = df.iloc[0]['name']
        
        return render_template('student_dashboard.html',
                             name=student_name,
                             usn=usn,
                             sem=sem,
                             subjects=df.to_dict('records'))
                             
    except Exception as e:
        flash(f'Error loading student data: {str(e)}', 'danger')
        return redirect(url_for('student_login'))

# ---------------- LOGOUT ----------------
@app.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out successfully.', 'success')
    return redirect(url_for('index'))

# ---------------- FACULTY LOGIN ----------------
# @app.route('/faculty_login', methods=['GET', 'POST'])
# def faculty_login():
#     if request.method == 'POST':
#         faculty_id = request.form.get('faculty_id')
#         password = request.form.get('password')
#         if faculty_id == "faculty001" and password == "faculty123":
#             session['faculty_logged_in'] = True
#             flash("Faculty Login Successful", "success")
#             return redirect(url_for('faculty_dashboard'))
#         else:
#             flash("Invalid Faculty Credentials", "danger")
#     return render_template('faculty_login.html')


# ---------------- ADMIN LOGIN ----------------
@app.route('/admin_login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        admin_id = request.form['admin_id']
        password = request.form['password']
        if admin_id == "admin@eduboard" and password == "admin123":
            flash("Admin Login Successful", "success")
            return redirect(url_for('admin_dashboard'))
        else:
            flash("Invalid Admin Credentials", "danger")
    return render_template('admin_login.html')


# ---------------- SEMESTER 1 DASHBOARD ----------------
@app.route('/semester1_dashboard')
def semester1_dashboard():
    conn = sqlite3.connect(get_db_path(1))
    df = pd.read_sql_query("SELECT * FROM students ORDER BY id ASC", conn)
    conn.close()
    
    # Handle column name transition
    df = ensure_final_total_column(df)

    if df.empty:
        data_records = []
        top10 = []
        bottom10 = []
        subjects = []
    else:
        data_records = df.to_dict(orient="records")
        
        # Calculate total marks per student across all subjects
        student_totals = df.groupby(['usn', 'name']).agg({
            'final_total100': 'sum',
            'grade': lambda x: list(x)  # Keep all grades for reference
        }).reset_index()
        student_totals = student_totals.sort_values(by="final_total100", ascending=False)
        
        # Convert totals to percentage (divide by actual number of subjects * 100)
        student_totals['subject_count'] = df.groupby(['usn', 'name'])['subject'].nunique().values
        student_totals['final_percentage'] = (student_totals['final_total100'] / (student_totals['subject_count'] * 100) * 100).round(2)
        
        # Determine overall grade based on percentage
        def get_overall_grade(percentage):
            if percentage >= 90: return 'S'
            elif percentage >= 80: return 'A'
            elif percentage >= 70: return 'B'
            elif percentage >= 60: return 'C'
            elif percentage >= 50: return 'D'
            elif percentage >= 40: return 'E'
            else: return 'F'
        
        student_totals['overall_grade'] = student_totals['final_percentage'].apply(get_overall_grade)
        
        top10 = student_totals.head(10).to_dict(orient="records")
        bottom10 = student_totals.tail(10).to_dict(orient="records")
        
        try:
            subjects = sorted([s for s in df['subject'].dropna().unique().tolist() if str(s).strip()])
        except Exception:
            subjects = []

    return render_template('semester1_dashboard.html', data=data_records, top10=top10, bottom10=bottom10, subjects=subjects)

# ---------------- SEMESTER 2 DASHBOARD ----------------
@app.route('/semester2_dashboard')
def semester2_dashboard():
    conn = sqlite3.connect(get_db_path(2))
    df = pd.read_sql_query("SELECT * FROM students ORDER BY id ASC", conn)
    conn.close()
    
    # Handle column name transition
    df = ensure_final_total_column(df)

    if df.empty:
        data_records = []
        top10 = []
        bottom10 = []
        subjects = []
    else:
        data_records = df.to_dict(orient="records")
        
        # Calculate total marks per student across all subjects
        student_totals = df.groupby(['usn', 'name']).agg({
            'final_total100': 'sum',
            'grade': lambda x: list(x)  # Keep all grades for reference
        }).reset_index()
        student_totals = student_totals.sort_values(by="final_total100", ascending=False)
        
        # Convert totals to percentage (divide by actual number of subjects * 100)
        student_totals['subject_count'] = df.groupby(['usn', 'name'])['subject'].nunique().values
        student_totals['final_percentage'] = (student_totals['final_total100'] / (student_totals['subject_count'] * 100) * 100).round(2)
        
        # Determine overall grade based on percentage
        def get_overall_grade(percentage):
            if percentage >= 90: return 'S'
            elif percentage >= 80: return 'A'
            elif percentage >= 70: return 'B'
            elif percentage >= 60: return 'C'
            elif percentage >= 50: return 'D'
            elif percentage >= 40: return 'E'
            else: return 'F'
        
        student_totals['overall_grade'] = student_totals['final_percentage'].apply(get_overall_grade)
        
        top10 = student_totals.head(10).to_dict(orient="records")
        bottom10 = student_totals.tail(10).to_dict(orient="records")
        
        try:
            subjects = sorted([s for s in df['subject'].dropna().unique().tolist() if str(s).strip()])
        except Exception:
            subjects = []

    return render_template('semester2_dashboard.html', data=data_records, top10=top10, bottom10=bottom10, subjects=subjects)

# ---------------- SEMESTER 3 DASHBOARD ----------------
@app.route('/semester3_dashboard')
def semester3_dashboard():
    conn = sqlite3.connect(get_db_path(3))
    df = pd.read_sql_query("SELECT * FROM students ORDER BY id ASC", conn)
    conn.close()
    
    # Handle column name transition
    df = ensure_final_total_column(df)

    if df.empty:
        data_records = []
        top10 = []
        bottom10 = []
        subjects = []
    else:
        data_records = df.to_dict(orient="records")
        
        # Calculate total marks per student across all subjects
        student_totals = df.groupby(['usn', 'name']).agg({
            'final_total100': 'sum',
            'grade': lambda x: list(x)  # Keep all grades for reference
        }).reset_index()
        student_totals = student_totals.sort_values(by="final_total100", ascending=False)
        
        # Convert totals to percentage (divide by actual number of subjects * 100)
        student_totals['subject_count'] = df.groupby(['usn', 'name'])['subject'].nunique().values
        student_totals['final_percentage'] = (student_totals['final_total100'] / (student_totals['subject_count'] * 100) * 100).round(2)
        
        # Determine overall grade based on percentage
        def get_overall_grade(percentage):
            if percentage >= 90: return 'S'
            elif percentage >= 80: return 'A'
            elif percentage >= 70: return 'B'
            elif percentage >= 60: return 'C'
            elif percentage >= 50: return 'D'
            elif percentage >= 40: return 'E'
            else: return 'F'
        
        student_totals['overall_grade'] = student_totals['final_percentage'].apply(get_overall_grade)
        
        top10 = student_totals.head(10).to_dict(orient="records")
        bottom10 = student_totals.tail(10).to_dict(orient="records")
        try:
            subjects = sorted([s for s in df['subject'].dropna().unique().tolist() if str(s).strip()])
        except Exception:
            subjects = []

    return render_template('semester3_dashboard.html', data=data_records, top10=top10, bottom10=bottom10, subjects=subjects)

# ---------------- SEMESTER 4 DASHBOARD ----------------
@app.route('/semester4_dashboard')
def semester4_dashboard():
    conn = sqlite3.connect(get_db_path(4))
    df = pd.read_sql_query("SELECT * FROM students ORDER BY id ASC", conn)
    conn.close()
    
    # Handle column name transition
    df = ensure_final_total_column(df)

    if df.empty:
        data_records = []
        top10 = []
        bottom10 = []
        subjects = []
    else:
        data_records = df.to_dict(orient="records")
        
        # Calculate total marks per student across all subjects
        student_totals = df.groupby(['usn', 'name']).agg({
            'final_total100': 'sum',
            'grade': lambda x: list(x)  # Keep all grades for reference
        }).reset_index()
        student_totals = student_totals.sort_values(by="final_total100", ascending=False)
        
        # Convert totals to percentage (divide by actual number of subjects * 100)
        student_totals['subject_count'] = df.groupby(['usn', 'name'])['subject'].nunique().values
        student_totals['final_percentage'] = (student_totals['final_total100'] / (student_totals['subject_count'] * 100) * 100).round(2)
        
        # Determine overall grade based on percentage
        def get_overall_grade(percentage):
            if percentage >= 90: return 'S'
            elif percentage >= 80: return 'A'
            elif percentage >= 70: return 'B'
            elif percentage >= 60: return 'C'
            elif percentage >= 50: return 'D'
            elif percentage >= 40: return 'E'
            else: return 'F'
        
        student_totals['overall_grade'] = student_totals['final_percentage'].apply(get_overall_grade)
        
        top10 = student_totals.head(10).to_dict(orient="records")
        bottom10 = student_totals.tail(10).to_dict(orient="records")
        try:
            subjects = sorted([s for s in df['subject'].dropna().unique().tolist() if str(s).strip()])
        except Exception:
            subjects = []

    return render_template('semester4_dashboard.html', data=data_records, top10=top10, bottom10=bottom10, subjects=subjects)

# ---------------- ADD MARKS (Semester-specific) ----------------
@app.route('/add_marks/sem1', methods=['GET', 'POST'])
def add_marks_sem1():
    if request.method == 'POST':
        usn = (request.form.get('usn') or '').strip()
        name = (request.form.get('name') or '').strip()
        subject = (request.form.get('subject') or '').strip()

        try:
            cie1 = float(request.form.get('cie1') or 0)
            cie2 = float(request.form.get('cie2') or 0)
            a1 = float(request.form.get('assignment1marks') or 0)
            a2 = float(request.form.get('assignment2marks') or 0)
            see = float(request.form.get('see') or 0)
        except ValueError:
            flash('Numeric fields required for marks.')
            return redirect(url_for('add_marks_sem1'))

        if any(x < 0 for x in (cie1, cie2, a1, a2, see)) or cie1 > 50 or cie2 > 50 or a1 > 50 or a2 > 50 or see > 100:
            flash('Marks limit exceeded or negative values found! CIE & Assignments max 50, SEE max 100.')
            return redirect(url_for('add_marks_sem1'))

        cie_total50 = ((cie1 + cie2) / 100.0) * 25.0
        ass_total50 = ((a1 + a2) / 100.0) * 25.0
        see_total50 = (see / 100.0) * 50.0
        final_total = cie_total50 + ass_total50 + see_total50
        grade = compute_grade(final_total)

        conn = sqlite3.connect(get_db_path(1))
        c = conn.cursor()
        c.execute("SELECT id FROM students WHERE usn=? AND subject= ?", (usn, subject))
        exist = c.fetchone()

        if not exist:
            c.execute(
                """
                INSERT INTO students (
                    usn, name, subject,
                    cie1, cie2, cie_total50,
                    assignment1marks, assignment2marks, ass_total50,
                    see, see_total50, final_total100, grade
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (usn, name, subject, cie1, cie2, cie_total50, a1, a2, ass_total50, see, see_total50, final_total, grade),
            )
            conn.commit()
            flash('Marks added successfully.')
        else:
            flash('Record already exists for this USN & Subject. No new record inserted.')
        conn.close()

        return redirect(url_for('semester1_dashboard'))

    return render_template('add_marks.html')

@app.route('/delete_student/<int:sem>', methods=['POST'])
def delete_student(sem: int):
    def _dashboard_endpoint_for_sem(s: int) -> str:
        return {1: 'semester1_dashboard', 2: 'semester2_dashboard', 3: 'semester3_dashboard', 4: 'semester4_dashboard'}.get(s, 'semester1_dashboard')

    redirect_endpoint = _dashboard_endpoint_for_sem(sem)
    try:
        rec_id = int(request.form.get('id') or 0)
    except Exception:
        rec_id = 0

    if sem not in (1, 2, 3, 4) or rec_id <= 0:
        flash('Invalid delete request.', 'danger')
        return redirect(url_for(redirect_endpoint))

    try:
        conn = sqlite3.connect(get_db_path(sem))
        c = conn.cursor()
        c.execute('DELETE FROM students WHERE id = ?', (rec_id,))
        deleted = c.rowcount
        conn.commit()
        conn.close()
        if deleted:
            flash('Record deleted successfully.', 'success')
        else:
            flash('Record not found.', 'warning')
    except Exception as e:
        flash(f'Error deleting record: {e}', 'danger')

    return redirect(url_for(redirect_endpoint))

@app.route('/add_marks/sem2', methods=['GET', 'POST'])
def add_marks_sem2():
    if request.method == 'POST':
        usn = (request.form.get('usn') or '').strip()
        name = (request.form.get('name') or '').strip()
        subject = (request.form.get('subject') or '').strip()

        try:
            cie1 = float(request.form.get('cie1') or 0)
            cie2 = float(request.form.get('cie2') or 0)
            a1 = float(request.form.get('assignment1marks') or 0)
            a2 = float(request.form.get('assignment2marks') or 0)
            see = float(request.form.get('see') or 0)
        except ValueError:
            flash('Numeric fields required for marks.')
            return redirect(url_for('add_marks_sem2'))

        if any(x < 0 for x in (cie1, cie2, a1, a2, see)) or cie1 > 50 or cie2 > 50 or a1 > 50 or a2 > 50 or see > 100:
            flash('Marks limit exceeded or negative values found! CIE & Assignments max 50, SEE max 100.')
            return redirect(url_for('add_marks_sem2'))

        cie_total50 = ((cie1 + cie2) / 100.0) * 25.0
        ass_total50 = ((a1 + a2) / 100.0) * 25.0
        see_total50 = (see / 100.0) * 50.0
        final_total = cie_total50 + ass_total50 + see_total50
        grade = compute_grade(final_total)

        conn = sqlite3.connect(get_db_path(2))
        c = conn.cursor()
        c.execute("SELECT id FROM students WHERE usn=? AND subject= ?", (usn, subject))
        exist = c.fetchone()

        if not exist:
            c.execute(
                """
                INSERT INTO students (
                    usn, name, subject,
                    cie1, cie2, cie_total50,
                    assignment1marks, assignment2marks, ass_total50,
                    see, see_total50, final_total100, grade
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (usn, name, subject, cie1, cie2, cie_total50, a1, a2, ass_total50, see, see_total50, final_total, grade),
            )
            conn.commit()
            flash('Marks added successfully.')
        else:
            flash('Record already exists for this USN & Subject. No new record inserted.')
        conn.close()

        return redirect(url_for('semester2_dashboard'))

    return render_template('add_marks.html')

@app.route('/add_marks/sem3', methods=['GET', 'POST'])
def add_marks_sem3():
    if request.method == 'POST':
        usn = (request.form.get('usn') or '').strip()
        name = (request.form.get('name') or '').strip()
        subject = (request.form.get('subject') or '').strip()

        try:
            cie1 = float(request.form.get('cie1') or 0)
            cie2 = float(request.form.get('cie2') or 0)
            a1 = float(request.form.get('assignment1marks') or 0)
            a2 = float(request.form.get('assignment2marks') or 0)
            see = float(request.form.get('see') or 0)
        except ValueError:
            flash('Numeric fields required for marks.')
            return redirect(url_for('add_marks_sem3'))

        if any(x < 0 for x in (cie1, cie2, a1, a2, see)) or cie1 > 50 or cie2 > 50 or a1 > 50 or a2 > 50 or see > 100:
            flash('Marks limit exceeded or negative values found! CIE & Assignments max 50, SEE max 100.')
            return redirect(url_for('add_marks_sem3'))

        cie_total50 = ((cie1 + cie2) / 100.0) * 25.0
        ass_total50 = ((a1 + a2) / 100.0) * 25.0
        see_total50 = (see / 100.0) * 50.0
        final_total = cie_total50 + ass_total50 + see_total50
        grade = compute_grade(final_total)

        conn = sqlite3.connect(get_db_path(3))
        c = conn.cursor()
        c.execute("SELECT id FROM students WHERE usn=? AND subject= ?", (usn, subject))
        exist = c.fetchone()

        if not exist:
            c.execute(
                """
                INSERT INTO students (
                    usn, name, subject,
                    cie1, cie2, cie_total50,
                    assignment1marks, assignment2marks, ass_total50,
                    see, see_total50, final_total100, grade
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (usn, name, subject, cie1, cie2, cie_total50, a1, a2, ass_total50, see, see_total50, final_total, grade),
            )
            conn.commit()
            flash('Marks added successfully.')
        else:
            flash('Record already exists for this USN & Subject. No new record inserted.')
        conn.close()

        return redirect(url_for('semester3_dashboard'))

    return render_template('add_marks.html')

@app.route('/add_marks/sem4', methods=['GET', 'POST'])
def add_marks_sem4():
    if request.method == 'POST':
        usn = (request.form.get('usn') or '').strip()
        name = (request.form.get('name') or '').strip()
        subject = (request.form.get('subject') or '').strip()

        try:
            cie1 = float(request.form.get('cie1') or 0)
            cie2 = float(request.form.get('cie2') or 0)
            a1 = float(request.form.get('assignment1marks') or 0)
            a2 = float(request.form.get('assignment2marks') or 0)
            see = float(request.form.get('see') or 0)
        except ValueError:
            flash('Numeric fields required for marks.')
            return redirect(url_for('add_marks_sem4'))

        if any(x < 0 for x in (cie1, cie2, a1
        , a2, see)) or cie1 > 50 or cie2 > 50 or a1 > 50 or a2 > 50 or see > 100:
            flash('Marks limit exceeded or negative values found! CIE & Assignments max 50, SEE max 100.')
            return redirect(url_for('add_marks_sem4'))

        cie_total50 = ((cie1 + cie2) / 100.0) * 25.0
        ass_total50 = ((a1 + a2) / 100.0) * 25.0
        see_total50 = (see / 100.0) * 50.0
        final_total = cie_total50 + ass_total50 + see_total50
        grade = compute_grade(final_total)

        conn = sqlite3.connect(get_db_path(4))
        c = conn.cursor()
        c.execute("SELECT id FROM students WHERE usn=? AND subject= ?", (usn, subject))
        exist = c.fetchone()

        if not exist:
            c.execute(
                """
                INSERT INTO students (
                    usn, name, subject,
                    cie1, cie2, cie_total50,
                    assignment1marks, assignment2marks, ass_total50,
                    see, see_total50, final_total100, grade
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (usn, name, subject, cie1, cie2, cie_total50, a1, a2, ass_total50, see, see_total50, final_total, grade),
            )
            conn.commit()
            flash('Marks added successfully.')
        else:
            flash('Record already exists for this USN & Subject. No new record inserted.')
        conn.close()

        return redirect(url_for('semester4_dashboard'))

    return render_template('add_marks.html')

def _handle_excel_upload_to_semester_db(filename: str, semester: int):
    filepath = os.path.join(UPLOAD_FOLDER, filename)
    try:
        if filename.lower().endswith('.csv'):
            df = pd.read_csv(filepath)
        else:
            df = pd.read_excel(filepath)
    except Exception as e:
        flash(f'Error reading spreadsheet: {e}')
        return False, 0, 0

    required_cols = {"USN", "Name", "Subject", "CIE1", "CIE2", "Assignment1marks", "Assignment2marks", "SEE"}
    missing = required_cols - set([c.strip() for c in df.columns])
    if missing:
        flash(f"Missing required columns in Excel: {', '.join(missing)}")
        return False, 0, 0

    conn = sqlite3.connect(get_db_path(semester))
    c = conn.cursor()

    skip_count = 0
    inserted_count = 0

    for _, row in df.iterrows():
        try:
            usn = str(row.get('USN', '')).strip()
            name = str(row.get('Name', '')).strip()
            subject = str(row.get('Subject', '')).strip()
            cie1 = float(row.get('CIE1') or 0)
            cie2 = float(row.get('CIE2') or 0)
            a1 = float(row.get('Assignment1marks') or 0)
            a2 = float(row.get('Assignment2marks') or 0)
            see = float(row.get('SEE') or 0)
        except Exception:
            skip_count += 1
            continue

        if any(x < 0 for x in (cie1, cie2, a1, a2, see)) or cie1 > 50 or cie2 > 50 or a1 > 50 or a2 > 50 or see > 100:
            skip_count += 1
            continue

        cie_total50 = ((cie1 + cie2) / 100.0) * 25.0
        ass_total50 = ((a1 + a2) / 100.0) * 25.0
        see_total50 = (see / 100.0) * 50.0
        final_total = cie_total50 + ass_total50 + see_total50
        grade = compute_grade(final_total)

        c.execute("SELECT id FROM students WHERE usn=? AND subject=?", (usn, subject))
        exist = c.fetchone()
        if not exist:
            c.execute(
                """
                INSERT INTO students (
                    usn, name, subject,
                    cie1, cie2, cie_total50,
                    assignment1marks, assignment2marks, ass_total50,
                    see, see_total50, final_total100, grade
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (usn, name, subject, cie1, cie2, cie_total50, a1, a2, ass_total50, see, see_total50, final_total, grade),
            )
            inserted_count += 1
        else:
            pass

    conn.commit()
    conn.close()
    return True, inserted_count, skip_count

# ---------------- UPLOAD EXCEL (Subject-specific) ----------------
def _upload_subject_common(semester: int, subject: str, success_redirect_endpoint):
    file = request.files.get('excel')
    if not file or file.filename == '':
        flash('Please upload a valid Excel file.')
        return redirect(success_redirect_endpoint() if callable(success_redirect_endpoint) else url_for(success_redirect_endpoint))

    if not allowed_file(file.filename):
        flash('Unsupported file type. Upload .xls, .xlsx or .csv only.')
        return redirect(success_redirect_endpoint() if callable(success_redirect_endpoint) else url_for(success_redirect_endpoint))

    # Generate unique filename to avoid permission issues
    original_filename = secure_filename(file.filename)
    name, ext = os.path.splitext(original_filename)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{name}_{timestamp}{ext}"
    filepath = os.path.join(UPLOAD_FOLDER, filename)
    
    try:
        file.save(filepath)
    except PermissionError as e:
        flash(f'Permission denied when saving file. The file might be open in another program.')
        return redirect(success_redirect_endpoint() if callable(success_redirect_endpoint) else url_for(success_redirect_endpoint))

    ok, inserted_count, skip_count = _handle_excel_upload_to_subject_db(filename, semester, subject)
    if not ok:
        return redirect(success_redirect_endpoint() if callable(success_redirect_endpoint) else url_for(success_redirect_endpoint))

    flash(f'Upload complete for subject {subject}. Inserted: {inserted_count}. Skipped/invalid rows: {skip_count}.')
    return redirect(success_redirect_endpoint() if callable(success_redirect_endpoint) else url_for(success_redirect_endpoint))

def _handle_excel_upload_to_subject_db(filename: str, semester: int, subject: str):
    filepath = os.path.join(UPLOAD_FOLDER, filename)
    try:
        if filename.lower().endswith('.csv'):
            df = pd.read_csv(filepath)
        else:
            df = pd.read_excel(filepath)
    except Exception as e:
        flash(f'Error reading file: {e}')
        return False, 0, 0

    # Clean up old files (keep only last 10 files per subject)
    _cleanup_old_files(subject)

    required_columns = ['usn', 'name', 'subject', 'cie1', 'cie2', 'assignment1marks', 'assignment2marks', 'see']
    missing_cols = [col for col in required_columns if col not in df.columns]
    if missing_cols:
        flash(f'Missing columns: {missing_cols}')
        return False, 0, 0

    conn = sqlite3.connect(get_db_path(semester))
    cursor = conn.cursor()
    inserted_count = 0
    skip_count = 0

    for _, row in df.iterrows():
        try:
            # Override subject with the provided subject parameter
            row_data = {
                'usn': str(row['usn']).strip(),
                'name': str(row['name']).strip(),
                'subject': subject,  # Force the subject to match the upload target
                'cie1': float(row['cie1']) if pd.notna(row['cie1']) else None,
                'cie2': float(row['cie2']) if pd.notna(row['cie2']) else None,
                'assignment1marks': float(row['assignment1marks']) if pd.notna(row['assignment1marks']) else None,
                'assignment2marks': float(row['assignment2marks']) if pd.notna(row['assignment2marks']) else None,
                'see': float(row['see']) if pd.notna(row['see']) else None
            }

            # Calculate derived fields
            cie_total50 = ((row_data['cie1'] or 0) + (row_data['cie2'] or 0)) / 2
            ass_total50 = ((row_data['assignment1marks'] or 0) + (row_data['assignment2marks'] or 0)) / 2
            see_total50 = (row_data['see'] or 0) / 2
            final_total100 = cie_total50 + ass_total50 + see_total50
            grade = calculate_grade(final_total100)

            # Check if record already exists
            cursor.execute(
                "SELECT COUNT(*) FROM students WHERE usn = ? AND subject = ?",
                (row_data['usn'], subject)
            )
            if cursor.fetchone()[0] == 0:
                cursor.execute(
                    """INSERT INTO students 
                    (usn, name, subject, cie1, cie2, cie_total50, assignment1marks, assignment2marks, ass_total50, see, see_total50, final_total100, grade)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        row_data['usn'], row_data['name'], row_data['subject'],
                        row_data['cie1'], row_data['cie2'], cie_total50,
                        row_data['assignment1marks'], row_data['assignment2marks'], ass_total50,
                        row_data['see'], see_total50, final_total100, grade
                    )
                )
                inserted_count += 1
            else:
                skip_count += 1
        except Exception as e:
            skip_count += 1
            continue

    conn.commit()
    conn.close()
    return True, inserted_count, skip_count

def _cleanup_old_files(subject_prefix: str, keep_count: int = 10):
    """Clean up old uploaded files, keeping only the most recent ones"""
    try:
        # Get all files that start with the subject prefix
        all_files = []
        for filename in os.listdir(UPLOAD_FOLDER):
            if filename.startswith(subject_prefix) and (filename.endswith('.xlsx') or filename.endswith('.xls') or filename.endswith('.csv')):
                filepath = os.path.join(UPLOAD_FOLDER, filename)
                mtime = os.path.getmtime(filepath)
                all_files.append((mtime, filename, filepath))
        
        # Sort by modification time (newest first)
        all_files.sort(reverse=True)
        
        # Remove old files beyond the keep count
        for i, (mtime, filename, filepath) in enumerate(all_files):
            if i >= keep_count:
                try:
                    os.remove(filepath)
                except PermissionError:
                    pass  # File might be in use, skip it
    except Exception:
        pass  # Ignore cleanup errors

# ---------------- UPLOAD EXCEL (Semester-specific) ----------------
def _upload_common(semester: int, success_redirect_endpoint: str):
    file = request.files.get('excel')
    if not file or file.filename == '':
        flash('Please upload a valid Excel file.')
        return redirect(url_for(success_redirect_endpoint))

    if not allowed_file(file.filename):
        flash('Unsupported file type. Upload .xls, .xlsx or .csv only.')
        return redirect(url_for(success_redirect_endpoint))

    # Generate unique filename to avoid permission issues
    original_filename = secure_filename(file.filename)
    name, ext = os.path.splitext(original_filename)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{name}_{timestamp}{ext}"
    filepath = os.path.join(UPLOAD_FOLDER, filename)
    
    try:
        file.save(filepath)
    except PermissionError as e:
        flash(f'Permission denied when saving file. The file might be open in another program.')
        return redirect(url_for(success_redirect_endpoint))

    ok, inserted_count, skip_count = _handle_excel_upload_to_semester_db(filename, semester)
    if not ok:
        return redirect(url_for(success_redirect_endpoint))

    flash(f'Upload complete. Inserted: {inserted_count}. Skipped/invalid rows: {skip_count}.')
    return redirect(url_for(success_redirect_endpoint))

@app.route('/upload_student_excel/sem1', methods=['POST'])
def upload_student_excel_sem1():
    return _upload_common(1, 'semester1_dashboard')

@app.route('/upload_student_excel/sem2', methods=['POST'])
def upload_student_excel_sem2():
    return _upload_common(2, 'semester2_dashboard')

@app.route('/upload_student_excel/sem3', methods=['POST'])
def upload_student_excel_sem3():
    return _upload_common(3, 'semester3_dashboard')

@app.route('/upload_student_excel/sem4', methods=['POST'])
def upload_student_excel_sem4():
    return _upload_common(4, 'semester4_dashboard')

# ---------------- SUBJECT-WISE UPLOAD ROUTES ----------------
@app.route('/upload_subject_excel/sem1/<path:subject_enc>', methods=['POST'])
def upload_subject_excel_sem1(subject_enc: str):
    subject = urllib.parse.unquote_plus(subject_enc)
    return _upload_subject_common(1, subject, lambda: url_for('subject_dashboard', sem=1, subject_enc=subject_enc))

@app.route('/upload_subject_excel/sem2/<path:subject_enc>', methods=['POST'])
def upload_subject_excel_sem2(subject_enc: str):
    subject = urllib.parse.unquote_plus(subject_enc)
    return _upload_subject_common(2, subject, lambda: url_for('subject_dashboard', sem=2, subject_enc=subject_enc))

@app.route('/upload_subject_excel/sem3/<path:subject_enc>', methods=['POST'])
def upload_subject_excel_sem3(subject_enc: str):
    subject = urllib.parse.unquote_plus(subject_enc)
    return _upload_subject_common(3, subject, lambda: url_for('subject_dashboard', sem=3, subject_enc=subject_enc))

@app.route('/upload_subject_excel/sem4/<path:subject_enc>', methods=['POST'])
def upload_subject_excel_sem4(subject_enc: str):
    subject = urllib.parse.unquote_plus(subject_enc)
    return _upload_subject_common(4, subject, lambda: url_for('subject_dashboard', sem=4, subject_enc=subject_enc))


# # ---------------- FACULTY DASHBOARD ----------------
# @app.route('/faculty_dashboard')
# def faculty_dashboard():
#     return render_template('faculty_dashboard.html')


# ---------------- ADMIN DASHBOARD ----------------
@app.route('/admin_dashboard')
def admin_dashboard():
    return render_template('admin_dashboard.html')


# ---------------- SEMESTER PAGE ----------------
@app.route('/semester/<int:sem_number>')
def semester_page(sem_number):
    if sem_number not in [1, 2, 3, 4]:
        flash("Invalid semester selected.", "danger")
        return redirect(url_for('faculty_dashboard'))
    return render_template('semester.html', sem_number=sem_number)


# ---------------- YEAR 1 TOPPERS (Sem 1 + Sem 2) ----------------
@app.route('/year1_toppers')
def year1_toppers():
    # Load data from both semester DBs
    def load_df(sem):
        try:
            conn = sqlite3.connect(get_db_path(sem))
            df_local = pd.read_sql_query("SELECT usn, name, subject, final_total100, final_total150, grade FROM students", conn)
            # Handle column name transition
            df_local = ensure_final_total_column(df_local)
            conn.close()
            df_local["semester"] = sem
            return df_local
        except Exception:
            return pd.DataFrame(columns=["usn","name","subject","final_total100","grade","semester"])

    df1 = load_df(1)
    df2 = load_df(2)
    df = pd.concat([df1, df2], ignore_index=True)

    # Graceful empty handling
    if df.empty:
        combined = []
        top5_for_pie = []
        line_chart_data = []
    else:
        # Compute per-student aggregate across subjects and semesters
        agg = (
            df.groupby(["usn","name"], as_index=False)["final_total100"]
              .mean()
              .rename(columns={"final_total100":"avg_final"})
        )
        # Sort and take top 10
        agg_sorted = agg.sort_values(by="avg_final", ascending=False)
        
        # Prepare data for table with semester-wise percentages and comparison
        combined = []
        for _, student in agg_sorted.head(10).iterrows():
            usn = student['usn']
            name = student['name']
            overall_avg = student['avg_final']
            
            # Get semester 1 percentage
            sem1_data = df[(df['usn'] == usn) & (df['semester'] == 1)]
            if not sem1_data.empty:
                sem1_avg = sem1_data['final_total100'].mean()
            else:
                sem1_avg = 0
            
            # Get semester 2 percentage
            sem2_data = df[(df['usn'] == usn) & (df['semester'] == 2)]
            if not sem2_data.empty:
                sem2_avg = sem2_data['final_total100'].mean()
            else:
                sem2_avg = 0
            
            # Calculate difference and determine high/low
            difference = sem2_avg - sem1_avg
            if difference > 0:
                comparison = "High"
                diff_display = f"+{difference:.2f}"
            elif difference < 0:
                comparison = "Low"
                diff_display = f"{difference:.2f}"
            else:
                comparison = "Same"
                diff_display = "0.00"
            
            combined.append({
                'usn': usn,
                'name': name,
                'avg_final': overall_avg,
                'sem1_percent': round(sem1_avg, 2),
                'sem2_percent': round(sem2_avg, 2),
                'comparison': comparison,
                'difference': diff_display
            })

        # Prepare top5 for pie chart
        top5 = agg_sorted.head(5)
        top5_for_pie = [
            {"label": f"{row['name']} ({row['usn']})", "value": float(row['avg_final'])}
            for _, row in top5.iterrows()
        ]
        
        # Prepare data for line chart - semester-wise percentages for top 10 students
        sem_percentages = []
        for _, student in agg_sorted.head(10).iterrows():
            usn = student['usn']
            name = student['name']
            
            # Get semester 1 percentage
            sem1_data = df[(df['usn'] == usn) & (df['semester'] == 1)]
            if not sem1_data.empty:
                sem1_avg = sem1_data['final_total100'].mean()
            else:
                sem1_avg = 0
            
            # Get semester 2 percentage
            sem2_data = df[(df['usn'] == usn) & (df['semester'] == 2)]
            if not sem2_data.empty:
                sem2_avg = sem2_data['final_total100'].mean()
            else:
                sem2_avg = 0
            
            # Calculate overall average
            overall_avg = student['avg_final']
            
            sem_percentages.append({
                'name': name,
                'sem1': round(sem1_avg, 2),
                'sem2': round(sem2_avg, 2),
                'average': round(overall_avg, 2)
            })
        
        line_chart_data = sem_percentages

    return render_template(
        'year1_toppers.html',
        toppers=combined,
        line_chart_data=line_chart_data
    )


# ---------------- YEAR 2 TOPPERS (Sem 3 + Sem 4) ----------------
@app.route('/year2_toppers')
def year2_toppers():
    def load_df(sem):
        try:
            conn = sqlite3.connect(get_db_path(sem))
            df_local = pd.read_sql_query("SELECT usn, name, subject, final_total100, final_total150, grade FROM students", conn)
            # Handle column name transition
            df_local = ensure_final_total_column(df_local)
            conn.close()
            df_local["semester"] = sem
            return df_local
        except Exception:
            return pd.DataFrame(columns=["usn","name","subject","final_total100","grade","semester"])

    df3 = load_df(3)
    df4 = load_df(4)
    df = pd.concat([df3, df4], ignore_index=True)

    if df.empty:
        combined = []
        top5_for_pie = []
        line_chart_data = []
    else:
        agg = (
            df.groupby(["usn","name"], as_index=False)["final_total100"]
              .mean()
              .rename(columns={"final_total100":"avg_final"})
        )
        agg_sorted = agg.sort_values(by="avg_final", ascending=False)
        
        # Prepare data for table with semester-wise percentages and comparison
        combined = []
        for _, student in agg_sorted.head(10).iterrows():
            usn = student['usn']
            name = student['name']
            overall_avg = student['avg_final']
            
            # Get semester 3 percentage
            sem3_data = df[(df['usn'] == usn) & (df['semester'] == 3)]
            if not sem3_data.empty:
                sem3_avg = sem3_data['final_total100'].mean()
            else:
                sem3_avg = 0
            
            # Get semester 4 percentage
            sem4_data = df[(df['usn'] == usn) & (df['semester'] == 4)]
            if not sem4_data.empty:
                sem4_avg = sem4_data['final_total100'].mean()
            else:
                sem4_avg = 0
            
            # Calculate difference and determine high/low
            difference = sem4_avg - sem3_avg
            if difference > 0:
                comparison = "High"
                diff_display = f"+{difference:.2f}"
            elif difference < 0:
                comparison = "Low"
                diff_display = f"{difference:.2f}"
            else:
                comparison = "Same"
                diff_display = "0.00"
            
            combined.append({
                'usn': usn,
                'name': name,
                'avg_final': overall_avg,
                'sem3_percent': round(sem3_avg, 2),
                'sem4_percent': round(sem4_avg, 2),
                'comparison': comparison,
                'difference': diff_display
            })

        top5 = agg_sorted.head(5)
        top5_for_pie = [
            {"label": f"{row['name']} ({row['usn']})", "value": float(row['avg_final'])}
            for _, row in top5.iterrows()
        ]
        
        # Prepare data for line chart - semester-wise percentages for top 10 students
        sem_percentages = []
        for _, student in agg_sorted.head(10).iterrows():
            usn = student['usn']
            name = student['name']
            
            # Get semester 3 percentage
            sem3_data = df[(df['usn'] == usn) & (df['semester'] == 3)]
            if not sem3_data.empty:
                sem3_avg = sem3_data['final_total100'].mean()
            else:
                sem3_avg = 0
            
            # Get semester 4 percentage
            sem4_data = df[(df['usn'] == usn) & (df['semester'] == 4)]
            if not sem4_data.empty:
                sem4_avg = sem4_data['final_total100'].mean()
            else:
                sem4_avg = 0
            
            # Calculate overall average
            overall_avg = student['avg_final']
            
            sem_percentages.append({
                'name': name,
                'sem3': round(sem3_avg, 2),
                'sem4': round(sem4_avg, 2),
                'average': round(overall_avg, 2)
            })
        
        line_chart_data = sem_percentages

    return render_template(
        'year2_toppers.html',
        toppers=combined,
        line_chart_data=line_chart_data
    )


# ---------------- COLLEGE TOPPERS (Sem 1 + 2 + 3 + 4) ----------------
@app.route('/college_toppers')
def college_toppers():
    def load_df(sem):
        try:
            conn = sqlite3.connect(get_db_path(sem))
            df_local = pd.read_sql_query("SELECT usn, name, subject, final_total100, final_total150, grade FROM students", conn)
            # Handle column name transition
            df_local = ensure_final_total_column(df_local)
            conn.close()
            df_local["semester"] = sem
            return df_local
        except Exception:
            return pd.DataFrame(columns=["usn","name","subject","final_total100","grade","semester"])

    frames = []
    for s in (1, 2, 3, 4):
        frames.append(load_df(s))
    df = pd.concat(frames, ignore_index=True) if len(frames) else pd.DataFrame()

    if df.empty:
        combined = []
        top5_for_pie = []
        line_chart_data = []
    else:
        agg = (
            df.groupby(["usn","name"], as_index=False)["final_total100"]
              .mean()
              .rename(columns={"final_total100":"avg_final"})
        )
        agg_sorted = agg.sort_values(by="avg_final", ascending=False)
        
        # Prepare data for table with semester-wise percentages and comparison
        combined = []
        for _, student in agg_sorted.head(10).iterrows():
            usn = student['usn']
            name = student['name']
            overall_avg = student['avg_final']
            
            # Get semester 1 percentage
            sem1_data = df[(df['usn'] == usn) & (df['semester'] == 1)]
            if not sem1_data.empty:
                sem1_avg = sem1_data['final_total100'].mean()
            else:
                sem1_avg = 0
            
            # Get semester 2 percentage
            sem2_data = df[(df['usn'] == usn) & (df['semester'] == 2)]
            if not sem2_data.empty:
                sem2_avg = sem2_data['final_total100'].mean()
            else:
                sem2_avg = 0
            
            # Get semester 3 percentage
            sem3_data = df[(df['usn'] == usn) & (df['semester'] == 3)]
            if not sem3_data.empty:
                sem3_avg = sem3_data['final_total100'].mean()
            else:
                sem3_avg = 0
            
            # Get semester 4 percentage
            sem4_data = df[(df['usn'] == usn) & (df['semester'] == 4)]
            if not sem4_data.empty:
                sem4_avg = sem4_data['final_total100'].mean()
            else:
                sem4_avg = 0
            
            # Calculate difference (compare last semester with first)
            difference = sem4_avg - sem1_avg
            if difference > 0:
                comparison = "High"
                diff_display = f"+{difference:.2f}"
            elif difference < 0:
                comparison = "Low"
                diff_display = f"{difference:.2f}"
            else:
                comparison = "Same"
                diff_display = "0.00"
            
            combined.append({
                'usn': usn,
                'name': name,
                'avg_final': overall_avg,
                'sem1_percent': round(sem1_avg, 2),
                'sem2_percent': round(sem2_avg, 2),
                'sem3_percent': round(sem3_avg, 2),
                'sem4_percent': round(sem4_avg, 2),
                'comparison': comparison,
                'difference': diff_display
            })

        top5 = agg_sorted.head(5)
        top5_for_pie = [
            {"label": f"{row['name']} ({row['usn']})", "value": float(row['avg_final'])}
            for _, row in top5.iterrows()
        ]
        
        # Prepare data for line chart - semester-wise percentages for top 10 students
        sem_percentages = []
        for _, student in agg_sorted.head(10).iterrows():
            usn = student['usn']
            name = student['name']
            
            # Get semester 1 percentage
            sem1_data = df[(df['usn'] == usn) & (df['semester'] == 1)]
            if not sem1_data.empty:
                sem1_avg = sem1_data['final_total100'].mean()
            else:
                sem1_avg = 0
            
            # Get semester 2 percentage
            sem2_data = df[(df['usn'] == usn) & (df['semester'] == 2)]
            if not sem2_data.empty:
                sem2_avg = sem2_data['final_total100'].mean()
            else:
                sem2_avg = 0
            
            # Get semester 3 percentage
            sem3_data = df[(df['usn'] == usn) & (df['semester'] == 3)]
            if not sem3_data.empty:
                sem3_avg = sem3_data['final_total100'].mean()
            else:
                sem3_avg = 0
            
            # Get semester 4 percentage
            sem4_data = df[(df['usn'] == usn) & (df['semester'] == 4)]
            if not sem4_data.empty:
                sem4_avg = sem4_data['final_total100'].mean()
            else:
                sem4_avg = 0
            
            # Calculate overall average
            overall_avg = student['avg_final']
            
            sem_percentages.append({
                'name': name,
                'sem1': round(sem1_avg, 2),
                'sem2': round(sem2_avg, 2),
                'sem3': round(sem3_avg, 2),
                'sem4': round(sem4_avg, 2),
                'average': round(overall_avg, 2)
            })
        
        line_chart_data = sem_percentages

    return render_template(
        'college_toppers.html',
        toppers=combined,
        line_chart_data=line_chart_data
    )


# ---------------- SUBJECT VIEW (per semester) ----------------
def _calculate_fail_analysis(df):
    """Calculate fail statistics for students"""
    if df.empty:
        return [], []
    
    # Students who failed (grade F or final_total100 < 60)
    failed_students = df[(df['grade'] == 'F') | (df['final_total100'] < 60)].copy()
    
    # Count fails per student
    fail_counts = failed_students.groupby('usn').agg({
        'name': 'first',
        'subject': 'count'
    }).rename(columns={'subject': 'fail_count'}).reset_index()
    
    # Sort by fail count (descending)
    fail_counts = fail_counts.sort_values('fail_count', ascending=False)
    
    # Prepare data for chart
    chart_data = []
    for _, row in fail_counts.iterrows():
        chart_data.append({
            'usn': row['usn'],
            'name': row['name'],
            'fail_count': row['fail_count']
        })
    
    return chart_data, fail_counts.to_dict('records')

def _calculate_top_students(df):
    """Calculate top 10 students for the subject"""
    if df.empty:
        return [], []
    
    # Students who passed (grade not F and final_total100 >= 60)
    passed_students = df[(df['grade'] != 'F') & (df['final_total100'] >= 60)].copy()
    
    # Sort by final_total100 (descending) and get top 10
    top_students = passed_students.sort_values('final_total100', ascending=False).head(10)
    
    # Prepare data for chart
    chart_data = []
    for _, row in top_students.iterrows():
        chart_data.append({
            'usn': row['usn'],
            'name': row['name'],
            'final_total100': row['final_total100'],
            'grade': row['grade']
        })
    
    return chart_data, top_students.to_dict('records')

@app.route('/semester/<int:sem>/subject/<path:subject_enc>')
def subject_dashboard(sem: int, subject_enc: str):
    if sem not in (1, 2, 3, 4):
        flash('Invalid semester selected.', 'danger')
        return redirect(url_for('faculty_dashboard'))
    subject = urllib.parse.unquote_plus(subject_enc)
    try:
        conn = sqlite3.connect(get_db_path(sem))
        df = pd.read_sql_query("SELECT * FROM students WHERE subject = ? ORDER BY id ASC", conn, params=(subject,))
        conn.close()
        
        # Handle column name transition
        df = ensure_final_total_column(df)
        records = df.to_dict(orient='records') if not df.empty else []
        
        # Calculate fail analysis
        chart_data, fail_stats = _calculate_fail_analysis(df)
        
        # Calculate top students
        top_chart_data, top_stats = _calculate_top_students(df)
    except Exception as e:
        flash(f'Error loading subject view: {e}', 'danger')
        records = []
        chart_data = []
        fail_stats = []
        top_chart_data = []
        top_stats = []
    
    return render_template('subject_dashboard.html', sem=sem, subject=subject, data=records, 
                         chart_data=chart_data, fail_stats=fail_stats, 
                         top_chart_data=top_chart_data, top_stats=top_stats)

# ---------------- STUDENT BIODATA VIEW ----------------
@app.route('/semester/<int:sem>/student/<usn>')
def student_biodata(sem: int, usn: str):
    if sem not in (1, 2, 3, 4):
        flash('Invalid semester selected', 'danger')
        return redirect(url_for('student_login'))
    
    try:
        # Connect to the database
        conn = sqlite3.connect(get_db_path(sem))
        
        # Get student data
        df = pd.read_sql_query(
            """
            SELECT * FROM students 
            WHERE UPPER(usn) = UPPER(?) 
            ORDER BY subject ASC
            """, 
            conn, 
            params=(usn.strip(),)
        )
        
        # Handle column name transition
        df = ensure_final_total_column(df)
        
        if not df.empty:
            # Convert to list of dictionaries
            records = df.to_dict(orient='records')
            # Get student name from first record (should be same for all records)
            name = records[0].get('name', '')
            
            return render_template(
                'student_biodata.html',
                name=name,
                usn=usn.upper(),
                sem=sem,
                data=records
            )
        else:
            flash(f'No records found for USN: {usn} in semester {sem}', 'warning')
            return redirect(url_for('student_login'))
            
    except sqlite3.Error as e:
        flash(f'Database error: {str(e)}', 'danger')
        return redirect(url_for('student_login'))
    except Exception as e:
        flash(f'An unexpected error occurred: {str(e)}', 'danger')
        return redirect(url_for('student_login'))
    finally:
        if 'conn' in locals():
            conn.close()
    return render_template('student_biodata.html', sem=sem, usn=usn, name=name, data=records)
    return redirect(url_for('index'))


@app.route('/favicon.ico')
def favicon():
    return send_from_directory(os.path.join(app.root_path, 'static'), 'favicon.svg', mimetype='image/svg+xml')


if __name__ == "__main__":
    app.run(debug=True)
