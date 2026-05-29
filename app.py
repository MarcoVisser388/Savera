from flask import Flask, render_template, jsonify, request
import sqlite3
import random
from datetime import datetime, timedelta
import config
import paho.mqtt.client as mqtt_client
import json
import threading
import requests as req
from database import save_energie_data

app = Flask(__name__)
app.config['SECRET_KEY'] = config.SECRET_KEY


# ── Database ──────────────────────────────────────────
def get_db():
    conn = sqlite3.connect(config.DATABASE)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS watermeter (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            liters REAL NOT NULL,
            liters_per_minuut REAL NOT NULL
        )
    ''')
    conn.commit()
    conn.close()
    print("Database aangemaakt!")


# ── Nep data ──────────────────────────────────────────
def genereer_nep_data():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM watermeter")
    count = cursor.fetchone()[0]

    if count == 0:
        print("Nep data genereren...")
        now = datetime.now()
        totaal_liters = 0

        for dag in range(7, 0, -1):
            for uur in range(24):
                timestamp = now - timedelta(days=dag, hours=uur)

                if 7 <= uur <= 9:
                    liters_per_min = round(random.uniform(1.5, 4.0), 2)
                elif 18 <= uur <= 22:
                    liters_per_min = round(random.uniform(1.0, 3.5), 2)
                elif 0 <= uur <= 6:
                    liters_per_min = round(random.uniform(0.0, 0.2), 2)
                else:
                    liters_per_min = round(random.uniform(0.2, 1.5), 2)

                liters = round(liters_per_min * 60, 2)
                totaal_liters += liters

                cursor.execute('''
                    INSERT INTO watermeter (timestamp, liters, liters_per_minuut)
                    VALUES (?, ?, ?)
                ''', (timestamp, totaal_liters, liters_per_min))

        conn.commit()
        print("Nep data gegenereerd!")
    conn.close()


# ── Routes ──────────────────────────────────────────
@app.route('/')
def index():
    return render_template('index.html')


@app.route('/water')
def water():
    return render_template('water.html')



@app.route('/api/energie/history')
def energie_history():

    conn = sqlite3.connect("database/savera.db")
    cursor = conn.cursor()

    cursor.execute("""
        SELECT timestamp, active_power_w
        FROM energie_data
        ORDER BY id DESC
        LIMIT 180
    """)

    rows = cursor.fetchall()
    conn.close()

    rows.reverse()

    return jsonify([
        {
            "timestamp": row[0],
            "active_power_w": row[1]
        }
        for row in rows
    ])

@app.route('/api/energie/periode')
def energie_periode():
    periode_type = request.args.get("type", "dag")

    conn = sqlite3.connect("database/savera.db")
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    if periode_type == "dag":
        group_format = "%H:00"
        since = "datetime('now', 'start of day')"
    elif periode_type == "week":
        group_format = "%Y-%m-%d"
        since = "datetime('now', '-7 days')"
    elif periode_type == "maand":
        group_format = "%Y-%m-%d"
        since = "datetime('now', '-30 days')"
    else:
        group_format = "%Y-%m"
        since = "datetime('now', '-12 months')"

    cursor.execute(f"""
        SELECT
            strftime('{group_format}', timestamp) as label,
            MIN(total_import_kwh) as import_start,
            MAX(total_import_kwh) as import_end,
            MIN(total_export_kwh) as export_start,
            MAX(total_export_kwh) as export_end,
            AVG(active_power_w) as gemiddeld_w,
            MAX(active_power_w) as piek_w
        FROM energie_data
        WHERE timestamp >= {since}
        GROUP BY label
        ORDER BY timestamp ASC
    """)

    rows = cursor.fetchall()
    conn.close()

    result = []

    for row in rows:
        verbruik_kwh = (row["import_end"] or 0) - (row["import_start"] or 0)
        teruglevering_kwh = (row["export_end"] or 0) - (row["export_start"] or 0)

        kosten = verbruik_kwh * config.STROOM_PRIJS_PER_KWH
        opbrengst = teruglevering_kwh * config.TERUGLEVER_PRIJS_PER_KWH

        result.append({
            "label": row["label"],
            "verbruik_kwh": round(verbruik_kwh, 4),
            "teruglevering_kwh": round(teruglevering_kwh, 4),
            "kosten": round(kosten, 2),
            "opbrengst": round(opbrengst, 2),
            "gemiddeld_w": round(row["gemiddeld_w"] or 0, 1),
            "piek_w": round(row["piek_w"] or 0, 1)
        })

    return jsonify(result)

@app.route('/api/energie/live')
def energie_live():
    try:
        response = req.get(config.P1_API_URL, timeout=5)
        data = response.json()

        active_power_w = data.get("active_power_w", 0)
        export_kwh = data.get("total_power_export_kwh", 0)
        import_kwh = data.get("total_power_import_kwh", 0)

        kosten_per_uur = round((active_power_w / 1000) * config.STROOM_PRIJS_PER_KWH, 4)

        save_energie_data(
            active_power_w,
            data.get("active_power_l1_w", 0),
            data.get("active_power_l2_w", 0),
            data.get("active_power_l3_w", 0),
            import_kwh,
            export_kwh,
            kosten_per_uur
        )

        return jsonify({
            "active_power_w": active_power_w,
            "active_power_l1_w": data.get("active_power_l1_w", 0),
            "active_power_l2_w": data.get("active_power_l2_w", 0),
            "active_power_l3_w": data.get("active_power_l3_w", 0),
            "total_power_import_kwh": import_kwh,
            "total_power_export_kwh": export_kwh,
            "kosten_per_uur": kosten_per_uur,
            "timestamp": datetime.now().strftime("%H:%M:%S")
        })

    except Exception as e:
        return jsonify({
            "error": str(e)
        }), 500

@app.route('/api/energie/vandaag')
def energie_vandaag():
    conn = sqlite3.connect("database/savera.db")
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            MIN(total_import_kwh) as import_start,
            MAX(total_import_kwh) as import_end,
            MIN(total_export_kwh) as export_start,
            MAX(total_export_kwh) as export_end
        FROM energie_data
        WHERE DATE(timestamp) = DATE('now')
    """)

    row = cursor.fetchone()
    conn.close()

    import_vandaag = (row["import_end"] or 0) - (row["import_start"] or 0)
    export_vandaag = (row["export_end"] or 0) - (row["export_start"] or 0)

    netto_kwh = export_vandaag - import_vandaag

    if netto_kwh >= 0:
        netto_euro = netto_kwh * config.TERUGLEVER_PRIJS_PER_KWH
    else:
        netto_euro = netto_kwh * config.STROOM_PRIJS_PER_KWH

    return jsonify({
        "import_vandaag_kwh": round(import_vandaag, 3),
        "export_vandaag_kwh": round(export_vandaag, 3),
        "netto_vandaag_kwh": round(netto_kwh, 3),
        "netto_euro": round(netto_euro, 2)
    })

@app.route('/weer')
def weer():
    return render_template('weer.html')


@app.route('/api/watermeter/live')
def watermeter_live():
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute('''
        SELECT timestamp, liters, liters_per_minuut
        FROM watermeter
        ORDER BY timestamp DESC
        LIMIT 1
    ''')

    row = cursor.fetchone()
    conn.close()

    if row is None:
        return jsonify({
            'liters_per_minuut': 0,
            'liters_per_uur': 0,
            'kosten_per_uur': 0,
            'timestamp': datetime.now().strftime('%H:%M:%S')
        })

    liters_per_minuut = row['liters_per_minuut']

    return jsonify({
        'liters_per_minuut': round(liters_per_minuut, 2),
        'liters_per_uur': round(liters_per_minuut * 60, 2),
        'kosten_per_uur': round((liters_per_minuut * 60 / 1000) * config.WATER_PRIJS_PER_M3, 4),
        'timestamp': row['timestamp']
    })


@app.route('/api/watermeter/vandaag')
def watermeter_vandaag():
    conn = get_db()
    cursor = conn.cursor()
    vandaag = datetime.now().date()
    cursor.execute('''
        SELECT SUM(liters) as totaal, AVG(liters_per_minuut) as gemiddeld
        FROM watermeter
        WHERE DATE(timestamp) = ?
    ''', (vandaag,))
    row = cursor.fetchone()
    conn.close()
    totaal = round(row['totaal'] or 0, 1)
    kosten = round((totaal / 1000) * config.WATER_PRIJS_PER_M3, 2)
    return jsonify({
        'liters': totaal,
        'kosten': kosten,
        'gemiddeld_per_minuut': round(row['gemiddeld'] or 0, 2)
    })


@app.route('/api/watermeter/week')
def watermeter_week():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT DATE(timestamp) as dag, SUM(liters) as totaal
        FROM watermeter
        WHERE timestamp >= datetime('now', '-7 days')
        GROUP BY DATE(timestamp)
        ORDER BY dag ASC
    ''')
    rows = cursor.fetchall()
    conn.close()
    dagen, waardes, kosten = [], [], []
    for row in rows:
        dagen.append(row['dag'])
        waardes.append(round(row['totaal'], 1))
        kosten.append(round((row['totaal'] / 1000) * config.WATER_PRIJS_PER_M3, 2))
    return jsonify({
        'dagen': dagen,
        'liters': waardes,
        'kosten': kosten
    })

