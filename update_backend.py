import re

# Read the current app.py file
with open('c:/Users/windows11/OneDrive/Desktop/final proj2/app.py', 'r') as f:
    content = f.read()

# Update year2_toppers function
year2_pattern = r'(@app\.route\(/year2_toppers.*?agg_sorted = agg\.sort_values\(by="avg_final", ascending=False\)\s*combined = agg_sorted\.head\(10\)\.to_dict\(orient="records"\))'

year2_replacement = '''@app.route('/year2_toppers')
def year2_toppers():
    def load_df(sem):
        try:
            conn = sqlite3.connect(get_db_path(sem))
            df_local = pd.read_sql_query("SELECT usn, name, subject, final_total150, grade FROM students", conn)
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
            })'''

content = re.sub(year2_pattern, year2_replacement, content, flags=re.DOTALL)

# Write the updated content back
with open('c:/Users/windows11/OneDrive/Desktop/final proj2/app.py', 'w') as f:
    f.write(content)

print("Updated year2_toppers function successfully")
