import sqlite3
import os

def migrate_database(db_path):
    """Migrate database from final_total150 to final_total100"""
    if not os.path.exists(db_path):
        print(f"Database {db_path} does not exist")
        return
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        # Check if final_total150 column exists
        cursor.execute("PRAGMA table_info(students)")
        columns = [row[1] for row in cursor.fetchall()]
        
        if 'final_total150' in columns and 'final_total100' not in columns:
            # Create a new table with the updated schema
            cursor.execute("""
                CREATE TABLE students_new (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    usn TEXT NOT NULL,
                    name TEXT NOT NULL,
                    subject TEXT NOT NULL,
                    cie1 REAL,
                    cie2 REAL,
                    cie_total50 REAL,
                    assignment1marks REAL,
                    assignment2marks REAL,
                    ass_total50 REAL,
                    see REAL,
                    see_total50 REAL,
                    final_total100 REAL,
                    grade TEXT
                )
            """)
            
            # Copy data from old table to new table
            cursor.execute("""
                INSERT INTO students_new (
                    id, usn, name, subject, cie1, cie2, cie_total50,
                    assignment1marks, assignment2marks, ass_total50,
                    see, see_total50, final_total100, grade
                )
                SELECT 
                    id, usn, name, subject, cie1, cie2, cie_total50,
                    assignment1marks, assignment2marks, ass_total50,
                    see, see_total50, final_total150, grade
                FROM students
            """)
            
            # Drop old table and rename new table
            cursor.execute("DROP TABLE students")
            cursor.execute("ALTER TABLE students_new RENAME TO students")
            
            conn.commit()
            print(f"Successfully migrated {db_path}")
        elif 'final_total100' in columns:
            print(f"Database {db_path} already has final_total100 column")
        else:
            print(f"Database {db_path} does not have final_total150 column")
            
    except Exception as e:
        print(f"Error migrating {db_path}: {e}")
        conn.rollback()
    finally:
        conn.close()

if __name__ == "__main__":
    # Migrate all semester databases
    for sem in range(1, 5):
        db_path = f"eduboard_sem{sem}.db"
        migrate_database(db_path)
