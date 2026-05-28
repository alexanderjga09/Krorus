import io
import zipfile

from modules.exif_checker import (
    HIGH_RISK_FIELDS,
    IMAGE_EXTENSIONS,
    SENSITIVE_EXIF_FIELDS,
    ArchiveExifReport,
    ExifFinding,
    check_archive_exif,
    check_image_exif,
    check_zip_exif,
)


class TestExifFinding:
    def test_create_finding(self):
        f = ExifFinding("photo.jpg", "GPSInfo", "GPS data found", "coords", True)
        assert f.filename == "photo.jpg"
        assert f.field_name == "GPSInfo"
        assert f.is_high_risk is True

    def test_default_high_risk_false(self):
        f = ExifFinding("a.jpg", "Make", "Camera make", "Canon")
        assert f.is_high_risk is False


class TestArchiveExifReport:
    def test_empty_report(self):
        r = ArchiveExifReport("test.zip")
        assert r.files_checked == 0
        assert r.files_with_exif == 0
        assert r.has_sensitive_data is False
        assert r.has_high_risk is False

    def test_summary_contains_filename(self):
        r = ArchiveExifReport("photo.zip")
        summary = r.summary()
        assert "photo.zip" in summary

    def test_summary_with_findings(self):
        r = ArchiveExifReport("test.zip")
        r.findings.append(ExifFinding("img.jpg", "GPSInfo", "GPS", "coords", True))
        r.files_checked = 1
        r.files_with_exif = 1
        r.has_sensitive_data = True
        r.has_high_risk = True
        summary = r.summary()
        assert "GPS" in summary
        assert "img.jpg" in summary


class TestConstants:
    def test_sensitive_fields_defined(self):
        assert "GPSInfo" in SENSITIVE_EXIF_FIELDS
        assert "CameraSerialNumber" in SENSITIVE_EXIF_FIELDS
        assert "OwnerName" in SENSITIVE_EXIF_FIELDS

    def test_high_risk_subset_of_sensitive(self):
        for field in HIGH_RISK_FIELDS:
            assert field in SENSITIVE_EXIF_FIELDS

    def test_image_extensions(self):
        assert "jpg" in IMAGE_EXTENSIONS
        assert "jpeg" in IMAGE_EXTENSIONS
        assert "webp" in IMAGE_EXTENSIONS


class TestCheckImageExif:
    def test_no_exif_data(self):
        findings = check_image_exif("test.jpg", b"not an image")
        assert findings == []

    def test_unsupported_extension(self):
        findings = check_image_exif("test.txt", b"some content")
        assert findings == []

    def test_empty_image_data(self):
        findings = check_image_exif("test.jpg", b"")
        assert findings == []


class TestCheckZipExif:
    def test_empty_zip(self):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("readme.txt", "hello")
        report = check_zip_exif(buf.getvalue(), "empty.zip")
        assert report.files_checked == 0

    def test_invalid_zip_data(self):
        report = check_zip_exif(b"not a zip file", "bad.zip")
        assert report.files_checked == 0
        assert report.files_with_exif == 0

    def test_corrupted_zip_is_handled(self):
        report = check_zip_exif(b"PK\x05\x06" + b"\x00" * 18, "corrupt.zip")
        assert report.files_checked == 0


class TestCheckArchiveExif:
    def test_unsupported_extension(self):
        report = check_archive_exif(b"data", "readme.txt")
        assert isinstance(report, ArchiveExifReport)
        assert report.files_checked == 0

    def test_zip_archive_delegation(self):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("readme.txt", "hello")
        report = check_archive_exif(buf.getvalue(), "archive.zip")
        assert isinstance(report, ArchiveExifReport)
