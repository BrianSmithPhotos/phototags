from phototags.services.exif_service import ExifService


def test_map_for_ui_prefers_first_available_key_per_field() -> None:
    service = ExifService()
    metadata = {
        "XMP:Title": "Sunset",
        "IPTC:ObjectName": "Should not win",
        "IFD0:Make": "OM Digital Solutions",
        "IFD0:Model": "OM-1",
        "Composite:Aperture": "4",
        "Composite:ShutterSpeed": "1/500",
        "ExifIFD:FocalLength": "150 mm",
        "ExifIFD:DateTimeOriginal": "2026:06:21 10:00:00",
        "ExifIFD:ISO": "200",
    }

    mapped = service.map_for_ui(metadata)

    assert mapped.title == "Sunset"
    assert mapped.camera == "OM Digital Solutions OM-1"
    assert mapped.camera_model == "OM-1"
    assert mapped.aperture == "f/4"
    assert mapped.shutter_speed == "1/500"
    assert mapped.focal_length == "150 mm"
    assert mapped.iso == "200"
    assert mapped.captured_at == "2026:06:21 10:00:00"
    assert mapped.captured_at_display == "Sun, Jun 21, 2026 10:00:00"


def test_map_for_ui_returns_empty_strings_when_nothing_present() -> None:
    service = ExifService()

    mapped = service.map_for_ui({})

    assert mapped.title == ""
    assert mapped.camera == ""
    assert mapped.gps_latitude == ""
    assert mapped.art_filter_token == ""


def test_keywords_text_joins_list_values_with_comma() -> None:
    service = ExifService()
    metadata = {"XMP:Subject": ["beach", "sunset", "family"]}

    mapped = service.map_for_ui(metadata)

    assert mapped.keywords == "beach, sunset, family"


def test_keywords_text_falls_back_through_candidates_when_list_is_empty() -> None:
    service = ExifService()
    metadata = {"XMP:Subject": [], "IPTC:Keywords": "beach, sunset"}

    mapped = service.map_for_ui(metadata)

    assert mapped.keywords == "beach, sunset"


def test_gps_coordinate_parses_plain_decimal_value() -> None:
    service = ExifService()
    metadata = {"Composite:GPSLatitude": "45.5"}

    mapped = service.map_for_ui(metadata)

    assert mapped.gps_latitude == "45.5000000"


def test_gps_coordinate_parses_dms_text_with_hemisphere_suffix() -> None:
    service = ExifService()
    metadata = {"Composite:GPSLatitude": "45 deg 30' 0.00\" S"}

    mapped = service.map_for_ui(metadata)

    assert mapped.gps_latitude == "-45.5000000"


def test_gps_coordinate_uses_ref_key_when_dms_text_has_no_hemisphere() -> None:
    service = ExifService()
    metadata = {
        "Composite:GPSLongitude": "122 deg 15' 0.00\"",
        "GPS:GPSLongitudeRef": "W",
    }

    mapped = service.map_for_ui(metadata)

    assert mapped.gps_longitude == "-122.2500000"


def test_gps_coordinate_rejects_out_of_range_latitude() -> None:
    service = ExifService()
    metadata = {"Composite:GPSLatitude": "95 deg 0' 0.00\" N"}

    mapped = service.map_for_ui(metadata)

    # 95 is out of latitude range, so parsing fails and the raw text passes through.
    assert mapped.gps_latitude == "95 deg 0' 0.00\" N"


def test_gps_altitude_formats_plain_numeric_value() -> None:
    service = ExifService()
    metadata = {"Composite:GPSAltitude": "123.456"}

    mapped = service.map_for_ui(metadata)

    assert mapped.gps_altitude == "123.46"


def test_gps_altitude_extracts_number_from_unit_suffixed_text() -> None:
    service = ExifService()
    metadata = {"Composite:GPSAltitude": "123.4 m Above Sea Level"}

    mapped = service.map_for_ui(metadata)

    assert mapped.gps_altitude == "123.4"


def test_art_filter_token_prefers_active_art_filter_effect() -> None:
    service = ExifService()
    metadata = {"Olympus:ArtFilterEffect": "Dramatic Tone; Yes; 0"}

    mapped = service.map_for_ui(metadata)

    assert mapped.art_filter_token == "Dramatic Tone"


def test_art_filter_token_ignores_off_art_filter_effect() -> None:
    service = ExifService()
    metadata = {"Olympus:ArtFilterEffect": "Off"}

    mapped = service.map_for_ui(metadata)

    assert mapped.art_filter_token == ""


def test_art_filter_token_falls_back_to_picture_mode_profile() -> None:
    service = ExifService()
    metadata = {"Olympus:PictureMode": "Color Profile 1"}

    mapped = service.map_for_ui(metadata)

    assert mapped.art_filter_token == "Color Profile 1"


def test_art_filter_token_falls_back_to_stacked_image_state() -> None:
    service = ExifService()
    metadata = {"Olympus:StackedImage": "Live Composite"}

    mapped = service.map_for_ui(metadata)

    assert mapped.art_filter_token == "Live Composite"


def test_art_filter_token_falls_back_to_multiple_exposure_mode() -> None:
    service = ExifService()
    metadata = {"Olympus:MultipleExposureMode": "On (2 Shots)"}

    mapped = service.map_for_ui(metadata)

    assert mapped.art_filter_token == "MultipleExposure"


def test_format_aperture_handles_integer_and_fractional_values() -> None:
    service = ExifService()

    assert service._format_aperture("4") == "f/4"
    assert service._format_aperture("2.8") == "f/2.8"
    assert service._format_aperture("f/5.6") == "f/5.6"
    assert service._format_aperture("") == ""
