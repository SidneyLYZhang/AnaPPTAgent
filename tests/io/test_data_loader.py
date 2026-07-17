"""Tests for the data loader module."""

import sqlite3

import pandas as pd
import pytest

from anappt.io.data_loader import detect_files, get_file_info, load_all, load_file


@pytest.fixture
def data_dir(tmp_path):
    """Create a data directory with sample files of various formats."""
    d = tmp_path / "data"
    d.mkdir()

    # CSV
    df = pd.DataFrame({"name": ["A", "B"], "value": [1, 2]})
    df.to_csv(d / "sales.csv", index=False)

    # Excel
    df.to_excel(d / "inventory.xlsx", index=False, engine="openpyxl")

    # SQLite
    conn = sqlite3.connect(str(d / "users.db"))
    df.to_sql("mytable", conn, index=False)
    conn.close()

    # Parquet
    df.to_parquet(d / "events.parquet")

    # Non-data file (should be ignored)
    (d / "readme.txt").write_text("not data")

    return d


class TestDetectFiles:
    """Test file detection."""

    def test_detect_csv(self, data_dir):
        files = detect_files(data_dir)
        extensions = {f.suffix.lower() for f in files}
        assert ".csv" in extensions

    def test_detect_excel(self, data_dir):
        files = detect_files(data_dir)
        extensions = {f.suffix.lower() for f in files}
        assert ".xlsx" in extensions

    def test_detect_sqlite(self, data_dir):
        files = detect_files(data_dir)
        extensions = {f.suffix.lower() for f in files}
        assert ".db" in extensions

    def test_detect_parquet(self, data_dir):
        files = detect_files(data_dir)
        extensions = {f.suffix.lower() for f in files}
        assert ".parquet" in extensions

    def test_detect_ignores_non_data_files(self, data_dir):
        files = detect_files(data_dir)
        names = {f.name for f in files}
        assert "readme.txt" not in names

    def test_detect_returns_sorted(self, data_dir):
        files = detect_files(data_dir)
        names = [f.name for f in files]
        assert names == sorted(names)

    def test_detect_empty_dir(self, tmp_path):
        assert detect_files(tmp_path) == []

    def test_detect_nonexistent_dir(self):
        assert detect_files("/nonexistent/path/xyz") == []


class TestLoadFile:
    """Test individual file loading."""

    def test_load_csv(self, data_dir):
        df = load_file(data_dir / "sales.csv")
        assert len(df) == 2
        assert "name" in df.columns
        assert "value" in df.columns

    def test_load_excel(self, data_dir):
        df = load_file(data_dir / "inventory.xlsx")
        assert len(df) == 2
        assert "name" in df.columns

    def test_load_sqlite(self, data_dir):
        df = load_file(data_dir / "users.db")
        assert len(df) == 2
        assert "name" in df.columns

    def test_load_parquet(self, data_dir):
        df = load_file(data_dir / "events.parquet")
        assert len(df) == 2
        assert "name" in df.columns

    def test_load_unsupported_format(self, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("hello")
        with pytest.raises(ValueError, match="Unsupported file format"):
            load_file(f)

    def test_load_nonexistent_file(self):
        with pytest.raises(FileNotFoundError):
            load_file("/nonexistent/file.csv")


class TestLoadAll:
    """Test loading all files from a directory."""

    def test_load_all_returns_dict(self, data_dir):
        result = load_all(data_dir)
        assert isinstance(result, dict)
        assert len(result) == 4  # csv, xlsx, db, parquet

    def test_load_all_keys_are_file_stems(self, data_dir):
        result = load_all(data_dir)
        assert "sales" in result
        assert "inventory" in result
        assert "users" in result
        assert "events" in result

    def test_load_all_dataframes_have_data(self, data_dir):
        result = load_all(data_dir)
        for name, df in result.items():
            assert len(df) == 2
            assert "name" in df.columns

    def test_load_all_empty_dir(self, tmp_path):
        result = load_all(tmp_path)
        assert result == {}


class TestGetFileInfo:
    """Test file info retrieval."""

    def test_file_info_csv(self, data_dir):
        info = get_file_info(data_dir / "sales.csv")
        assert info["format"] == "csv"
        assert info["exists"] is True
        assert info["size_bytes"] > 0

    def test_file_info_nonexistent(self):
        info = get_file_info("/nonexistent/file.csv")
        assert info["exists"] is False
        assert info["size_bytes"] == 0
