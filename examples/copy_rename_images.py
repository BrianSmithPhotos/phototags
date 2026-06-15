import os
import shutil
import argparse
import subprocess
import json
from datetime import datetime

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

def safe_filename(dst_folder, new_filename):
    """Ensure filename is unique by appending counter if needed."""
    base, ext = os.path.splitext(new_filename)
    counter = 1
    candidate = new_filename
    while os.path.exists(os.path.join(dst_folder, candidate)):
        candidate = f"{base}_{counter}{ext}"
        counter += 1
    return candidate

def rename_and_copy_images(src_folder, dst_folder, location):
    for filename in os.listdir(src_folder):
        if filename.lower().endswith((".xpg", ".xpeg", ".raf", ".xng", ".orf")):
            src_path = os.path.join(src_folder, filename)
            exif = get_exif_data(src_path)

            # Extract sequence number from filename (e.g., DSCF5064.RAF → 5064)
            seq_num = ''.join(filter(str.isdigit, filename))

            # Date taken
            date_taken = exif.get("DateTimeOriginal") or exif.get("CreateDate")
            if date_taken:
                dt = datetime.strptime(date_taken, "%Y:%m:%d %H:%M:%S")
                short_date = dt.strftime("%b-%d-%Y")   # e.g., Nov-21-2025
                month_folder = dt.strftime("%B")       # e.g., November
                day_folder = dt.strftime("%d")         # e.g., 21
                time_str = dt.strftime("%H-%M")        # e.g., 14-32
            else:
                short_date = "UnknownDate"
                month_folder = "UnknownMonth"
                day_folder = "UnknownDay"
                time_str = "UnknownTime"

            # Camera model with fallback
            camera = (
                exif.get("Model")
                or exif.get("CameraModelName")
                or exif.get("Make")
                or "UnknownCamera"
            )
            camera = camera.replace(" ", "-")

            # Lens info with fallback
            lens = (
                exif.get("LensModel")
                or exif.get("Lens")
                or exif.get("LensInfo")
                or "UnknownLens"
            )
            lens = lens.replace(" ", "-")
            lens = lens.replace("/", "-")
        

            # Build new filename
            new_filename = f"{seq_num}_{short_date}_{location}_{time_str}_{camera}_{lens}_{filename}"

            # Destination subfolder based on month/day
            dst_subfolder = os.path.join(dst_folder, month_folder, day_folder)
            if not os.path.exists(dst_subfolder):
                os.makedirs(dst_subfolder)

            # Ensure uniqueness
            new_filename = safe_filename(dst_subfolder, new_filename)

            dst_path = os.path.join(dst_subfolder, new_filename)

            # Copy file
            shutil.copy2(src_path, dst_path)
            print(f"Copied and renamed: {filename} → {new_filename} (into {month_folder}/{day_folder}/)")

def main():
    parser = argparse.ArgumentParser(description="Copy and rename images with EXIF metadata using exiftool.")
    parser.add_argument("src_folder", help="Source folder containing images")
    parser.add_argument("dst_folder", help="Destination folder for renamed images")
    parser.add_argument("location", help="Location string to include in filename")

    args = parser.parse_args()
    rename_and_copy_images(args.src_folder, args.dst_folder, args.location)

if __name__ == "__main__":
    main()


""""/Users/bsmi067/Library/CloudStorage/GoogleDrive-lunchwithalens@gmail.com/My Drive/vc/image_stuff/.venv/bin/python" 
"/Users/bsmi067/Library/CloudStorage/GoogleDrive-lunchwithalens@gmail.com/My Drive/vc/image_stuff/copy_rename_images.py" 
"/Volumes/Untitled/DCIM/103_FUJI" "/Users/bsmi067/Pictures/DxO" Test
or for FujiFilm python3 "/Users/bsmi067/Library/CloudStorage/GoogleDrive-lunchwithalens@gmail.com/My Drive/vc/image_stuff/copy_rename_images.py" 
"/Volumes/Untitled/DCIM/103_FUJI" "/Users/bsmi067/Pictures/DxO" SanRafael
or for OM python3 "/Users/bsmi067/Library/CloudStorage/GoogleDrive-lunchwithalens@gmail.com/My Drive/vc/image_stuff/copy_rename_images.py" "/Volumes/OM SYSTEM/DCIM/100OMSYS" "/Users/bsmi067/Pictures/DxO" SanRafael
"""