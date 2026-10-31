import csv, os, re, sqlite3
from flask import Flask, jsonify, request, render_template, g

BASE = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(BASE, "hospital.db")
app = Flask(__name__)

SCHEMA = """
CREATE TABLE departments (dept_id INTEGER PRIMARY KEY, dept_name TEXT NOT NULL UNIQUE);
CREATE TABLE doctors (doctor_id INTEGER PRIMARY KEY, doctor_name TEXT NOT NULL,
  dept_id INTEGER NOT NULL REFERENCES departments(dept_id), consultation_fee REAL NOT NULL CHECK (consultation_fee > 0));
CREATE TABLE patients (patient_id INTEGER PRIMARY KEY, patient_name TEXT NOT NULL,
  gender TEXT NOT NULL CHECK (gender IN ('Male','Female')), age INTEGER NOT NULL CHECK (age BETWEEN 0 AND 120), city TEXT);
CREATE TABLE appointments (appt_id INTEGER PRIMARY KEY, patient_id INTEGER NOT NULL REFERENCES patients(patient_id),
  doctor_id INTEGER NOT NULL REFERENCES doctors(doctor_id), appt_date TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('Completed','Cancelled','No-show')));
CREATE TABLE billing (bill_id INTEGER PRIMARY KEY, appt_id INTEGER NOT NULL UNIQUE REFERENCES appointments(appt_id),
  amount REAL NOT NULL, payment_status TEXT NOT NULL CHECK (payment_status IN ('Paid','Pending','Insurance')));
CREATE INDEX idx_appt_date ON appointments(appt_date);
CREATE VIEW hospital_flat AS
SELECT a.appt_id, a.appt_date, substr(a.appt_date,1,7) AS month, p.patient_name, p.gender, p.age, p.city,
       doc.doctor_name, d.dept_name, a.status, b.amount AS bill_amount, b.payment_status
FROM appointments a JOIN patients p ON p.patient_id=a.patient_id JOIN doctors doc ON doc.doctor_id=a.doctor_id
JOIN departments d ON d.dept_id=doc.dept_id LEFT JOIN billing b ON b.appt_id=a.appt_id;
"""

def init_db():
    con = sqlite3.connect(DB)
    con.executescript(SCHEMA)
    for table in ["departments", "doctors", "patients", "appointments", "billing"]:
        with open(os.path.join(BASE, "data", table + ".csv"), newline="", encoding="utf-8") as f:
            rows = list(csv.reader(f))
        marks = ",".join("?" * len(rows[0]))
        con.executemany(f"INSERT INTO {table} ({','.join(rows[0])}) VALUES ({marks})", rows[1:])
    con.commit(); con.close()

def db_ready():
    if not os.path.exists(DB) or os.path.getsize(DB) == 0:
        return False
    try:
        con = sqlite3.connect(DB)
        n = con.execute("SELECT COUNT(*) FROM appointments").fetchone()[0]
        con.close()
        return n > 0
    except sqlite3.Error:
        return False

if not db_ready():
    if os.path.exists(DB):
        os.remove(DB)
    init_db()

def db():
    if "db" not in g:
        g.db = sqlite3.connect(DB); g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db

@app.teardown_appcontext
def close_db(_):
    con = g.pop("db", None)
    if con: con.close()

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/data")
def data():
    c = db()
    depts = [{"id": r[0], "name": r[1]} for r in c.execute("SELECT dept_id, dept_name FROM departments ORDER BY dept_id")]
    docs = [{"id": r[0], "name": r[1], "dept": r[2], "fee": r[3]} for r in c.execute("SELECT doctor_id, doctor_name, dept_id, consultation_fee FROM doctors ORDER BY doctor_id")]
    pats = [{"id": r[0], "name": r[1], "gender": r[2], "age": r[3], "city": r[4]} for r in c.execute("SELECT * FROM patients ORDER BY patient_id")]
    appts = [{"id": r[0], "date": r[1], "docId": r[2], "patId": r[3], "status": r[4], "amount": r[5] or 0, "pay": r[6] or ""}
             for r in c.execute("""SELECT a.appt_id, a.appt_date, a.doctor_id, a.patient_id, a.status, b.amount, b.payment_status
                                   FROM appointments a LEFT JOIN billing b ON b.appt_id=a.appt_id ORDER BY a.appt_date, a.appt_id""")]
    names = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]
    months = [[m, names[int(m[5:7]) - 1]] for (m,) in c.execute("SELECT DISTINCT substr(appt_date,1,7) FROM appointments ORDER BY 1")]
    as_of = c.execute("SELECT MAX(appt_date) FROM appointments").fetchone()[0]
    return jsonify(AS_OF=as_of, MONTHS=months, DEPTS=depts, DOCTORS=docs, PATIENTS=pats, APPTS=appts)

@app.route("/api/appointments", methods=["POST"])
def add_appt():
    j = request.get_json(force=True); c = db()
    try:
        nid = (c.execute("SELECT COALESCE(MAX(appt_id),5000)+1 FROM appointments").fetchone()[0])
        c.execute("INSERT INTO appointments VALUES (?,?,?,?,?)", (nid, int(j["patId"]), int(j["docId"]), j["date"], j["status"]))
        if j["status"] == "Completed":
            bid = c.execute("SELECT COALESCE(MAX(bill_id),9000)+1 FROM billing").fetchone()[0]
            c.execute("INSERT INTO billing VALUES (?,?,?,?)", (bid, nid, float(j.get("amount") or 0), j.get("pay") or "Pending"))
        c.commit()
    except (sqlite3.Error, KeyError, ValueError) as e:
        c.rollback(); return jsonify(error=str(e)), 400
    return jsonify(id=nid)

@app.route("/api/appointments/<int:aid>", methods=["DELETE"])
def del_appt(aid):
    c = db(); c.execute("DELETE FROM billing WHERE appt_id=?", (aid,)); c.execute("DELETE FROM appointments WHERE appt_id=?", (aid,)); c.commit()
    return jsonify(ok=True)

@app.route("/api/query", methods=["POST"])
def query():
    sql = (request.get_json(force=True).get("sql") or "").strip().rstrip(";")
    if not re.match(r"(?is)^select\b", sql) or ";" in sql:
        return jsonify(error="Only a single SELECT statement is allowed."), 400
    ro = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    try:
        cur = ro.execute(sql); cols = [d[0] for d in cur.description]; rows = cur.fetchmany(200)
        return jsonify(cols=cols, rows=rows)
    except sqlite3.Error as e:
        return jsonify(error=str(e)), 400
    finally:
        ro.close()

if __name__ == "__main__":
    app.run(debug=True)
