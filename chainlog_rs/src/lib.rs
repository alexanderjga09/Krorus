use chrono::{SecondsFormat, Utc};
use pyo3::prelude::*;
use pyo3::types::{PyDict, PyList, PyString};
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use std::collections::HashMap;
use std::fs;
use std::path::PathBuf;
use std::sync::{Arc, Mutex};

// ---------- Estructura de bloque ----------
#[derive(Debug, Clone, Serialize, Deserialize)]
struct Block {
    index: usize,
    timestamp: String,
    data: serde_json::Value,
    previous_hash: String,
    hash: String,
    #[serde(rename = "block_type")]
    block_type: String,
}

// ---------- Estado interno ----------
struct ChainLogInner {
    chain: Vec<Block>,
}

#[pyclass]
struct ChainLog {
    filepath: PathBuf,
    inner: Arc<Mutex<ChainLogInner>>,
}

#[pymethods]
impl ChainLog {
    #[new]
    fn new(filepath: String) -> PyResult<Self> {
        let path = PathBuf::from(filepath);
        let chain = if path.exists() {
            let content = fs::read_to_string(&path).map_err(|e| {
                PyErr::new::<pyo3::exceptions::PyIOError, _>(format!(
                    "Failed to read chain file {}: {}",
                    path.display(),
                    e
                ))
            })?;
            if content.trim().is_empty() {
                Vec::new()
            } else {
                serde_json::from_str::<Vec<Block>>(&content).map_err(|e| {
                    PyErr::new::<pyo3::exceptions::PyValueError, _>(format!(
                        "Failed to parse chain file {}: {}",
                        path.display(),
                        e
                    ))
                })?
            }
        } else {
            Vec::new()
        };
        Ok(ChainLog {
            filepath: path,
            inner: Arc::new(Mutex::new(ChainLogInner { chain })),
        })
    }

    fn add_alert(
        &self,
        py: Python,
        user_id: String,
        code: String,
        reason: String,
        jump_url: String,
    ) -> PyResult<String> {
        let mut inner = self.inner.lock().map_err(|e| {
            PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(format!("Mutex lock error: {}", e))
        })?;
        let index = inner.chain.len();
        let previous_hash = inner
            .chain
            .last()
            .map(|b| b.hash.clone())
            .unwrap_or_else(|| "0".repeat(64));
        let timestamp = Utc::now().to_rfc3339_opts(SecondsFormat::Secs, true);
        let data_obj = serde_json::json!({
            "block_type": "alert",
            "user_id": user_id,
            "code": code,
            "reason": reason,
            "jump_url": jump_url,
        });
        let block_hash = self._hash_block_internal(index, &timestamp, &data_obj, &previous_hash);
        let block = Block {
            index,
            timestamp,
            data: data_obj,
            previous_hash,
            hash: block_hash.clone(),
            block_type: "alert".to_string(),
        };
        inner.chain.push(block);

        let chain_to_save = inner.chain.clone();
        drop(inner);

        self._save_chain(py, &chain_to_save)?;
        Ok(block_hash)
    }

    fn add_pardon(
        &self,
        py: Python,
        original_block_index: usize,
        moderator_id: String,
        reason: String,
    ) -> PyResult<Option<String>> {
        let mut inner = self.inner.lock().map_err(|e| {
            PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(format!("Mutex lock error: {}", e))
        })?;
        if original_block_index >= inner.chain.len() {
            return Ok(None);
        }
        if inner.chain[original_block_index].block_type != "alert" {
            return Ok(None);
        }
        if self._is_pardoned_locked(&inner, original_block_index) {
            return Ok(None);
        }
        let index = inner.chain.len();
        let previous_hash = inner
            .chain
            .last()
            .map(|b| b.hash.clone())
            .unwrap_or_else(|| "0".repeat(64));
        let timestamp = Utc::now().to_rfc3339_opts(SecondsFormat::Secs, true);
        let data_obj = serde_json::json!({
            "block_type": "pardon",
            "original_index": original_block_index,
            "moderator_id": moderator_id,
            "reason": reason,
        });
        let block_hash = self._hash_block_internal(index, &timestamp, &data_obj, &previous_hash);
        let block = Block {
            index,
            timestamp,
            data: data_obj,
            previous_hash,
            hash: block_hash.clone(),
            block_type: "pardon".to_string(),
        };
        inner.chain.push(block);

        let chain_to_save = inner.chain.clone();
        drop(inner);

        self._save_chain(py, &chain_to_save)?;
        Ok(Some(block_hash))
    }

    fn is_pardoned(&self, block_index: usize) -> PyResult<bool> {
        let inner = self.inner.lock().map_err(|e| {
            PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(format!("Mutex lock error: {}", e))
        })?;
        Ok(self._is_pardoned_locked(&inner, block_index))
    }

