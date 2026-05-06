import io
import logging
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

try:
    from PIL import Image
    from PIL.ExifTags import GPSTAGS, TAGS

    HAS_PIL = True
except ImportError:
    HAS_PIL = False

try:
    from exif_rs import check_archive_exif as rust_check_exif

    HAS_RUST = True
except ImportError:
    HAS_RUST = False

logger = logging.getLogger(__name__)

IMAGE_EXTENSIONS = {"jpg", "jpeg", "tif", "tiff", "webp"}
ARCHIVE_EXTENSIONS = {"zip", "rar", "7z", "tar", "gz", "bz2"}

SENSITIVE_EXIF_FIELDS = {
    "GPSInfo": "Información GPS detectada",
    "GPSLatitude": "Latitud GPS encontrada",
    "GPSLongitude": "Longitud GPS encontrada",
    "GPSLatitudeRef": "Referencia de latitud GPS",
    "GPSLongitudeRef": "Referencia de longitud GPS",
    "GPSAltitude": "Altitud GPS encontrada",
    "GPSAltitudeRef": "Referencia de altitud GPS",
    "GPSMapDatum": "Datum de mapa GPS",
    "GPSVersionID": "Versión GPS",
    "GPSTimeStamp": "Marca de tiempo GPS",
    "GPSDateStamp": "Marca de fecha GPS",
    "MakerNote": "Notas del fabricante (puede contener serial)",
    "UserComment": "Comentario del usuario",
    "ImageDescription": "Descripción de la imagen",
    "Artist": "Artista/Autor",
    "Copyright": "Copyright",
    "Software": "Software utilizado",
    "DateTime": "Fecha y hora de captura",
    "DateTimeOriginal": "Fecha y hora original",
    "DateTimeDigitized": "Fecha y hora de digitalización",
    "CameraSerialNumber": "Número de serie de cámara",
    "SerialNumber": "Número de serie",
    "LensSerialNumber": "Número de serie del lente",
    "BodySerialNumber": "Número de serie del cuerpo",
    "LensModel": "Modelo del lente",
    "Make": "Fabricante de cámara",
    "Model": "Modelo de cámara",
    "LensInfo": "Información del lente",
    "OwnerName": "Nombre del propietario",
    "InternalSerialNumber": "Número de serie interno",
}

HIGH_RISK_FIELDS = {
    "GPSInfo",
    "GPSLatitude",
    "GPSLongitude",
    "GPSLatitudeRef",
    "GPSLongitudeRef",
    "GPSAltitude",
    "GPSAltitudeRef",
    "GPSMapDatum",
    "GPSTimeStamp",
    "GPSDateStamp",
    "CameraSerialNumber",
    "SerialNumber",
    "LensSerialNumber",
    "BodySerialNumber",
    "InternalSerialNumber",
    "OwnerName",
}


@dataclass
class ExifFinding:
    filename: str
    field_name: str
    description: str
    value: str = ""
    is_high_risk: bool = False


@dataclass
class ArchiveExifReport:
    archive_filename: str
    findings: list[ExifFinding] = field(default_factory=list)
    files_checked: int = 0
    files_with_exif: int = 0
    has_sensitive_data: bool = False
    has_high_risk: bool = False

    def summary(self) -> str:
        lines = [f"📦 Archivo: {self.archive_filename}"]
        lines.append(f"📄 Archivos revisados: {self.files_checked}")
        lines.append(f"🏷️ Archivos con EXIF: {self.files_with_exif}")
        lines.append(f"⚠️ Datos sensibles: {self.has_sensitive_data}")
        lines.append(f"🚨 Riesgo alto: {self.has_high_risk}")
        if self.findings:
            lines.append("\n🔍 Hallazgos:")
            for f in self.findings:
                risk = "🚨" if f.is_high_risk else "⚠️"
                lines.append(f"  {risk} {f.filename}: {f.description}")
                if f.value:
                    val_display = f.value[:100] + ("..." if len(f.value) > 100 else "")
                    lines.append(f"     Valor: {val_display}")
        return "\n".join(lines)


def _extract_exif_data(image_data: bytes) -> dict:
    """Extrae todos los datos EXIF de una imagen en bytes."""
    if not HAS_PIL:
        return {}

    try:
        img = Image.open(io.BytesIO(image_data))
        exif_data = img.getexif()
        if not exif_data:
            return {}

        result = {}
        for tag_id, value in exif_data.items():
            tag_name = TAGS.get(tag_id, str(tag_id))
            result[tag_name] = value

        if "GPSInfo" in result and isinstance(result["GPSInfo"], dict):
            gps_info = result["GPSInfo"]
            gps_dict = {}
            for gps_tag_id, gps_value in gps_info.items():
                gps_tag_name = GPSTAGS.get(gps_tag_id, str(gps_tag_id))
                gps_dict[gps_tag_name] = gps_value
            result["GPSInfo"] = gps_dict

        return result
    except Exception as e:
        logger.debug(f"No se pudo extraer EXIF: {e}")
        return {}


