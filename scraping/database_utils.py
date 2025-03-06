# dataclass_utils.py

from dataclasses import fields, is_dataclass
from typing import get_origin, get_args, Union

def map_python_type_to_sql(py_type) -> str:
    """
    Very simple mapping from Python type to an SQL column type.
    Adjust as you see fit (this is naive).
    """
    # Strip Optional[...] if present
    # e.g. Optional[str] => str
    base = py_type
    if get_origin(py_type) is Union:
        # e.g. Union[str, NoneType]
        args = get_args(py_type)
        not_none = [a for a in args if a.__name__ != 'NoneType']
        if not_none:
            base = not_none[0]

    # Now map the base
    if base == str:
        return "TEXT"
    elif base == int:
        return "INTEGER"
    elif base == float:
        return "REAL"
    elif base == bool:
        return "BOOLEAN"
    else:
        # fallback
        return "TEXT"

def generate_create_table_sql(
    cls, 
    table_name: str, 
    primary_key: str,
    auto_increment_pk: bool = False
) -> str:
    """
    Generates a CREATE TABLE IF NOT EXISTS statement from a dataclass.
    The field named 'primary_key' is assigned 'PRIMARY KEY', or
    'PRIMARY KEY AUTOINCREMENT' if auto_increment_pk=True and the field is an int.
    """
    if not is_dataclass(cls):
        raise TypeError(f"{cls} is not a dataclass")

    column_defs = []
    for f in fields(cls):
        sql_type = map_python_type_to_sql(f.type)

        if f.name == primary_key:
            # If user wants an autoincrement PK and the field is integer
            if auto_increment_pk and sql_type.upper() in ("INT", "INTEGER", "BIGINT"):
                col_def = f"{f.name} INTEGER PRIMARY KEY AUTOINCREMENT"
            else:
                col_def = f"{f.name} {sql_type} PRIMARY KEY"
        else:
            col_def = f"{f.name} {sql_type}"
        column_defs.append(col_def)

    col_str = ",\n  ".join(column_defs)
    return f"CREATE TABLE IF NOT EXISTS {table_name} (\n  {col_str}\n);"

def generate_upsert_sql(
    cls, 
    table_name: str, 
    primary_key: str
) -> str:
    """
    Generates an INSERT/UPSERT statement that only updates columns
    that are NOT NULL in the new data (via COALESCE).
    e.g.:
      INSERT INTO table (col1, col2, ...)
      VALUES (?, ?, ...)
      ON CONFLICT(primary_key) DO UPDATE SET
         col1 = COALESCE(excluded.col1, table.col1),
         col2 = COALESCE(excluded.col2, table.col2), ...
    """
    if not is_dataclass(cls):
        raise TypeError(f"{cls} is not a dataclass")

    all_fields = [f.name for f in fields(cls)]
    col_list = ", ".join(all_fields)
    placeholders = ", ".join("?" for _ in all_fields)

    # Build the COALESCE lines
    coalesce_updates = []
    for c in all_fields:
        line = f"{c} = COALESCE(excluded.{c}, {table_name}.{c})"
        coalesce_updates.append(line)

    coalesce_str = ",\n  ".join(coalesce_updates)

    sql = f"""
INSERT INTO {table_name} ({col_list})
VALUES ({placeholders})
ON CONFLICT({primary_key}) DO UPDATE SET
  {coalesce_str}
;
"""
    return sql.strip()
