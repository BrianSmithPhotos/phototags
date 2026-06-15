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

def rename_and_copy_jpg(src_folder, dst_folder, location):
    for filename in os.listdir(src_folder):
        if filename.lower().endswith(".jpg"):
            src_path = os.path.join(src_folder, filename)
            exif = get_exif_data(src_path)

            multiple_exposure = exif.get("MultipleExposureMode")

            # Extract sequence number from filename
            seq_num = ''.join(filter(str.isdigit, filename))
            if not seq_num:
                seq_num = "0"

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

            # ArtFilter info with fallback (use first part before any semicolon)
            art_filter_effect = exif.get("ArtFilterEffect") or "NoFilter"
            art_filter = str(art_filter_effect).split(";")[0].replace(" ", "-")

            # Handle ArtFilter "Off" with PictureMode or StackedImage fallback
            if art_filter.lower() == "off":
                picture_mode = exif.get("PictureMode") or ""
                if "profile" in str(picture_mode).lower():
                    # Extract text before semicolon from PictureMode
                    art_filter = str(picture_mode).split(";")[0].replace(" ", "-")
                    print(f"Using PictureMode for {filename}: {art_filter}")
                else:
                    # If StackedImage is present and not 'No', use it instead of skipping
                    stacked = exif.get("StackedImage") or exif.get("StackedImages") or "No"
                    if str(stacked).lower() != "no" and str(stacked).strip() != "":
                        art_filter = str(stacked).split(";")[0].replace(" ", "-")
                        print(f"Using StackedImage for {filename}: {art_filter}")
                    else:
                        # Skip if no "profile" in PictureMode and no useful StackedImage, unless MultipleExposureMode is On
                        if multiple_exposure and str(multiple_exposure).startswith('On'):
                            art_filter = "MultipleExposure"
                        else:
                            print(f"Skipping {filename} — ArtFilter is Off, no profile in PictureMode, no StackedImage, and MultipleExposureMode is not On")
                            continue

            # Build new filename with ArtFilter
            new_filename = f"{seq_num}_{short_date}_{art_filter}_{location}_{time_str}_{camera}_{lens}_{filename}"

            # Destination subfolder
            dst_subfolder = os.path.join(dst_folder, month_folder, day_folder, "jpg")
            if not os.path.exists(dst_subfolder):
                os.makedirs(dst_subfolder)

            # Ensure uniqueness
            new_filename = safe_filename(dst_subfolder, new_filename)

            dst_path = os.path.join(dst_subfolder, new_filename)

            # Copy file
            shutil.copy2(src_path, dst_path)
            print(f"Copied and renamed: {filename} → {new_filename} (into {month_folder}/{day_folder}/jpg/)")

def main():
    parser = argparse.ArgumentParser(description="Copy and rename JPG images with EXIF metadata using exiftool.")
    parser.add_argument("src_folder", help="Source folder containing JPG images")
    parser.add_argument("dst_folder", help="Destination folder for renamed images")
    parser.add_argument("location", help="Location string to include in filename")

    args = parser.parse_args()
    rename_and_copy_jpg(args.src_folder, args.dst_folder, args.location)

if __name__ == "__main__":
    main()
