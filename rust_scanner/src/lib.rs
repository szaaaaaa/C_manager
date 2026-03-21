mod mft_reader;
mod models;

use pyo3::prelude::*;
use pyo3::types::PyDict;

/// Scan NTFS MFT and return the top largest files.
///
/// Args:
///     volume: Volume path, e.g. "\\\\.\\C:"
///     min_size_bytes: Minimum file size in bytes to include
///     top_n: Maximum number of results to return
///
/// Returns:
///     List of dicts with keys: path, name, size, is_dir
#[pyfunction]
#[pyo3(signature = (volume = "\\\\.\\C:", min_size_bytes = 10485760, top_n = 200))]
fn scan_mft(
    py: Python<'_>,
    volume: &str,
    min_size_bytes: u64,
    top_n: usize,
) -> PyResult<Vec<Py<PyDict>>> {
    let records = mft_reader::scan_mft(volume, min_size_bytes, top_n)
        .map_err(|e| pyo3::exceptions::PyRuntimeError::new_err(e))?;

    let mut results = Vec::with_capacity(records.len());
    for rec in records {
        let dict = PyDict::new(py);
        let file_name = rec
            .name
            .rsplit('\\')
            .next()
            .unwrap_or(&rec.name)
            .to_string();
        dict.set_item("path", &rec.name)?;
        dict.set_item("name", file_name)?;
        dict.set_item("size", rec.size)?;
        dict.set_item("is_dir", false)?;
        results.push(dict.into());
    }

    Ok(results)
}

/// Python module definition.
#[pymodule]
fn rust_scanner(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(scan_mft, m)?)?;
    Ok(())
}
