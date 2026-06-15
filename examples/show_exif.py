import os
import subprocess
import json
import sys

def get_exif_data(filepath):
    """Extract EXIF data using exiftool."""
    try:
        result = subprocess.run(
            ["exiftool", "-j", filepath],
            capture_output=True, text=True, check=True
        )
        data = json.loads(result.stdout)[0]
        return data
    except Exception as e:
        print(f"Error reading EXIF from {filepath}: {e}")
        return {}

def show_last_jpg_exif(src_folder, limit=8):
    """Find the last `limit` JPG files (by modification time) and display all EXIF data.

    Shows newest files first.
    """
    # Collect JPG files with full paths
    jpg_files = [f for f in os.listdir(src_folder) if f.lower().endswith('.jpg')]
    if not jpg_files:
        print("No JPG files found in the source directory.")
        return

    # Sort by modification time (oldest -> newest), then take the last `limit` entries
    jpg_files.sort(key=lambda fn: os.path.getmtime(os.path.join(src_folder, fn)))
    selected = jpg_files[-limit:]

    # Display newest first
    selected.reverse()

    for idx, filename in enumerate(selected, start=1):
        src_path = os.path.join(src_folder, filename)
        print(f"File {idx}: {filename}\n")
        print(f"Path: {src_path}\n")

        exif = get_exif_data(src_path)

        if exif:
            print("EXIF Data:")
            print("-" * 80)
            for key, value in sorted(exif.items()):
                print(f"{key}: {value}")
        else:
            print("No EXIF data found.")

        print("\n" + "=" * 80 + "\n")

def main():
    if len(sys.argv) < 2:
        print("Usage: python show_exif.py <source_folder>")
        sys.exit(1)
    
    src_folder = sys.argv[1]
    
    if not os.path.isdir(src_folder):
        print(f"Error: {src_folder} is not a valid directory.")
        sys.exit(1)
    
    show_last_jpg_exif(src_folder, limit=8)

if __name__ == "__main__":
    main()
