import io

import piexif
import pytest
from PIL import Image

from services.gis_service.exif import extract_exif_gps


def _jpeg_with_gps(lat_dms, lat_ref, lon_dms, lon_ref) -> Image.Image:
    gps = {
        piexif.GPSIFD.GPSLatitude: lat_dms,
        piexif.GPSIFD.GPSLatitudeRef: lat_ref,
        piexif.GPSIFD.GPSLongitude: lon_dms,
        piexif.GPSIFD.GPSLongitudeRef: lon_ref,
    }
    exif_bytes = piexif.dump({"GPS": gps})
    buf = io.BytesIO()
    Image.new("RGB", (8, 8)).save(buf, "jpeg", exif=exif_bytes)
    buf.seek(0)
    return Image.open(buf)


def test_north_east_coordinates():
    # 45°30'0" N, 73°33'36" W → Montreal-ish
    img = _jpeg_with_gps(
        ((45, 1), (30, 1), (0, 1)), b"N",
        ((73, 1), (33, 1), (36, 1)), b"W",
    )
    lat, lon = extract_exif_gps(img)
    assert lat == pytest.approx(45.5)
    assert lon == pytest.approx(-73.56)


def test_south_reference_is_negative():
    img = _jpeg_with_gps(
        ((12, 1), (0, 1), (0, 1)), b"S",
        ((30, 1), (0, 1), (0, 1)), b"E",
    )
    lat, lon = extract_exif_gps(img)
    assert lat == pytest.approx(-12.0)
    assert lon == pytest.approx(30.0)


def test_image_without_exif_returns_none():
    assert extract_exif_gps(Image.new("RGB", (8, 8))) is None


def test_exif_without_gps_returns_none():
    exif_bytes = piexif.dump({"0th": {piexif.ImageIFD.Make: b"TestCam"}})
    buf = io.BytesIO()
    Image.new("RGB", (8, 8)).save(buf, "jpeg", exif=exif_bytes)
    buf.seek(0)
    assert extract_exif_gps(Image.open(buf)) is None
