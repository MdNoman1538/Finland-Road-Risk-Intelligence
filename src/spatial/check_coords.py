from pathlib import Path
import csv

PROJECT_ROOT = Path("/Users/noman/Documents/AI/RoadAccident")
RAW_DATA_DIR = PROJECT_ROOT / "data" / "raw"

def check_coordinate_columns():
    # Pick one legacy file and one modern file
    legacy_file = next(RAW_DATA_DIR.glob("**/tieliikenneonnettomuudet_2018_onnettomuus.csv"))
    modern_file = next(RAW_DATA_DIR.glob("**/tieliikenneonnettomuudet_2023_onnettomuudet.csv"))

    for f_path in [legacy_file, modern_file]:
        with open(f_path, 'r', encoding='ISO-8859-1') as f:
            reader = csv.reader(f, delimiter=';')
            header = next(reader)
            # Clean potential BOM from first header
            header[0] = header[0].lstrip('\ufeff')
            
            # Find coordinate-like columns
            coord_cols = [h for h in header if any(k in h.lower() for k in ['x', 'y', 'koord', 'pohjoinen', 'itainen', 'geom'])]
            print(f"File: {f_path.name}")
            print(f"  Coordinate-related columns found: {coord_cols}\n")

if __name__ == "__main__":
    check_coordinate_columns()