@app.route('/energie')
def energie():
    return render_template('energie.html')

@app.route('/api/radar/tiles')
def radar_proxy():
    """Proxy voor KNMI WMS radar tiles met API key"""
    knmi_url = 'https://api.dataplatform.knmi.nl/wms/adaguc-server'
    params = dict(request.args)
    params['DATASET'] = 'radar_reflectivity_composites'

    try:
        resp = req.get(
            knmi_url,
            params=params,
            headers={'Authorization': 'eyJvcmciOiI1ZTU1NGUxOTI3NGE5NjAwMDEyYTNlYjEiLCJpZCI6IjI5YWUzZDZlYTIxZDQ4MWVhODkzNTIzODVjMzU1ZWQ2IiwiaCI6Im11cm11cjEyOCJ9'},
            timeout=10
        )
        return resp.content, resp.status_code, {'Content-Type': resp.headers.get('Content-Type', 'image/png')}
    except Exception as e:
        return str(e), 500


# ── MQTT ──────────────────────────────────────────
def on_mqtt_message(client, userdata, message):
    try:
        data = json.loads(message.payload.decode())
        liters_per_minuut = data.get('liters_per_minuut', 0)
        totaal_liters = data.get('totaal_liters', 0)

        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO watermeter (liters, liters_per_minuut)
            VALUES (?, ?)
        ''', (totaal_liters, liters_per_minuut))
        conn.commit()
        conn.close()
        print(f"Watermeter data ontvangen: {liters_per_minuut} L/min, totaal: {totaal_liters} L")
    except Exception as e:
        print(f"MQTT fout: {e}")


def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print("MQTT verbonden!")
        client.subscribe("savera/watermeter")
    else:
        print(f"MQTT verbinding mislukt: {rc}")


def start_mqtt():
    print("MQTT thread gestart...")
    print(f"Verbinden met MQTT broker: {config.MQTT_BROKER}:{config.MQTT_PORT}")

    client = mqtt_client.Client()

    client.on_connect = on_connect
    client.on_message = on_mqtt_message

    client.connect(config.MQTT_BROKER, config.MQTT_PORT, 60)

    client.loop_forever()


def start_mqtt_thread():
    thread = threading.Thread(target=start_mqtt, daemon=True)
    thread.start()


# ── Start ──────────────────────────────────────────
if __name__ == '__main__':
    init_db()
    from database import init_db as init_extra_db
    init_extra_db()

    # genereer_nep_data()
    start_mqtt_thread()
    app.run(debug=config.DEBUG, host='0.0.0.0', port=5000)