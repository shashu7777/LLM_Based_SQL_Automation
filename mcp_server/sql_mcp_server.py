from fastmcp import FastMCP
from sqlalchemy import create_engine, inspect, text
import json
import os

mcp = FastMCP(name="SQL MCP Server")

# Global connection store
connections = {}
CONFIG_FILE = "last_conn.json"

# --- Utility: Load last connection if exists ---
def load_last_connection():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r") as f:
                data = json.load(f)
            print("🔁 Reconnecting using saved credentials...")
            return data
        except Exception as e:
            print(f"⚠️ Failed to load saved connection: {e}")
    return None


# --- Utility: Save connection info ---
def save_connection_info(info):
    try:
        with open(CONFIG_FILE, "w") as f:
            json.dump(info, f)
        print("💾 Connection info saved.")
    except Exception as e:
        print(f"⚠️ Could not save connection info: {e}")


@mcp.tool
def connect_to_db(db_type: str, host: str, username: str, password: str, database_name: str):
    """Connect once and save credentials to disk."""
    print("mcp connection db")
    with open("connect_to_db", "w") as f:
            json.dump({}, f)
    if "engine" in connections:
        return "✅ Already connected."

    if db_type == "mysql":
        conn_str = f"mysql+pymysql://{username}:{password}@{host}/{database_name}"
    elif db_type == "postgresql":
        conn_str = f"postgresql+psycopg2://{username}:{password}@{host}/{database_name}"
    elif db_type == "sqlserver":
        conn_str = f"mssql+pyodbc://{username}:{password}@{host}/{database_name}?driver=ODBC+Driver+17+for+SQL+Server"
    else:
        return "❌ Unsupported DB type."

    try:
        engine = create_engine(conn_str)
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))  # test connection
        connections["engine"] = engine

        # Save for persistence
        save_connection_info({
            "db_type": db_type,
            "host": host,
            "username": username,
            "password": password,
            "database_name": database_name
        })

        return "✅ Connected and credentials saved!"
    except Exception as e:
        return f"❌ Failed to connect: {str(e)}"


@mcp.tool
def get_schema():
    """Return full DB schema: tables, columns, PK, FK."""
    info = load_last_connection()
    conn_str = f"{info['db_type']}+pymysql://{info['username']}:{info['password']}@{info['host']}/{info['database_name']}"
    engine = create_engine(conn_str)
    if not engine:
        return "❌ No active connection."
    
    # engine = connections.get("engine")
    # if not engine:
    #     return "❌ No active connection."

    inspector = inspect(engine)
    schema = {}

    for table_name in inspector.get_table_names():
        table_info = {"columns": [], "primary_key": [], "foreign_keys": []}

        columns = inspector.get_columns(table_name)
        for col in columns:
            col_info = {
                "name": col["name"],
                "type": str(col["type"]),
                "nullable": col["nullable"],
                "default": col.get("default"),
                "autoincrement": col.get("autoincrement"),
            }
            table_info["columns"].append(col_info)

        pk = inspector.get_pk_constraint(table_name)
        table_info["primary_key"] = pk.get("constrained_columns", [])

        fks = inspector.get_foreign_keys(table_name)
        for fk in fks:
            fk_info = {
                "constrained_columns": fk["constrained_columns"],
                "referred_table": fk["referred_table"],
                "referred_columns": fk["referred_columns"],
                "name": fk.get("name")
            }
            table_info["foreign_keys"].append(fk_info)

        schema[table_name] = table_info

    return schema


@mcp.tool
def execute_query(query: str):
    """Execute any SQL query and return results in dict format, along with rowcount."""
    engine = connections.get("engine")
    if not engine:
        return {"error": "❌ No active connection."}

    with engine.connect() as conn:
        
        result = conn.execute(text(query))
        rowcount = result.rowcount

        try:
            rows = result.fetchall()
            columns = result.keys()

        except Exception:
            rows = []
            columns=[]

        return  {'columns':columns, 'rows':rows}

# --- Auto reconnect on startup ---
if __name__ == "__main__":

    mcp.run(transport="http", host="127.0.0.1", port=8000)
