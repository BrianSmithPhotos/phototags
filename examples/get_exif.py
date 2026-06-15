import os
import shutil
import argparse
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


if __name__ == "__main__":
    file_path = sys.argv[1]
    exif = get_exif_data(file_path)
    print(json.dumps(exif))
