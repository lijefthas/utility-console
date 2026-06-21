"""
SQL query strings and MySQL shell command builder for VIS device operations.
All queries are defined here and imported wherever they are needed.
"""

# ── Constants ─────────────────────────────────────────────────────────────────

SQL_SHOW_DATABASES = "SHOW DATABASES"
SQL_SHOW_TABLES    = "SHOW TABLES"

SQL_LIST_MODULES = "SELECT filename FROM epr_modules ORDER BY filename"

SQL_SELECT_LAST_UNFINALIZED_TRANSACTION = (
    "SELECT * FROM epr_transactions"
    " WHERE controller_reference IS NULL"
    " AND (sale_volume IS NULL OR sale_value IS NULL)"
    " ORDER BY date_time DESC LIMIT 1"
)

SQL_MODULE_DETAILS = (
    "SELECT CONCAT(name, '|', version) FROM eprvi.epr_module_detail"
    " UNION ALL"
    " SELECT CONCAT(name, '|', version) FROM eprtip.tip_module_detail"
)

# ── Parameterised builders ────────────────────────────────────────────────────

def sql_set_module_status(name: str, status: str) -> str:
    return f"UPDATE epr_modules SET status='{status}' WHERE filename='{name}'"


def sql_select_all(table: str) -> str:
    return f"SELECT * FROM {table}"


# ── Shell command builder ─────────────────────────────────────────────────────

def mysql_cmd(query: str, database: str = None, with_headers: bool = False) -> str:
    """Wrap a SQL query in a mysql CLI invocation for SSH execution."""
    db_flag = f"-D {database} " if database else ""
    silent  = "" if with_headers else " --silent"
    return f"mysql {db_flag}--batch{silent} -e \"{query}\""