    fn get_pardon_info(&self, py: Python, block_index: usize) -> PyResult<Option<PyObject>> {
        let inner = self.inner.lock().map_err(|e| {
            PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(format!("Mutex lock error: {}", e))
        })?;
        for block in &inner.chain {
            if block.block_type == "pardon" {
                let is_match = block
                    .data
                    .get("original_index")
                    .and_then(|v| v.as_u64())
                    .map_or(false, |orig| orig == block_index as u64);

                if is_match {
                    let dict = PyDict::new_bound(py);
                    dict.set_item("index", block.index)?;
                    dict.set_item("timestamp", &block.timestamp)?;

                    for field in ["moderator_id", "reason"] {
                        if let Some(val) = block.data.get(field).and_then(|v| v.as_str()) {
                            dict.set_item(field, val)?;
                        }
                    }
                    return Ok(Some(dict.into()));
                }
            }
        }
        Ok(None)
    }

    fn get_active_alerts(&self, py: Python) -> PyResult<PyObject> {
        let inner = self.inner.lock().map_err(|e| {
            PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(format!("Mutex lock error: {}", e))
        })?;
        let list = PyList::empty_bound(py);
        for (i, block) in inner.chain.iter().enumerate() {
            if block.block_type == "alert" && !self._is_pardoned_locked(&inner, i) {
                let dict = PyDict::new_bound(py);
                dict.set_item("index", block.index)?;
                dict.set_item("timestamp", &block.timestamp)?;
                dict.set_item("data", block_to_py_dict(py, &block.data)?)?;
                dict.set_item("previous_hash", &block.previous_hash)?;
                dict.set_item("hash", &block.hash)?;
                dict.set_item("block_type", &block.block_type)?;
                list.append(dict)?;
            }
        }
        Ok(list.into())
    }

    fn verify_chain(&self) -> PyResult<bool> {
        let inner = self.inner.lock().map_err(|e| {
            PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(format!("Mutex lock error: {}", e))
        })?;
        for (i, block) in inner.chain.iter().enumerate() {
            if block.index != i {
                return Ok(false);
            }
            let expected_prev_hash = if i > 0 {
                inner.chain[i - 1].hash.as_str()
            } else {
                "0000000000000000000000000000000000000000000000000000000000000000"
            };

            if block.previous_hash != expected_prev_hash {
                return Ok(false);
            }
            let expected = self._hash_block_internal(
                block.index,
                &block.timestamp,
                &block.data,
                &block.previous_hash,
            );
            if block.hash != expected {
                return Ok(false);
            }
        }
        Ok(true)
    }

    fn last_hash(&self) -> PyResult<Option<String>> {
        let inner = self.inner.lock().map_err(|e| {
            PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(format!("Mutex lock error: {}", e))
        })?;
        Ok(inner.chain.last().map(|b| b.hash.clone()))
    }

    #[pyo3(signature = (include_pardoned=false))]
    fn get_alerts_by_user(&self, py: Python, include_pardoned: bool) -> PyResult<PyObject> {
        let inner = self.inner.lock().map_err(|e| {
            PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(format!("Mutex lock error: {}", e))
        })?;
        let mut result: HashMap<String, Vec<PyObject>> = HashMap::new();
        for (i, block) in inner.chain.iter().enumerate() {
            if block.block_type != "alert" {
                continue;
            }
            if !include_pardoned && self._is_pardoned_locked(&inner, i) {
                continue;
            }
            let user_id = match block.data.get("user_id").and_then(|v| v.as_str()) {
                Some(uid) => uid.to_string(),
                None => continue,
            };
            let dict = PyDict::new_bound(py);
            dict.set_item("index", block.index)?;
            dict.set_item("timestamp", &block.timestamp)?;
            dict.set_item("data", block_to_py_dict(py, &block.data)?)?;
            dict.set_item("previous_hash", &block.previous_hash)?;
            dict.set_item("hash", &block.hash)?;
            dict.set_item("block_type", &block.block_type)?;
            result.entry(user_id).or_default().push(dict.into());
        }
        let out_dict = PyDict::new_bound(py);
        for (uid, blocks) in result {
            let list = PyList::new_bound(py, blocks);
            out_dict.set_item(uid, list)?;
        }
        Ok(out_dict.into())
    }

    fn list_users(&self, py: Python) -> PyResult<PyObject> {
        let alerts_by_user_py = self.get_alerts_by_user(py, false)?;
        let alerts_dict = alerts_by_user_py.bind(py).downcast::<PyDict>()?;
        let out_list = PyList::empty_bound(py);
        for (key, value) in alerts_dict.iter() {
            let user_id = key.to_string();
            let blocks = value.downcast::<PyList>()?;
            let count = blocks.len();
            let tuple = (user_id, count);
            out_list.append(tuple)?;
        }
        Ok(out_list.into())
    }

