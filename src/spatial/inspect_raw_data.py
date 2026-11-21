import os
import zipfile
from pathlib import Path

# Explicit absolute path to prevent any resolution mistakes
PROJECT_ROOT = Path(__file__).resolve().parents[2]
RAW_DATA_DIR = PROJECT_ROOT / "data" / "raw"


def inspect_raw_data():
    print(f"Scanning target directory: {RAW_DATA_DIR}\n")

    if not RAW_DATA_DIR.exists():
        print(f"Directory does not exist: {RAW_DATA_DIR}")
        return

    all_files = os.listdir(RAW_DATA_DIR)
    target_files = [f for f in all_files if not f.startswith(".")]

    if not target_files:
        print("No files found in data/raw/.")
        return

    for filename in target_files:
        file_path = RAW_DATA_DIR / filename
        print(f"Found item: {filename}")

        # Handle ZIP archives automatically
        if filename.endswith(".zip"):
            print(f"  -> Unpacking ZIP archive: {filename}")
            try:
                with zipfile.ZipFile(file_path, "r") as zf:
                    extracted_dir = RAW_DATA_DIR / filename[:-4]
                    extracted_dir.mkdir(exist_ok=True)
                    zf.extractall(extracted_dir)
                    print(f"  -> Extracted contents to: {extracted_dir.name}/")

                    # List inner contents
                    for inner_file in zf.namelist():
                        print(f"     - {inner_file}")
            except Exception as e:
                print(f"  -> Error unpacking {filename}: {e}")

        elif filename.endswith((".csv", ".txt")):
            print("  -> Inspecting CSV header:")
            try:
                with open(file_path, encoding="ISO-8859-1") as f:
                    header = f.readline().strip()
                    print(f"     Header: {header[:150]}...")
            except Exception as e:
                print(f"  -> Error reading CSV header: {e}")

        print("-" * 50)


if __name__ == "__main__":
    inspect_raw_data()
