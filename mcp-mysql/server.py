from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import mysql.connector
import os
import pulp

app = FastAPI(
    title="OPDS-AI MySQL Tools",
    description="Machine historian tools for OPDS-AI",
    version="2.0"
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

@app.get("/optimize_maintenance_schedule")
def optimize_maintenance_schedule(
    tool_wear_threshold: int = 200,
    max_per_day: int = 5,
    planning_days: int = 7
):
    """
    Generate an optimised maintenance schedule for high-risk machines
    using PuLP linear programming. Maximises machines scheduled,
    prioritises by risk score (tool wear + failure weighting),
    and respects daily technician capacity constraints.
    """

    # ── Step 1: Pull high-risk machines from MySQL ──
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute(f"""
        SELECT UDI, Product_ID, Type, Tool_wear_min,
               Torque_Nm, Rotational_speed_rpm, Machine_failure,
               TWF, HDF, PWF, OSF, RNF
        FROM ai4i_maintenance
        WHERE Tool_wear_min > {tool_wear_threshold}
        ORDER BY Tool_wear_min DESC
        LIMIT 30
    """)
    machines = cursor.fetchall()
    conn.close()

    if not machines:
        return {"message": "No high-risk machines found.", "schedule": []}

    # ── Step 2: Calculate risk score for each machine ──
    for m in machines:
        failure_bonus = (
            int(m["TWF"]) +
            int(m["HDF"]) +
            int(m["PWF"]) +
            int(m["OSF"]) +
            int(m["RNF"])
        ) * 50
        m["risk_score"] = int(m["Tool_wear_min"]) + failure_bonus

    days = list(range(1, planning_days + 1))
    machine_ids = [m["UDI"] for m in machines]
    risk = {m["UDI"]: m["risk_score"] for m in machines}
    max_risk = max(risk.values()) if risk else 1
    is_critical = {m["UDI"]: m["Tool_wear_min"] >= 252 for m in machines}

    # ── Step 3: Define the optimisation problem ──
    prob = pulp.LpProblem("MaintenanceSchedule", pulp.LpMaximize)

    # Decision variable: x[machine][day] = 1 if machine scheduled on that day
    x = {
        (uid, d): pulp.LpVariable(f"x_{uid}_{d}", cat="Binary")
        for uid in machine_ids
        for d in days
    }

    # ── Step 4: Objective ──
    # Primary: maximise number of machines scheduled (weight 1000)
    # Secondary: among scheduled, prefer higher risk scores
    # Tertiary: prefer earlier days for higher risk machines
    prob += (
        1000 * pulp.lpSum(x[(uid, d)] for uid in machine_ids for d in days) +
        pulp.lpSum(
            (risk[uid] / max_risk) * x[(uid, d)]
            for uid in machine_ids
            for d in days
        ) +
        pulp.lpSum(
            (risk[uid] / max_risk) * (planning_days - d + 1) * 0.1 * x[(uid, d)]
            for uid in machine_ids
            for d in days
        )
    )

    # ── Step 5: Constraints ──

    # Each machine scheduled at most once
    for uid in machine_ids:
        prob += pulp.lpSum(x[(uid, d)] for d in days) <= 1

    # Max machines per day (technician capacity)
    for d in days:
        prob += pulp.lpSum(x[(uid, d)] for uid in machine_ids) <= max_per_day

    # ── Step 6: Solve ──
    prob.solve(pulp.PULP_CBC_CMD(msg=0))

    # ── Step 7: Build the schedule output ──
    schedule = []
    unscheduled = []
    machine_lookup = {m["UDI"]: m for m in machines}

    for uid in machine_ids:
        assigned_day = None
        for d in days:
            if pulp.value(x[(uid, d)]) is not None and pulp.value(x[(uid, d)]) > 0.5:
                assigned_day = d
                break
        m = machine_lookup[uid]
        entry = {
            "UDI": uid,
            "Product_ID": m["Product_ID"],
            "Type": m["Type"],
            "Tool_wear_min": m["Tool_wear_min"],
            "Risk_score": risk[uid],
            "Critical": is_critical[uid],
            "Recommended_action": "Immediate tool replacement" if m["Tool_wear_min"] >= 252 else "Schedule tool inspection",
        }
        if assigned_day:
            entry["Scheduled_day"] = assigned_day
            schedule.append(entry)
        else:
            entry["Scheduled_day"] = "Unscheduled — exceeds capacity"
            unscheduled.append(entry)

    schedule.sort(key=lambda e: (e["Scheduled_day"], -e["Risk_score"]))

    return {
        "solver_status": pulp.LpStatus[prob.status],
        "total_high_risk_machines": len(machines),
        "total_scheduled": len(schedule),
        "total_unscheduled": len(unscheduled),
        "planning_days": planning_days,
        "max_per_day": max_per_day,
        "schedule": schedule,
        "unscheduled": unscheduled
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
