from pathlib import Path
import csv

PROJECT_ROOT = Path(__file__).resolve().parents[2]
RAW_DATA_DIR = PROJECT_ROOT / "data" / "raw"

def check_csv_headers():
    csv_files = list(RAW_DATA_DIR.glob("**/*onnettomuus*.csv")) + list(RAW_DATA_DIR.glob("**/*onnettomuudet*.csv"))
    
    print(f"Found {len(csv_files)} accident CSV files across all year folders.\n")
    
    schemas = {}
    for file_path in csv_files:
        try:
            with open(file_path, 'r', encoding='ISO-8859-1') as f:
                reader = csv.reader(f, delimiter=';') # Finnish CSVs usually use semicolons
                header = next(reader)
                # Store sorted tuple of headers for comparison
                schemas[file_path.name] = set(h.lower().strip() for h in header)
                print(f"File: {file_path.name}")
                print(f"  Columns ({len(header)}): {header[:5]}... (delimiter likely ';')\n")
        except Exception as e:
            print(f"Error reading {file_path.name}: {e}")

if __name__ == "__main__":
    check_csv_headers()