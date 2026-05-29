use pyo3::prelude::*;
use pyo3::types::{PyDict, PyList};
use std::io::Cursor;

const IMAGE_EXTENSIONS: &[&str] = &["jpg", "jpeg", "tif", "tiff", "webp"];

const SENSITIVE_EXIF_FIELDS: &[(&str, &str)] = &[
    ("GPSInfo", "Información GPS detectada"),
    ("GPSLatitude", "Latitud GPS encontrada"),
    ("GPSLongitude", "Longitud GPS encontrada"),
    ("GPSLatitudeRef", "Referencia de latitud GPS"),
    ("GPSLongitudeRef", "Referencia de longitud GPS"),
    ("GPSAltitude", "Altitud GPS encontrada"),
    ("GPSAltitudeRef", "Referencia de altitud GPS"),
    ("GPSMapDatum", "Datum de mapa GPS"),
    ("GPSTimeStamp", "Marca de tiempo GPS"),
    ("GPSDateStamp", "Marca de fecha GPS"),
    ("MakerNote", "Notas del fabricante (puede contener serial)"),
    ("UserComment", "Comentario del usuario"),
    ("ImageDescription", "Descripción de la imagen"),
    ("Artist", "Artista/Autor"),
    ("Copyright", "Copyright"),
    ("Software", "Software utilizado"),
    ("DateTime", "Fecha y hora de captura"),
    ("DateTimeOriginal", "Fecha y hora original"),
    ("DateTimeDigitized", "Fecha y hora de digitalización"),
    ("CameraSerialNumber", "Número de serie de cámara"),
    ("SerialNumber", "Número de serie"),
    ("LensSerialNumber", "Número de serie del lente"),
    ("BodySerialNumber", "Número de serie del cuerpo"),
    ("LensModel", "Modelo del lente"),
    ("Make", "Fabricante de cámara"),
    ("Model", "Modelo de cámara"),
    ("LensInfo", "Información del lente"),
    ("OwnerName", "Nombre del propietario"),
];

const HIGH_RISK_FIELDS: &[&str] = &[
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
    "OwnerName",
];

#[derive(Debug, Clone)]
struct ExifFinding {
    filename: String,
    field_name: String,
    description: String,
    value: String,
    is_high_risk: bool,
}

#[derive(Debug, Clone)]
struct ImageExifReport {
    filename: String,
    findings: Vec<ExifFinding>,
    has_sensitive_data: bool,
    has_high_risk: bool,
}

impl ImageExifReport {
    fn to_py_dict(&self, py: Python) -> PyResult<PyObject> {
        let dict = PyDict::new_bound(py);
        dict.set_item("archive_filename", &self.filename)?;
        dict.set_item("files_checked", 1)?;
        dict.set_item("files_with_exif", if self.findings.is_empty() { 0 } else { 1 })?;
        dict.set_item("has_sensitive_data", self.has_sensitive_data)?;
        dict.set_item("has_high_risk", self.has_high_risk)?;

        let findings_list = PyList::empty_bound(py);
        for finding in &self.findings {
            let finding_dict = PyDict::new_bound(py);
            finding_dict.set_item("filename", &finding.filename)?;
            finding_dict.set_item("field_name", &finding.field_name)?;
            finding_dict.set_item("description", &finding.description)?;
            finding_dict.set_item("value", &finding.value)?;
            finding_dict.set_item("is_high_risk", finding.is_high_risk)?;
            findings_list.append(finding_dict)?;
        }
        dict.set_item("findings", findings_list)?;

        Ok(dict.into())
    }
}

fn extract_exif_data(image_data: &[u8]) -> Vec<(String, String)> {
    let mut results = Vec::new();

    let mut cursor = Cursor::new(image_data);
    match exif::Reader::new().read_from_container(&mut cursor) {
        Ok(exif) => {
            for field in exif.fields() {
                let tag_name = field.tag.to_string();
                let value = field.display_value().to_string();
                results.push((tag_name, value));
            }
        }
        Err(_) => {}
    }
    results
}

#[pyfunction(signature = (file_data, filename, _content_type=None))]
fn check_archive_exif(file_data: &[u8], filename: &str, _content_type: Option<&str>) -> PyResult<PyObject> {
    let ext = filename.rsplit('.').next().unwrap_or("").to_lowercase();

    if !IMAGE_EXTENSIONS.contains(&ext.as_str()) {
        return Python::with_gil(|py| {
            let dict = PyDict::new_bound(py);
            dict.set_item("archive_filename", filename)?;
            dict.set_item("files_checked", 0)?;
            dict.set_item("files_with_exif", 0)?;
            dict.set_item("has_sensitive_data", false)?;
            dict.set_item("has_high_risk", false)?;
            dict.set_item("findings", PyList::empty_bound(py))?;
            Ok(dict.into())
        });
    }

    let exif_data = extract_exif_data(file_data);
    let mut findings = Vec::new();
    let mut has_high_risk = false;
    let mut has_sensitive = false;

    for (tag_name, value) in exif_data {
        if let Some((_, desc)) = SENSITIVE_EXIF_FIELDS.iter().find(|(k, _)| *k == tag_name) {
            let is_high_risk = HIGH_RISK_FIELDS.iter().any(|f| *f == tag_name);
            if is_high_risk {
                has_high_risk = true;
            }
            has_sensitive = true;
            findings.push(ExifFinding {
                filename: filename.to_string(),
                field_name: tag_name.clone(),
                description: desc.to_string(),
                value: value.clone(),
                is_high_risk,
            });
        }
    }

    let report = ImageExifReport {
        filename: filename.to_string(),
        findings,
        has_sensitive_data: has_sensitive,
        has_high_risk,
    };

    Python::with_gil(|py| report.to_py_dict(py))
}

#[pymodule]
fn exif_rs(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(check_archive_exif, m)?)?;
    Ok(())
}