def _convert_gps_decimal(gps_info: dict) -> tuple | None:
    """Convierte coordenadas GPS a formato decimal para verificación."""
    try:
        lat_ref = gps_info.get("GPSLatitudeRef", "N")
        lon_ref = gps_info.get("GPSLongitudeRef", "E")
        lat = gps_info.get("GPSLatitude")
        lon = gps_info.get("GPSLongitude")

        if not lat or not lon:
            return None

        def to_decimal(coords, ref):
            degrees = coords[0]
            minutes = coords[1]
            seconds = coords[2]
            decimal = degrees + minutes / 60 + seconds / 3600
            if ref in ("S", "W"):
                decimal = -decimal
            return decimal

        return (to_decimal(lat, lat_ref), to_decimal(lon, lon_ref))
    except Exception:
        return None


def _format_value(value) -> str:
    """Formatea un valor EXIF para presentación."""
    if isinstance(value, (tuple, list)):
        parts = []
        for v in value:
            if hasattr(v, "numerator"):
                parts.append(str(v))
            else:
                parts.append(str(v))
        return ", ".join(parts)
    return str(value)


def check_image_exif(filename: str, image_data: bytes) -> list[ExifFinding]:
    """Revisa datos EXIF sensibles en una imagen individual."""
    findings = []
    ext = Path(filename).suffix.lower().lstrip(".")

    if ext not in IMAGE_EXTENSIONS:
        return findings

    exif_data = _extract_exif_data(image_data)
    if not exif_data:
        return findings

    for tag_name, value in exif_data.items():
        if tag_name in SENSITIVE_EXIF_FIELDS:
            is_high_risk = tag_name in HIGH_RISK_FIELDS
            finding = ExifFinding(
                filename=filename,
                field_name=tag_name,
                description=SENSITIVE_EXIF_FIELDS[tag_name],
                value=_format_value(value),
                is_high_risk=is_high_risk,
            )
            findings.append(finding)

    return findings


def check_zip_exif(
    zip_data: bytes, archive_name: str = "archivo.zip"
) -> ArchiveExifReport:
    """Revisa datos EXIF sensibles en imágenes dentro de un archivo ZIP."""
    report = ArchiveExifReport(archive_filename=archive_name)

    try:
        with zipfile.ZipFile(io.BytesIO(zip_data), "r") as zf:
            for file_info in zf.filelist:
                if file_info.is_dir():
                    continue

                file_ext = Path(file_info.filename).suffix.lower().lstrip(".")
                if file_ext not in IMAGE_EXTENSIONS:
                    continue

                try:
                    image_data = zf.read(file_info.filename)
                    report.files_checked += 1

                    findings = check_image_exif(file_info.filename, image_data)
                    if findings:
                        report.files_with_exif += 1
                        report.findings.extend(findings)

                        for f in findings:
                            if f.is_high_risk:
                                report.has_high_risk = True
                                report.has_sensitive_data = True
                            else:
                                report.has_sensitive_data = True

                except Exception as e:
                    logger.debug(f"Error al procesar {file_info.filename}: {e}")

    except zipfile.BadZipFile:
        logger.warning(f"Archivo ZIP inválido: {archive_name}")
    except Exception as e:
        logger.error(f"Error al revisar ZIP {archive_name}: {e}")

    return report


def check_archive_exif(
    file_data: bytes,
    filename: str,
    content_type: str | None = None,
) -> ArchiveExifReport:
    """Revisa datos EXIF sensibles en archivos comprimidos o imágenes individuales."""
    ext = Path(filename).suffix.lower().lstrip(".")

    if ext == "zip":
        return check_zip_exif(file_data, filename)

    if HAS_RUST and ext in IMAGE_EXTENSIONS:
        result = rust_check_exif(file_data, filename, content_type)
        findings = [
            ExifFinding(
                filename=f["filename"],
                field_name=f["field_name"],
                description=f["description"],
                value=f["value"],
                is_high_risk=f["is_high_risk"],
            )
            for f in result.get("findings", [])
        ]
        return ArchiveExifReport(
            archive_filename=result.get("archive_filename", filename),
            findings=findings,
            files_checked=result.get("files_checked", 0),
            files_with_exif=result.get("files_with_exif", 0),
            has_sensitive_data=result.get("has_sensitive_data", False),
            has_high_risk=result.get("has_high_risk", False),
        )

    return ArchiveExifReport(archive_filename=filename)
