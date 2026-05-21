from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import mysql.connector
import os

app = FastAPI(
    title="OPDS-AI MySQL Tools",
    description="Machine historian tools for OPDS-AI",
    version="1.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

def get_connection():
    return mysql.connector.connect(
        host=os.environ.get("MYSQL_HOST", "127.0.0.1"),
        port=int(os.environ.get("MYSQL_PORT", "3306")),
        user=os.environ.get("MYSQL_USER", "root"),
        password=os.environ.get("MYSQL_PASSWORD", "sensei_pass"),
        database=os.environ.get("MYSQL_DATABASE", "production_historian")
    )

@app.get("/query_machines")
def query_machines(limit: int = 10):
    """Query machine sensor data from the historian database"""
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute(f"SELECT * FROM ai4i_maintenance LIMIT {limit}")
    rows = cursor.fetchall()
    conn.close()
    return rows

@app.get("/count_failures")
def count_failures():
    """Count total machine failures in the historian database"""
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT COUNT(*) as total_failures FROM ai4i_maintenance WHERE Machine_failure = 1")
    result = cursor.fetchone()
    conn.close()
    return result

@app.get("/get_failure_breakdown")
def get_failure_breakdown():
    """Get breakdown of failure types TWF HDF PWF OSF RNF"""
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT 
            SUM(TWF) as tool_wear_failures,
            SUM(HDF) as heat_dissipation_failures,
            SUM(PWF) as power_failures,
            SUM(OSF) as overstrain_failures,
            SUM(RNF) as random_failures,
            SUM(Machine_failure) as total_failures
        FROM ai4i_maintenance
    """)
    result = cursor.fetchone()
    conn.close()
    return result

@app.get("/get_high_risk_machines")
def get_high_risk_machines(tool_wear_threshold: int = 200):
    """Get machines at high risk based on tool wear minutes"""
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute(f"""
        SELECT UDI, Product_ID, Type, Tool_wear_min,
               Torque_Nm, Rotational_speed_rpm
        FROM ai4i_maintenance
        WHERE Tool_wear_min > {tool_wear_threshold}
        ORDER BY Tool_wear_min DESC
        LIMIT 20
    """)
    rows = cursor.fetchall()
    conn.close()
    return rows

@app.get("/get_temperature_stats")
def get_temperature_stats():
    """Get average air and process temperatures across all machines"""
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT
            ROUND(AVG(Air_temperature_K), 2) as avg_air_temp_K,
            ROUND(AVG(Process_temperature_K), 2) as avg_process_temp_K,
            ROUND(MAX(Air_temperature_K), 2) as max_air_temp_K,
            ROUND(MAX(Process_temperature_K), 2) as max_process_temp_K
        FROM ai4i_maintenance
    """)
    result = cursor.fetchone()
    conn.close()
    return result

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)

