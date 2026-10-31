MediTrack Hospital Analytics - Flask + SQLite

Run:
  1. pip install flask
  2. python app.py
  3. Open http://127.0.0.1:5000

The first run creates hospital.db from the CSV files in data/.
Delete hospital.db to reset the data.

Files:
  app.py               server, database setup and API
  templates/index.html the website (dashboard, records, add form, SQL console)
  data/*.csv           sample data loaded into the database
