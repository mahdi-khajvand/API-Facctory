from flask import Flask, jsonify, request, g
import psycopg2
from psycopg2.extras import RealDictCursor
import os, json, time, sqlite3

app = Flask(__name__)

@app.before_request
def start_timer():
    g.start_time = time.time()

@app.after_request
def log_and_cors(response):
    response.headers['Access-Control-Allow-Origin'] = '*'
    try:
        duration = (time.time() - g.start_time) * 1000
        db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'analytics.db')
        conn = sqlite3.connect(db_path, timeout=10)
        cursor = conn.cursor()
        cursor.execute(
            'INSERT INTO api_logs (service, endpoint, status, duration, size) VALUES (?, ?, ?, ?, ?)',
            ("test.py", request.path, response.status_code, duration, len(response.data))
        )
        conn.commit()
        conn.close()
    except Exception:
        pass
    return response

@app.route("/api/joined")
def h():

    try:
        c = psycopg2.connect(**{'host': 'localhost', 'port': 5432, 'user': 'postgres', 'password': '219022', 'dbname': 'postgres'})
        cur = c.cursor(cursor_factory=RealDictCursor)
        cond, p = [], []
        
        q = 'SELECT "DL"."MeterInfo.Id" AS "DL_MeterInfo.Id", "DL"."MeterInfo.customer_id" AS "DL_MeterInfo.customer_id", "DL"."MeterInfo.TimeTag" AS "DL_MeterInfo.TimeTag", "DL"."MeterInfo.PowerActive" AS "DL_MeterInfo.PowerActive", "DL"."MeterInfo.PowerReactive" AS "DL_MeterInfo.PowerReactive", "DL"."MeterInfo.ActiveEnergyImport" AS "DL_MeterInfo.ActiveEnergyImport", "DL"."MeterInfo.ReactiveEnergyImport" AS "DL_MeterInfo.ReactiveEnergyImport", "DL"."MeterInfo.VoltageL1" AS "DL_MeterInfo.VoltageL1", "DL"."MeterInfo.VoltageL2" AS "DL_MeterInfo.VoltageL2", "DL"."MeterInfo.VoltageL3" AS "DL_MeterInfo.VoltageL3" FROM "DL.MeterInfo"'
        if cond:
            q += " WHERE " + " AND ".join(cond)

        limit = request.args.get('limit', default=100, type=int)
        offset = request.args.get('offset', default=0, type=int)
        q += f' LIMIT {limit} OFFSET {offset}'

        cur.execute(q, tuple(p))
        res = cur.fetchall()
        cur.close()
        c.close()
        return jsonify(res)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001)
