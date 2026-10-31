"""Create the bronze tables, file formats and run log for the 6 sources (safe to run again)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common import connect  # noqa: E402

SQL_FILE = Path(__file__).resolve().parent.parent / "sql" / "bronze_sources.sql"


def statements(text):
    lines = [line for line in text.splitlines() if not line.strip().startswith("--")]
    return [s.strip() for s in "\n".join(lines).split(";") if s.strip()]


def main():
    con = connect()
    cur = con.cursor()
    try:
        for stmt in statements(SQL_FILE.read_text()):
            cur.execute(stmt)
            print("  ok:", " ".join(stmt.split())[:90])
    finally:
        cur.close()
        con.close()
    print("Bronze tables ready.")


if __name__ == "__main__":
    main()
