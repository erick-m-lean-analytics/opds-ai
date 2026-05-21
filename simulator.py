import mysql.connector
import random
import time
import math

MAX_ROWS = 50000
INTERVAL = 2
ORIGINAL_ROWS = 10000  # Reset point on every start

def get_connection():
    return mysql.connector.connect(
        host="127.0.0.1",
        port=3306,
        user="root",
        password="sensei_pass",
        database="production_historian"
    )

def reset_to_original(cursor, conn):
    cursor.execute("SELECT COUNT(*) FROM ai4i_maintenance")
    count = cursor.fetchone()[0]
    if count > ORIGINAL_ROWS:
        cursor.execute(f"DELETE FROM ai4i_maintenance WHERE UDI > {ORIGINAL_ROWS}")
        conn.commit()
        print(f"[Startup Reset] Removed simulated rows. Restored to {ORIGINAL_ROWS:,} original rows.")
    else:
        print(f"[Startup] Data is clean. Current rows: {count:,}")

def get_next_udi(cursor):
    cursor.execute("SELECT MAX(UDI) FROM ai4i_maintenance")
    result = cursor.fetchone()
    return (result[0] or ORIGINAL_ROWS) + 1

def cleanup_old_rows(cursor, conn):
    cursor.execute("SELECT COUNT(*) FROM ai4i_maintenance")
    count = cursor.fetchone()[0]
    if count > MAX_ROWS:
        excess = count - MAX_ROWS
        cursor.execute(f"DELETE FROM ai4i_maintenance WHERE UDI > {ORIGINAL_ROWS} ORDER BY UDI ASC LIMIT {excess}")
        conn.commit()

def simulate_reading(udi, t):
    machine_types = ["L", "M", "H"]
    machine_type = random.choice(machine_types)
    product_id = f"{machine_type}-{random.randint(10000, 99999)}"

    # Temperature drifts slowly
    air_temp = round(298 + 5 * math.sin(t / 50) + random.uniform(-0.5, 0.5), 1)
    process_temp = round(air_temp + 10 + random.uniform(-0.3, 0.3), 1)

    # RPM by machine type
    if machine_type == "L":
        rpm = random.randint(1168, 1980)
    elif machine_type == "M":
        rpm = random.randint(1300, 2200)
    else:
        rpm = random.randint(1500, 2500)

    torque = round(random.uniform(3.5, 76.6), 1)
    tool_wear = random.randint(0, 253)

    # Realistic failure thresholds matching AI4I dataset
    twf = 1 if tool_wear > 200 and random.random() < 0.05 else 0
    hdf = 1 if (process_temp - air_temp < 8.6) and rpm < 1380 and random.random() < 0.3 else 0
    pwf = 1 if (torque * rpm < 3500 or torque * rpm > 9000) and random.random() < 0.05 else 0
    osf = 1 if torque > 55 and tool_wear > 200 and random.random() < 0.1 else 0
    rnf = 1 if random.random() < 0.001 else 0
    failure = 1 if any([twf, hdf, pwf, osf, rnf]) else 0

    return {
        "UDI": udi,
        "Product_ID": product_id,
        "Type": machine_type,
        "Air_temperature_K": air_temp,
        "Process_temperature_K": process_temp,
        "Rotational_speed_rpm": rpm,
        "Torque_Nm": torque,
        "Tool_wear_min": tool_wear,
        "Machine_failure": failure,
        "TWF": twf, "HDF": hdf, "PWF": pwf, "OSF": osf, "RNF": rnf
    }

def insert_reading(cursor, data):
    cursor.execute("""
        INSERT INTO ai4i_maintenance
        (UDI, Product_ID, Type, Air_temperature_K, Process_temperature_K,
         Rotational_speed_rpm, Torque_Nm, Tool_wear_min, Machine_failure,
         TWF, HDF, PWF, OSF, RNF)
        VALUES (%(UDI)s, %(Product_ID)s, %(Type)s, %(Air_temperature_K)s,
                %(Process_temperature_K)s, %(Rotational_speed_rpm)s, %(Torque_Nm)s,
                %(Tool_wear_min)s, %(Machine_failure)s,
                %(TWF)s, %(HDF)s, %(PWF)s, %(OSF)s, %(RNF)s)
    """, data)

print("=" * 60)
print("OPDS-AI Data Simulator")
print(f"Interval: {INTERVAL}s | Max rows: {MAX_ROWS:,} | Reset point: {ORIGINAL_ROWS:,}")
print("=" * 60)

# Reset to original rows on every startup
conn = get_connection()
cursor = conn.cursor()
reset_to_original(cursor, conn)
conn.close()

print("Simulator running... Press Ctrl+C to stop.")
print("-" * 60)

t = 0
try:
    while True:
        conn = get_connection()
        cursor = conn.cursor()
        udi = get_next_udi(cursor)
        data = simulate_reading(udi, t)
        insert_reading(cursor, data)
        conn.commit()
        cleanup_old_rows(cursor, conn)

        status = "FAILURE" if data["Machine_failure"] else "OK"
        print(f"UDI: {udi} | Type: {data['Type']} | "
              f"Temp: {data['Air_temperature_K']}K | "
              f"RPM: {data['Rotational_speed_rpm']} | "
              f"Tool Wear: {data['Tool_wear_min']}min | "
              f"Status: {status}")

        conn.close()
        t += 1
        time.sleep(INTERVAL)

except KeyboardInterrupt:
    print("\nSimulator stopped.")