    #[pyo3(signature = (user_id, include_pardoned=false))]
    fn get_user_alerts(
        &self,
        py: Python,
        user_id: String,
        include_pardoned: bool,
    ) -> PyResult<PyObject> {
        let alerts_by_user_py = self.get_alerts_by_user(py, include_pardoned)?;
        let alerts_dict = alerts_by_user_py.bind(py).downcast::<PyDict>()?;
        let key = PyString::new_bound(py, &user_id);
        match alerts_dict.get_item(key)? {
            Some(blocks) => Ok(blocks.into()),
            None => Ok(PyList::empty_bound(py).into()),
        }
    }

    #[pyo3(signature = (code, only_active=true))]
    fn find_alert_index_by_code(&self, code: String, only_active: bool) -> PyResult<Option<usize>> {
        let inner = self.inner.lock().map_err(|e| {
            PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(format!("Mutex lock error: {}", e))
        })?;
        for (i, block) in inner.chain.iter().enumerate() {
            if block.block_type != "alert" {
                continue;
            }
            if let Some(c) = block.data.get("code").and_then(|v| v.as_str()) {
                if c == code {
                    if only_active && self._is_pardoned_locked(&inner, i) {
                        continue;
                    }
                    return Ok(Some(i));
                }
            }
        }
        Ok(None)
    }

    fn __len__(&self) -> PyResult<usize> {
        let inner = self.inner.lock().map_err(|e| {
            PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(format!("Mutex lock error: {}", e))
        })?;
        Ok(inner.chain.len())
    }
}

// Internal helpers
impl ChainLog {
    fn _is_pardoned_locked(&self, inner: &ChainLogInner, block_index: usize) -> bool {
        inner.chain.iter().any(|block| {
            block.block_type == "pardon"
                && block
                    .data
                    .get("original_index")
                    .and_then(|v| v.as_u64())
                    .map_or(false, |orig| orig == block_index as u64)
        })
    }

    fn _hash_block_internal(
        &self,
        index: usize,
        timestamp: &str,
        data: &serde_json::Value,
        previous_hash: &str,
    ) -> String {
        let block_obj = serde_json::json!({
            "index": index,
            "timestamp": timestamp,
            "data": data,
            "previous_hash": previous_hash,
        });
        let block_str = serde_json::to_string(&block_obj).unwrap();
        let mut hasher = Sha256::new();
        hasher.update(block_str.as_bytes());
        format!("{:x}", hasher.finalize())
    }

    fn _save_chain(&self, py: Python, chain: &[Block]) -> PyResult<()> {
        let json = serde_json::to_string_pretty(chain).map_err(|e| {
            PyErr::new::<pyo3::exceptions::PyValueError, _>(format!("Serialization error: {}", e))
        })?;
        let filepath = self.filepath.clone();
        py.allow_threads(|| {
            fs::write(filepath, json).map_err(|e| {
                PyErr::new::<pyo3::exceptions::PyIOError, _>(format!("Write error: {}", e))
            })
        })?;
        Ok(())
    }
}

// ---------- Funciones auxiliares para convertir JSON a PyObject ----------
fn block_to_py_dict(py: Python, value: &serde_json::Value) -> PyResult<PyObject> {
    match value {
        serde_json::Value::Object(map) => {
            let dict = PyDict::new_bound(py);
            for (k, v) in map {
                dict.set_item(k, json_value_to_py(py, v)?)?;
            }
            Ok(dict.into())
        }
        _ => Ok(py.None()),
    }
}

fn json_value_to_py(py: Python, value: &serde_json::Value) -> PyResult<PyObject> {
    use serde_json::Value;
    match value {
        Value::Null => Ok(py.None()),
        Value::Bool(b) => Ok(b.to_object(py)),
        Value::Number(n) => {
            if let Some(i) = n.as_i64() {
                Ok(i.to_object(py))
            } else if let Some(f) = n.as_f64() {
                Ok(f.to_object(py))
            } else {
                Ok(py.None())
            }
        }
        Value::String(s) => Ok(s.to_object(py)),
        Value::Array(arr) => {
            let list = PyList::empty_bound(py);
            for item in arr {
                list.append(json_value_to_py(py, item)?)?;
            }
            Ok(list.into())
        }
        Value::Object(map) => {
            let dict = PyDict::new_bound(py);
            for (k, v) in map {
                dict.set_item(k, json_value_to_py(py, v)?)?;
            }
            Ok(dict.into())
        }
    }
}

#[pymodule]
fn chainlog_rs(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_class::<ChainLog>()?;
    Ok(())
}
