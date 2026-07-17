"""Multi-format data loader for AnaPPTAgent.

Supports CSV, Excel, SQLite, DuckDB, and Parquet file formats.
Uses pandas for loading and returns DataFrame objects.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd
from pandas import DataFrame

# Supported file extensions and their loaders
SUPPORTED_EXTENSIONS: set[str] = {
    ".csv", ".xlsx", ".xls", ".db", ".sqlite", ".sqlite3", ".duckdb", ".parquet",
}


def detect_files(data_dir: str | Path) -> list[Path]:
    """Scan a directory for supported data files.

    Args:
        data_dir: Path to the data directory.

    Returns:
        List of paths to supported data files, sorted by name.
    """
    data_dir = Path(data_dir)
    if not data_dir.exists() or not data_dir.is_dir():
        return []
    files: list[Path] = []
    for entry in data_dir.iterdir():
        if entry.is_file() and entry.suffix.lower() in SUPPORTED_EXTENSIONS:
            files.append(entry)
    return sorted(files)


def _get_table_name(path: Path) -> str:
    """Get the base name for a data file (without extension)."""
    return path.stem


def load_file(path: str | Path) -> DataFrame:
    """Load a single data file into a DataFrame.

    Automatically detects the file format based on extension.

    Args:
        path: Path to the data file.

    Returns:
        pandas DataFrame containing the data.

    Raises:
        ValueError: If the file format is not supported.
        FileNotFoundError: If the file does not exist.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")

    ext = path.suffix.lower()

    if ext == ".csv":
        return pd.read_csv(path)
    elif ext in (".xlsx", ".xls"):
        return pd.read_excel(path, engine="openpyxl")
    elif ext in (".db", ".sqlite", ".sqlite3"):
        return _load_sqlite(path)
    elif ext == ".duckdb":
        return _load_duckdb(path)
    elif ext == ".parquet":
        return pd.read_parquet(path)
    else:
        raise ValueError(f"Unsupported file format: {ext} for file {path}")


def _load_sqlite(path: Path) -> DataFrame:
    """Load the first table from a SQLite database file."""
    import sqlite3

    conn = sqlite3.connect(str(path))
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = cursor.fetchall()
        if not tables:
            return DataFrame()
        table_name = tables[0][0]
        return pd.read_sql_query(f"SELECT * FROM {table_name}", conn)
    finally:
        conn.close()


def _load_duckdb(path: Path) -> DataFrame:
    """Load the first table from a DuckDB database file."""
    import duckdb

    conn = duckdb.connect(str(path), read_only=True)
    try:
        tables = conn.execute("SHOW TABLES").fetchall()
        if not tables:
            return DataFrame()
        table_name = tables[0][0]
        return conn.execute(f"SELECT * FROM {table_name}").fetchdf()
    finally:
        conn.close()


def load_all(data_dir: str | Path) -> dict[str, DataFrame]:
    """Load all supported data files from a directory.

    Args:
        data_dir: Path to the data directory.

    Returns:
        Dictionary mapping file stem names to DataFrames.
    """
    files = detect_files(data_dir)
    result: dict[str, DataFrame] = {}
    for file_path in files:
        name = _get_table_name(file_path)
        result[name] = load_file(file_path)
    return result


def get_file_info(path: str | Path) -> dict[str, Any]:
    """Get metadata about a data file.

    Args:
        path: Path to the data file.

    Returns:
        Dictionary with file_name, format, size_bytes, and exists.
    """
    path = Path(path)
    info: dict[str, Any] = {
        "file_name": path.name,
        "format": path.suffix.lower().lstrip("."),
        "size_bytes": path.stat().st_size if path.exists() else 0,
        "exists": path.exists(),
    }
    return info
