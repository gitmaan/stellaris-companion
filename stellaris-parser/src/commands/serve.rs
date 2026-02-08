//! Session mode server for the Stellaris parser.
//!
//! Loads and parses a save file once, then responds to JSON requests via stdin/stdout.
//! This eliminates re-parsing overhead when making multiple queries against the same save.

use crate::error::{ErrorKind, SCHEMA_VERSION, TOOL_VERSION};
use aho_corasick::AhoCorasick;
use anyhow::{Context, Result};
use jomini::text::de::from_windows1252_slice;
use serde::{Deserialize, Serialize};
use serde_json::{json, Map, Value};
use std::collections::HashMap;
use std::io::{self, BufRead, Write};

/// Request types for session mode
#[derive(Debug, Deserialize)]
#[serde(tag = "op", rename_all = "snake_case")]
enum Request {
    ExtractSections {
        sections: Vec<String>,
    },
    IterSection {
        section: String,
        #[serde(default = "default_batch_size")]
        batch_size: usize,
    },
    GetEntry {
        section: String,
        key: String,
    },
    GetEntries {
        section: String,
        keys: Vec<String>,
        #[serde(default)]
        fields: Option<Vec<String>>,
    },
    CountKeys {
        keys: Vec<String>,
    },
    ContainsTokens {
        tokens: Vec<String>,
    },
    ContainsKv {
        pairs: Vec<(String, String)>,
    },
    GetCountrySummaries {
        fields: Vec<String>,
    },
    GetDuplicateValues {
        section: String,
        key: String,
        field: String,
    },
    /// Get raw Clausewitz text for a single entry (for duplicate-key parsing in Python)
    GetEntryText {
        section: String,
        key: String,
    },
    /// Batch multiple operations in a single request to reduce IPC overhead
    Multi {
        ops: Vec<MultiOp>,
    },
    Close,
}

/// Operations that can be batched in a multi-op request.
/// Note: IterSection and Close are excluded as they have special handling requirements.
#[derive(Debug, Deserialize)]
#[serde(tag = "op", rename_all = "snake_case")]
enum MultiOp {
    ExtractSections {
        sections: Vec<String>,
    },
    GetEntry {
        section: String,
        key: String,
    },
    GetEntries {
        section: String,
        keys: Vec<String>,
        #[serde(default)]
        fields: Option<Vec<String>>,
    },
    CountKeys {
        keys: Vec<String>,
    },
    ContainsTokens {
        tokens: Vec<String>,
    },
    ContainsKv {
        pairs: Vec<(String, String)>,
    },
    GetCountrySummaries {
        fields: Vec<String>,
    },
    GetDuplicateValues {
        section: String,
        key: String,
        field: String,
    },
    GetEntryText {
        section: String,
        key: String,
    },
}

/// Default batch size for iter_section (100 entries per message)
fn default_batch_size() -> usize {
    100
}

/// Successful response wrapper
#[derive(Debug, Serialize)]
struct SuccessResponse {
    ok: bool,
    #[serde(flatten)]
    data: ResponseData,
}

/// Response data variants
#[derive(Debug, Serialize)]
#[serde(untagged)]
#[allow(dead_code)] // Some variants reserved for future streaming modes
enum ResponseData {
    Extract {
        data: Value,
    },
    SingleEntry {
        entry: Value,
        found: bool,
    },
    MultipleEntries {
        entries: Vec<Value>,
    },
    StreamHeader {
        stream: bool,
        op: String,
        section: String,
    },
    StreamEntry {
        entry: EntryData,
    },
    StreamBatch {
        entries: Vec<EntryData>,
    },
    StreamDone {
        done: bool,
        op: String,
        section: String,
    },
    Closed {
        closed: bool,
    },
    KeyCounts {
        counts: HashMap<String, usize>,
    },
    TokenMatches {
        matches: HashMap<String, bool>,
    },
    KvMatches {
        matches: HashMap<String, bool>,
    },
    CountrySummaries {
        countries: Vec<Value>,
    },
    DuplicateValues {
        values: Vec<String>,
        found: bool,
    },
    /// Raw Clausewitz text for a single entry
    EntryText {
        text: String,
        found: bool,
    },
    /// Results from a multi-op batch request
    MultiResults {
        results: Vec<Value>,
    },
}

#[derive(Debug, Serialize)]
struct EntryData {
    key: String,
    value: Value,
}

/// Error response matching the ParserError contract
#[derive(Debug, Serialize)]
struct ErrorResponse {
    ok: bool,
    error: String,
    message: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    line: Option<u32>,
    #[serde(skip_serializing_if = "Option::is_none")]
    col: Option<u32>,
    exit_code: i32,
    schema_version: u32,
    tool_version: &'static str,
    game: &'static str,
}

impl ErrorResponse {
    fn new(error: &str, message: &str, exit_code: i32) -> Self {
        Self {
            ok: false,
            error: error.to_string(),
            message: message.to_string(),
            line: None,
            col: None,
            exit_code,
            schema_version: SCHEMA_VERSION,
            tool_version: TOOL_VERSION,
            game: "stellaris",
        }
    }
}

/// Parsed save data held in memory for the session
struct ParsedSave {
    gamestate: HashMap<String, Value>,
    gamestate_bytes: Vec<u8>, // Keep for token scanning with Aho-Corasick
    meta: Option<HashMap<String, Value>>,
}

impl ParsedSave {
    /// Load and parse a .sav file
    fn load(path: &str) -> Result<Self> {
        let (gamestate_bytes, meta_bytes) = crate::commands::extract::read_sav_file(path)?;

        let gamestate: HashMap<String, Value> = from_windows1252_slice(&gamestate_bytes)
            .with_context(|| "Failed to parse gamestate")?;

        let meta = if let Some(meta_bytes) = meta_bytes {
            Some(from_windows1252_slice(&meta_bytes).with_context(|| "Failed to parse meta file")?)
        } else {
            None
        };

        Ok(Self {
            gamestate,
            gamestate_bytes,
            meta,
        })
    }

    /// Extract specific sections from the parsed data
    fn extract_sections(&self, sections: &[String]) -> Value {
        let mut result = Map::new();
        result.insert("schema_version".to_string(), json!(SCHEMA_VERSION));
        result.insert("tool_version".to_string(), json!(TOOL_VERSION));
        result.insert("game".to_string(), json!("stellaris"));

        for section in sections {
            if section == "meta" {
                if let Some(ref meta) = self.meta {
                    result.insert("meta".to_string(), json!(meta));
                }
            } else if let Some(value) = self.gamestate.get(section) {
                result.insert(section.clone(), value.clone());
            }
        }

        Value::Object(result)
    }
}

/// Write a JSON line to stdout (protocol output)
fn write_response<T: Serialize>(response: &T) -> io::Result<()> {
    let mut stdout = io::stdout().lock();
    serde_json::to_writer(&mut stdout, response)?;
    stdout.write_all(b"\n")?;
    stdout.flush()?;
    Ok(())
}

/// Write a stream entry directly without cloning the value.
/// This avoids expensive deep clones of large Value trees.
fn write_stream_entry(key: &str, value: &Value) -> io::Result<()> {
    let mut stdout = io::stdout().lock();
    // Write the JSON structure directly, serializing value in place
    write!(stdout, r#"{{"ok":true,"entry":{{"key":"{}","value":"#, key)?;
    serde_json::to_writer(&mut stdout, value)?;
    stdout.write_all(b"}}\n")?;
    stdout.flush()?;
    Ok(())
}

/// Write a batch of stream entries directly without cloning.
/// Each entry's value is serialized in place to avoid deep clones.
fn write_stream_batch(entries: &[(&str, &Value)]) -> io::Result<()> {
    let mut stdout = io::stdout().lock();
    // Build JSON: {"ok":true,"entries":[{"key":"...","value":...},...]}
    stdout.write_all(b"{\"ok\":true,\"entries\":[")?;
    for (i, (key, value)) in entries.iter().enumerate() {
        if i > 0 {
            stdout.write_all(b",")?;
        }
        write!(stdout, r#"{{"key":"{}","value":"#, key)?;
        serde_json::to_writer(&mut stdout, value)?;
        stdout.write_all(b"}")?;
    }
    stdout.write_all(b"]}\n")?;
    stdout.flush()?;
    Ok(())
}

/// Write an error response
fn write_error(error: &str, message: &str, exit_code: i32) -> io::Result<()> {
    write_response(&ErrorResponse::new(error, message, exit_code))
}

/// Handle extract_sections operation
fn handle_extract_sections(parsed: &ParsedSave, sections: Vec<String>) -> io::Result<()> {
    let data = parsed.extract_sections(&sections);
    write_response(&SuccessResponse {
        ok: true,
        data: ResponseData::Extract { data },
    })
}

/// Handle iter_section operation (streaming)
fn handle_iter_section(parsed: &ParsedSave, section: String, batch_size: usize) -> io::Result<()> {
    // Write stream header
    write_response(&SuccessResponse {
        ok: true,
        data: ResponseData::StreamHeader {
            stream: true,
            op: "iter_section".to_string(),
            section: section.clone(),
        },
    })?;

    // Get section and iterate
    if let Some(Value::Object(map)) = parsed.gamestate.get(&section) {
        if batch_size <= 1 {
            // Single-entry mode (backward compatible)
            for (key, value) in map {
                write_stream_entry(key, value)?;
            }
        } else {
            // Batched mode - collect entries and write in batches
            let mut batch: Vec<(&str, &Value)> = Vec::with_capacity(batch_size);
            for (key, value) in map {
                batch.push((key.as_str(), value));
                if batch.len() >= batch_size {
                    write_stream_batch(&batch)?;
                    batch.clear();
                }
            }
            // Write remaining entries
            if !batch.is_empty() {
                write_stream_batch(&batch)?;
            }
        }
    }

    // Write done marker
    write_response(&SuccessResponse {
        ok: true,
        data: ResponseData::StreamDone {
            done: true,
            op: "iter_section".to_string(),
            section,
        },
    })
}

/// Handle get_entry operation - fetch a single entry by section and key
fn handle_get_entry(parsed: &ParsedSave, section: String, key: String) -> io::Result<()> {
    // Get the section from gamestate
    if let Some(Value::Object(map)) = parsed.gamestate.get(&section) {
        if let Some(entry_value) = map.get(&key) {
            return write_response(&SuccessResponse {
                ok: true,
                data: ResponseData::SingleEntry {
                    entry: entry_value.clone(),
                    found: true,
                },
            });
        }
    }

    // Entry not found - return null with found=false
    write_response(&SuccessResponse {
        ok: true,
        data: ResponseData::SingleEntry {
            entry: Value::Null,
            found: false,
        },
    })
}

/// Handle get_entries operation - batch fetch multiple entries by keys with optional field projection
fn handle_get_entries(
    parsed: &ParsedSave,
    section: String,
    keys: Vec<String>,
    fields: Option<Vec<String>>,
) -> io::Result<()> {
    let mut entries: Vec<Value> = Vec::new();

    // Get the section from gamestate
    if let Some(Value::Object(map)) = parsed.gamestate.get(&section) {
        for key in &keys {
            if let Some(entry_value) = map.get(key) {
                // Apply field projection if specified
                let projected = if let Some(ref field_list) = fields {
                    if let Value::Object(entry_obj) = entry_value {
                        let mut projected_obj = Map::new();
                        projected_obj.insert("_key".to_string(), json!(key));
                        for field in field_list {
                            if let Some(field_value) = entry_obj.get(field) {
                                projected_obj.insert(field.clone(), field_value.clone());
                            }
                        }
                        Value::Object(projected_obj)
                    } else {
                        // Non-object entry (e.g., "none"), include as-is with key
                        let mut obj = Map::new();
                        obj.insert("_key".to_string(), json!(key));
                        obj.insert("_value".to_string(), entry_value.clone());
                        Value::Object(obj)
                    }
                } else {
                    // No projection - include full entry with key
                    let mut obj = Map::new();
                    obj.insert("_key".to_string(), json!(key));
                    obj.insert("_value".to_string(), entry_value.clone());
                    Value::Object(obj)
                };
                entries.push(projected);
            }
            // Note: keys that don't exist are silently skipped
        }
    }

    write_response(&SuccessResponse {
        ok: true,
        data: ResponseData::MultipleEntries { entries },
    })
}

/// Handle count_keys operation - traverse tree and count occurrences of specified keys
fn handle_count_keys(parsed: &ParsedSave, keys: Vec<String>) -> io::Result<()> {
    use std::collections::HashSet;

    let key_set: HashSet<&str> = keys.iter().map(|s| s.as_str()).collect();
    let mut counts: HashMap<String, usize> = keys.iter().map(|k| (k.clone(), 0)).collect();

    /// Recursively traverse a Value tree and count key occurrences
    fn traverse(value: &Value, key_set: &HashSet<&str>, counts: &mut HashMap<String, usize>) {
        match value {
            Value::Object(map) => {
                for (k, v) in map {
                    if key_set.contains(k.as_str()) {
                        *counts.get_mut(k.as_str()).unwrap() += 1;
                    }
                    traverse(v, key_set, counts);
                }
            }
            Value::Array(arr) => {
                for v in arr {
                    traverse(v, key_set, counts);
                }
            }
            _ => {}
        }
    }

    // Traverse all sections in the gamestate
    for section in parsed.gamestate.values() {
        traverse(section, &key_set, &mut counts);
    }

    write_response(&SuccessResponse {
        ok: true,
        data: ResponseData::KeyCounts { counts },
    })
}

/// Handle contains_tokens operation - Aho-Corasick scan for token presence
fn handle_contains_tokens(gamestate_bytes: &[u8], tokens: Vec<String>) -> io::Result<()> {
    let mut matches: HashMap<String, bool> = tokens.iter().map(|t| (t.clone(), false)).collect();

    if !tokens.is_empty() {
        let ac = AhoCorasick::new(&tokens).expect("Failed to build Aho-Corasick automaton");

        for mat in ac.find_iter(gamestate_bytes) {
            let pattern_idx = mat.pattern().as_usize();
            if pattern_idx < tokens.len() {
                matches.insert(tokens[pattern_idx].clone(), true);
            }
        }
    }

    write_response(&SuccessResponse {
        ok: true,
        data: ResponseData::TokenMatches { matches },
    })
}

/// Handle contains_kv operation - whitespace-insensitive key=value check in parsed tree
/// This traverses the JSON tree looking for keys with matching values, handling
/// both `key=value` and `key = value` formatting variations that regex struggles with.
fn handle_contains_kv(parsed: &ParsedSave, pairs: Vec<(String, String)>) -> io::Result<()> {
    use std::collections::HashSet;

    // Build a lookup structure: key -> set of values we're looking for
    let mut key_to_values: HashMap<String, HashSet<String>> = HashMap::new();
    for (key, value) in &pairs {
        key_to_values
            .entry(key.clone())
            .or_default()
            .insert(value.clone());
    }

    // Track which pairs we've found (using "key=value" as the result key)
    let mut matches: HashMap<String, bool> = pairs
        .iter()
        .map(|(k, v)| (format!("{}={}", k, v), false))
        .collect();

    /// Recursively traverse a Value tree and check for key=value matches
    fn traverse(
        value: &Value,
        key_to_values: &HashMap<String, HashSet<String>>,
        matches: &mut HashMap<String, bool>,
    ) {
        match value {
            Value::Object(map) => {
                for (k, v) in map {
                    // Check if this key is one we're looking for
                    if let Some(target_values) = key_to_values.get(k.as_str()) {
                        // Check if the value matches any of our targets
                        let value_str = match v {
                            Value::String(s) => Some(s.as_str()),
                            Value::Number(_) => None, // Will handle below
                            Value::Bool(b) => {
                                if *b {
                                    Some("yes")
                                } else {
                                    Some("no")
                                }
                            }
                            _ => None,
                        };

                        if let Some(vs) = value_str {
                            if target_values.contains(vs) {
                                matches.insert(format!("{}={}", k, vs), true);
                            }
                        }

                        // Handle numbers - compare as string
                        if let Value::Number(n) = v {
                            let num_str = n.to_string();
                            if target_values.contains(&num_str) {
                                matches.insert(format!("{}={}", k, num_str), true);
                            }
                        }
                    }
                    // Recurse into the value
                    traverse(v, key_to_values, matches);
                }
            }
            Value::Array(arr) => {
                for v in arr {
                    traverse(v, key_to_values, matches);
                }
            }
            _ => {}
        }
    }

    // Traverse all sections in the gamestate
    for section in parsed.gamestate.values() {
        traverse(section, &key_to_values, &mut matches);
    }

    write_response(&SuccessResponse {
        ok: true,
        data: ResponseData::KvMatches { matches },
    })
}

/// Handle get_country_summaries operation - return lightweight country projections
fn handle_get_country_summaries(parsed: &ParsedSave, fields: Vec<String>) -> io::Result<()> {
    let mut countries: Vec<Value> = Vec::new();

    // Get the country section from gamestate
    if let Some(Value::Object(country_map)) = parsed.gamestate.get("country") {
        for (country_id, country_data) in country_map {
            let mut summary = Map::new();
            summary.insert("id".to_string(), json!(country_id));

            // Extract only the requested fields
            if let Value::Object(country_obj) = country_data {
                for field in &fields {
                    if let Some(value) = country_obj.get(field) {
                        summary.insert(field.clone(), value.clone());
                    }
                }
            }

            countries.push(Value::Object(summary));
        }
    }

    write_response(&SuccessResponse {
        ok: true,
        data: ResponseData::CountrySummaries { countries },
    })
}

/// Handle get_duplicate_values operation - extract all values for a field with duplicate keys
///
/// This is needed because jomini's JSON-style deserialization collapses duplicate keys,
/// but Stellaris save files use duplicate keys for list-like structures (e.g., traits="x"
/// appearing multiple times for a leader).
///
/// This function scans the raw gamestate bytes to find the entry and extracts all values
/// for the specified field using byte-level parsing.
fn handle_get_duplicate_values(
    gamestate_bytes: &[u8],
    section: String,
    key: String,
    field: String,
) -> io::Result<()> {
    // Strategy:
    // 1. Find the section start (e.g., "leaders={")
    // 2. Find the specific entry by key (e.g., "\n\t12345=")
    // 3. Extract all values for the field (e.g., traits="value")

    let mut values: Vec<String> = Vec::new();
    let mut found = false;

    // Convert to string for searching (save files are Windows-1252 encoded, mostly ASCII-compatible)
    let content = String::from_utf8_lossy(gamestate_bytes);

    // Find section start: section={
    let section_pattern = format!("\n{}=", section);
    if let Some(section_start) = content.find(&section_pattern) {
        // Find the opening brace
        let section_content_start = match content[section_start..].find('{') {
            Some(pos) => section_start + pos + 1,
            None => {
                return write_response(&SuccessResponse {
                    ok: true,
                    data: ResponseData::DuplicateValues {
                        values,
                        found: false,
                    },
                });
            }
        };

        // Look for the entry: \n\t<key>=
        // Note: keys at top level of section are tab-indented once
        let entry_patterns = [
            format!("\n\t{}=\n\t{{", key), // Standard format with newline before brace
            format!("\n\t{}={{", key),     // Compact format without newline
            format!("\n\t{} =", key),      // With space before equals
        ];

        let mut entry_start: Option<usize> = None;
        for pattern in &entry_patterns {
            if let Some(pos) = content[section_content_start..].find(pattern) {
                entry_start = Some(section_content_start + pos);
                break;
            }
        }

        if let Some(start) = entry_start {
            found = true;

            // Find the entry's content by counting braces
            let entry_content = &content[start..];
            let mut brace_count = 0;
            let mut entry_end = entry_content.len();
            let mut in_entry = false;

            for (i, ch) in entry_content.chars().enumerate() {
                if ch == '{' {
                    brace_count += 1;
                    in_entry = true;
                } else if ch == '}' {
                    brace_count -= 1;
                    if in_entry && brace_count == 0 {
                        entry_end = i + 1;
                        break;
                    }
                }
            }

            let entry_block = &entry_content[..entry_end];

            // Extract all values for the field: field="value"
            // Pattern: field="<value>"
            let field_pattern = format!("{}=\"", field);
            let mut search_pos = 0;

            while let Some(field_start) = entry_block[search_pos..].find(&field_pattern) {
                let value_start = search_pos + field_start + field_pattern.len();
                if let Some(value_end) = entry_block[value_start..].find('"') {
                    let value = &entry_block[value_start..value_start + value_end];
                    values.push(value.to_string());
                    search_pos = value_start + value_end + 1;
                } else {
                    break;
                }
            }
        }
    }

    write_response(&SuccessResponse {
        ok: true,
        data: ResponseData::DuplicateValues { values, found },
    })
}

/// Helper to extract duplicate values from raw bytes with optional cached section offset.
/// Returns (values, found, section_end_for_caching).
fn extract_duplicate_values(
    content: &str,
    section: &str,
    key: &str,
    field: &str,
    cached_section_start: Option<usize>,
) -> (Vec<String>, bool, Option<usize>) {
    let mut values: Vec<String> = Vec::new();

    // Find section start (use cache if available)
    let section_content_start = if let Some(start) = cached_section_start {
        start
    } else {
        let section_pattern = format!("\n{}=", section);
        if let Some(section_start) = content.find(&section_pattern) {
            match content[section_start..].find('{') {
                Some(pos) => section_start + pos + 1,
                None => return (values, false, None),
            }
        } else {
            return (values, false, None);
        }
    };

    // Look for the entry: \n\t<key>=
    let entry_patterns = [
        format!("\n\t{}=\n\t{{", key),
        format!("\n\t{}={{", key),
        format!("\n\t{} =", key),
    ];

    let mut entry_start: Option<usize> = None;
    for pattern in &entry_patterns {
        if let Some(pos) = content[section_content_start..].find(pattern) {
            entry_start = Some(section_content_start + pos);
            break;
        }
    }

    let Some(start) = entry_start else {
        return (values, false, Some(section_content_start));
    };

    // Find the entry's content by counting braces
    let entry_content = &content[start..];
    let mut brace_count = 0;
    let mut entry_end = entry_content.len();
    let mut in_entry = false;

    for (i, ch) in entry_content.chars().enumerate() {
        if ch == '{' {
            brace_count += 1;
            in_entry = true;
        } else if ch == '}' {
            brace_count -= 1;
            if in_entry && brace_count == 0 {
                entry_end = i + 1;
                break;
            }
        }
    }

    let entry_block = &entry_content[..entry_end];

    // Extract all values for the field: field="value"
    let field_pattern = format!("{}=\"", field);
    let mut search_pos = 0;

    while let Some(field_start) = entry_block[search_pos..].find(&field_pattern) {
        let value_start = search_pos + field_start + field_pattern.len();
        if let Some(value_end) = entry_block[value_start..].find('"') {
            let value = &entry_block[value_start..value_start + value_end];
            values.push(value.to_string());
            search_pos = value_start + value_end + 1;
        } else {
            break;
        }
    }

    (values, true, Some(section_content_start))
}

/// Handle get_entry_text operation - extract raw Clausewitz text for a single entry
///
/// This is needed for cases where Python needs to parse duplicate keys (like relation={})
/// that can't be represented in JSON. Instead of searching the entire gamestate in Python,
/// this returns just the entry's raw text for targeted regex parsing.
fn handle_get_entry_text(gamestate_bytes: &[u8], section: String, key: String) -> io::Result<()> {
    let content = String::from_utf8_lossy(gamestate_bytes);
    let (text, found) = extract_entry_text(&content, &section, &key, None);

    write_response(&SuccessResponse {
        ok: true,
        data: ResponseData::EntryText { text, found },
    })
}

/// Helper to extract raw entry text with optional cached section offset.
/// Returns (text, found, section_end_for_caching).
fn extract_entry_text(
    content: &str,
    section: &str,
    key: &str,
    cached_section_start: Option<usize>,
) -> (String, bool) {
    // Find section start (use cache if available)
    let section_content_start = if let Some(start) = cached_section_start {
        start
    } else {
        let section_pattern = format!("\n{}=", section);
        if let Some(section_start) = content.find(&section_pattern) {
            match content[section_start..].find('{') {
                Some(pos) => section_start + pos + 1,
                None => return (String::new(), false),
            }
        } else {
            return (String::new(), false);
        }
    };

    // Look for the entry: \n\t<key>=
    let entry_patterns = [
        format!("\n\t{}=\n\t{{", key),
        format!("\n\t{}={{", key),
        format!("\n\t{} =", key),
    ];

    let mut entry_start: Option<usize> = None;
    for pattern in &entry_patterns {
        if let Some(pos) = content[section_content_start..].find(pattern) {
            entry_start = Some(section_content_start + pos);
            break;
        }
    }

    let Some(start) = entry_start else {
        return (String::new(), false);
    };

    // Find the entry's content by counting braces
    let entry_content = &content[start..];
    let mut brace_count = 0;
    let mut entry_end = entry_content.len();
    let mut in_entry = false;

    for (i, ch) in entry_content.chars().enumerate() {
        if ch == '{' {
            brace_count += 1;
            in_entry = true;
        } else if ch == '}' {
            brace_count -= 1;
            if in_entry && brace_count == 0 {
                entry_end = i + 1;
                break;
            }
        }
    }

    let entry_block = &entry_content[..entry_end];
    (entry_block.to_string(), true)
}

/// Handle multi-op batch request - execute multiple operations in one request
/// to reduce IPC round-trip overhead.
///
/// Returns results in the same order as the input operations.
fn handle_multi_op(parsed: &ParsedSave, ops: Vec<MultiOp>) -> io::Result<()> {
    let mut results: Vec<Value> = Vec::with_capacity(ops.len());

    // Cache for section offsets in get_duplicate_values (section_name -> content_start_offset)
    let mut section_offset_cache: HashMap<String, usize> = HashMap::new();
    let content = String::from_utf8_lossy(&parsed.gamestate_bytes);

    for op in ops {
        let result = match op {
            MultiOp::ExtractSections { sections } => {
                let data = parsed.extract_sections(&sections);
                json!({ "data": data })
            }
            MultiOp::GetEntry { section, key } => {
                if let Some(Value::Object(map)) = parsed.gamestate.get(&section) {
                    if let Some(entry_value) = map.get(&key) {
                        json!({ "entry": entry_value, "found": true })
                    } else {
                        json!({ "entry": Value::Null, "found": false })
                    }
                } else {
                    json!({ "entry": Value::Null, "found": false })
                }
            }
            MultiOp::GetEntries {
                section,
                keys,
                fields,
            } => {
                let mut entries: Vec<Value> = Vec::new();
                if let Some(Value::Object(map)) = parsed.gamestate.get(&section) {
                    for key in &keys {
                        if let Some(entry_value) = map.get(key) {
                            let projected = if let Some(ref field_list) = fields {
                                if let Value::Object(entry_obj) = entry_value {
                                    let mut projected_obj = Map::new();
                                    projected_obj.insert("_key".to_string(), json!(key));
                                    for field in field_list {
                                        if let Some(field_value) = entry_obj.get(field) {
                                            projected_obj
                                                .insert(field.clone(), field_value.clone());
                                        }
                                    }
                                    Value::Object(projected_obj)
                                } else {
                                    let mut obj = Map::new();
                                    obj.insert("_key".to_string(), json!(key));
                                    obj.insert("_value".to_string(), entry_value.clone());
                                    Value::Object(obj)
                                }
                            } else {
                                let mut obj = Map::new();
                                obj.insert("_key".to_string(), json!(key));
                                obj.insert("_value".to_string(), entry_value.clone());
                                Value::Object(obj)
                            };
                            entries.push(projected);
                        }
                    }
                }
                json!({ "entries": entries })
            }
            MultiOp::CountKeys { keys } => {
                use std::collections::HashSet;
                let key_set: HashSet<&str> = keys.iter().map(|s| s.as_str()).collect();
                let mut counts: HashMap<String, usize> =
                    keys.iter().map(|k| (k.clone(), 0)).collect();

                fn traverse(
                    value: &Value,
                    key_set: &HashSet<&str>,
                    counts: &mut HashMap<String, usize>,
                ) {
                    match value {
                        Value::Object(map) => {
                            for (k, v) in map {
                                if key_set.contains(k.as_str()) {
                                    *counts.get_mut(k.as_str()).unwrap() += 1;
                                }
                                traverse(v, key_set, counts);
                            }
                        }
                        Value::Array(arr) => {
                            for v in arr {
                                traverse(v, key_set, counts);
                            }
                        }
                        _ => {}
                    }
                }

                for section in parsed.gamestate.values() {
                    traverse(section, &key_set, &mut counts);
                }
                json!({ "counts": counts })
            }
            MultiOp::ContainsTokens { tokens } => {
                let mut matches: HashMap<String, bool> =
                    tokens.iter().map(|t| (t.clone(), false)).collect();
                if !tokens.is_empty() {
                    let ac =
                        AhoCorasick::new(&tokens).expect("Failed to build Aho-Corasick automaton");
                    for mat in ac.find_iter(&parsed.gamestate_bytes) {
                        let pattern_idx = mat.pattern().as_usize();
                        if pattern_idx < tokens.len() {
                            matches.insert(tokens[pattern_idx].clone(), true);
                        }
                    }
                }
                json!({ "matches": matches })
            }
            MultiOp::ContainsKv { pairs } => {
                use std::collections::HashSet;
                let mut key_to_values: HashMap<String, HashSet<String>> = HashMap::new();
                for (key, value) in &pairs {
                    key_to_values
                        .entry(key.clone())
                        .or_default()
                        .insert(value.clone());
                }
                let mut matches: HashMap<String, bool> = pairs
                    .iter()
                    .map(|(k, v)| (format!("{}={}", k, v), false))
                    .collect();

                fn traverse_kv(
                    value: &Value,
                    key_to_values: &HashMap<String, HashSet<String>>,
                    matches: &mut HashMap<String, bool>,
                ) {
                    match value {
                        Value::Object(map) => {
                            for (k, v) in map {
                                if let Some(target_values) = key_to_values.get(k.as_str()) {
                                    let value_str = match v {
                                        Value::String(s) => Some(s.as_str()),
                                        Value::Number(_) => None,
                                        Value::Bool(b) => {
                                            if *b {
                                                Some("yes")
                                            } else {
                                                Some("no")
                                            }
                                        }
                                        _ => None,
                                    };
                                    if let Some(vs) = value_str {
                                        if target_values.contains(vs) {
                                            matches.insert(format!("{}={}", k, vs), true);
                                        }
                                    }
                                    if let Value::Number(n) = v {
                                        let num_str = n.to_string();
                                        if target_values.contains(&num_str) {
                                            matches.insert(format!("{}={}", k, num_str), true);
                                        }
                                    }
                                }
                                traverse_kv(v, key_to_values, matches);
                            }
                        }
                        Value::Array(arr) => {
                            for v in arr {
                                traverse_kv(v, key_to_values, matches);
                            }
                        }
                        _ => {}
                    }
                }

                for section in parsed.gamestate.values() {
                    traverse_kv(section, &key_to_values, &mut matches);
                }
                json!({ "matches": matches })
            }
            MultiOp::GetCountrySummaries { fields } => {
                let mut countries: Vec<Value> = Vec::new();
                if let Some(Value::Object(country_map)) = parsed.gamestate.get("country") {
                    for (country_id, country_data) in country_map {
                        let mut summary = Map::new();
                        summary.insert("id".to_string(), json!(country_id));
                        if let Value::Object(country_obj) = country_data {
                            for field in &fields {
                                if let Some(value) = country_obj.get(field) {
                                    summary.insert(field.clone(), value.clone());
                                }
                            }
                        }
                        countries.push(Value::Object(summary));
                    }
                }
                json!({ "countries": countries })
            }
            MultiOp::GetDuplicateValues {
                section,
                key,
                field,
            } => {
                // Use cached section offset if available to avoid re-scanning 84MB gamestate
                let cached_offset = section_offset_cache.get(&section).copied();
                let (values, found, new_offset) =
                    extract_duplicate_values(&content, &section, &key, &field, cached_offset);
                // Cache the section offset for future ops in this batch
                if let Some(offset) = new_offset {
                    section_offset_cache.insert(section.clone(), offset);
                }
                json!({ "values": values, "found": found })
            }
            MultiOp::GetEntryText { section, key } => {
                let (text, found) = extract_entry_text(&content, &section, &key, None);
                json!({ "text": text, "found": found })
            }
        };
        results.push(result);
    }

    write_response(&SuccessResponse {
        ok: true,
        data: ResponseData::MultiResults { results },
    })
}

/// Main serve loop
pub fn run(path: &str) -> Result<()> {
    // Log startup to stderr (stdout is reserved for protocol)
    eprintln!(
        "[serve] Loading save file: {} (tool_version={})",
        path, TOOL_VERSION
    );

    // Load and parse the save file once
    let parsed = match ParsedSave::load(path) {
        Ok(p) => {
            eprintln!("[serve] Save loaded successfully, entering request loop");
            p
        }
        Err(e) => {
            // Write error response and exit directly (don't propagate to main error handler)
            let message = format!("{:#}", e);
            let exit_code =
                if message.contains("Failed to open file") || message.contains("No such file") {
                    ErrorKind::FileNotFound.exit_code()
                } else {
                    ErrorKind::ParseError.exit_code()
                };
            let _ = write_error("ParseError", &message, exit_code);
            std::process::exit(exit_code);
        }
    };

    // Enter stdin read loop
    let stdin = io::stdin();
    let reader = stdin.lock();

    for line in reader.lines() {
        let line = match line {
            Ok(l) => l,
            Err(e) => {
                eprintln!("[serve] Error reading stdin: {}", e);
                break;
            }
        };

        // Empty line or EOF
        if line.is_empty() {
            continue;
        }

        // Parse the request
        let request: Request = match serde_json::from_str(&line) {
            Ok(r) => r,
            Err(e) => {
                let _ = write_error(
                    "InvalidRequest",
                    &format!("Failed to parse request: {}", e),
                    ErrorKind::InvalidArgument.exit_code(),
                );
                continue;
            }
        };

        // Handle the request
        let result = match request {
            Request::ExtractSections { sections } => handle_extract_sections(&parsed, sections),
            Request::IterSection {
                section,
                batch_size,
            } => handle_iter_section(&parsed, section, batch_size),
            Request::GetEntry { section, key } => handle_get_entry(&parsed, section, key),
            Request::GetEntries {
                section,
                keys,
                fields,
            } => handle_get_entries(&parsed, section, keys, fields),
            Request::CountKeys { keys } => handle_count_keys(&parsed, keys),
            Request::ContainsTokens { tokens } => {
                handle_contains_tokens(&parsed.gamestate_bytes, tokens)
            }
            Request::ContainsKv { pairs } => handle_contains_kv(&parsed, pairs),
            Request::GetCountrySummaries { fields } => {
                handle_get_country_summaries(&parsed, fields)
            }
            Request::GetDuplicateValues {
                section,
                key,
                field,
            } => handle_get_duplicate_values(&parsed.gamestate_bytes, section, key, field),
            Request::GetEntryText { section, key } => {
                handle_get_entry_text(&parsed.gamestate_bytes, section, key)
            }
            Request::Multi { ops } => handle_multi_op(&parsed, ops),
            Request::Close => {
                eprintln!("[serve] Received close request, shutting down");
                write_response(&SuccessResponse {
                    ok: true,
                    data: ResponseData::Closed { closed: true },
                })?;
                break;
            }
        };

        if let Err(e) = result {
            eprintln!("[serve] Error writing response: {}", e);
            break;
        }
    }

    eprintln!("[serve] Session ended");
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_request_parsing() {
        let json = r#"{"op": "extract_sections", "sections": ["meta", "player"]}"#;
        let req: Request = serde_json::from_str(json).unwrap();
        match req {
            Request::ExtractSections { sections } => {
                assert_eq!(sections, vec!["meta", "player"]);
            }
            _ => panic!("Wrong request type"),
        }
    }

    #[test]
    fn test_iter_section_request() {
        let json = r#"{"op": "iter_section", "section": "country"}"#;
        let req: Request = serde_json::from_str(json).unwrap();
        match req {
            Request::IterSection {
                section,
                batch_size,
            } => {
                assert_eq!(section, "country");
                assert_eq!(batch_size, 100); // Default batch size
            }
            _ => panic!("Wrong request type"),
        }
    }

    #[test]
    fn test_iter_section_request_with_batch_size() {
        let json = r#"{"op": "iter_section", "section": "country", "batch_size": 50}"#;
        let req: Request = serde_json::from_str(json).unwrap();
        match req {
            Request::IterSection {
                section,
                batch_size,
            } => {
                assert_eq!(section, "country");
                assert_eq!(batch_size, 50);
            }
            _ => panic!("Wrong request type"),
        }
    }

    #[test]
    fn test_get_entry_request() {
        let json = r#"{"op": "get_entry", "section": "country", "key": "0"}"#;
        let req: Request = serde_json::from_str(json).unwrap();
        match req {
            Request::GetEntry { section, key } => {
                assert_eq!(section, "country");
                assert_eq!(key, "0");
            }
            _ => panic!("Wrong request type"),
        }
    }

    #[test]
    fn test_close_request() {
        let json = r#"{"op": "close"}"#;
        let req: Request = serde_json::from_str(json).unwrap();
        assert!(matches!(req, Request::Close));
    }

    #[test]
    fn test_get_entries_request() {
        let json = r#"{"op": "get_entries", "section": "country", "keys": ["0", "1", "2"]}"#;
        let req: Request = serde_json::from_str(json).unwrap();
        match req {
            Request::GetEntries {
                section,
                keys,
                fields,
            } => {
                assert_eq!(section, "country");
                assert_eq!(keys, vec!["0", "1", "2"]);
                assert!(fields.is_none());
            }
            _ => panic!("Wrong request type"),
        }
    }

    #[test]
    fn test_get_entries_request_with_fields() {
        let json = r#"{"op": "get_entries", "section": "country", "keys": ["0"], "fields": ["name", "type"]}"#;
        let req: Request = serde_json::from_str(json).unwrap();
        match req {
            Request::GetEntries {
                section,
                keys,
                fields,
            } => {
                assert_eq!(section, "country");
                assert_eq!(keys, vec!["0"]);
                assert_eq!(fields, Some(vec!["name".to_string(), "type".to_string()]));
            }
            _ => panic!("Wrong request type"),
        }
    }

    #[test]
    fn test_count_keys_request() {
        let json = r#"{"op": "count_keys", "keys": ["name", "type", "flag"]}"#;
        let req: Request = serde_json::from_str(json).unwrap();
        match req {
            Request::CountKeys { keys } => {
                assert_eq!(keys, vec!["name", "type", "flag"]);
            }
            _ => panic!("Wrong request type"),
        }
    }

    #[test]
    fn test_error_response_serialization() {
        let err = ErrorResponse::new("SectionNotFound", "Section 'foo' not found", 2);
        let json = serde_json::to_string(&err).unwrap();
        assert!(json.contains(r#""ok":false"#));
        assert!(json.contains(r#""error":"SectionNotFound""#));
    }

    #[test]
    fn test_contains_tokens_request() {
        let json = r#"{"op": "contains_tokens", "tokens": ["country", "fleet", "xyz123"]}"#;
        let req: Request = serde_json::from_str(json).unwrap();
        match req {
            Request::ContainsTokens { tokens } => {
                assert_eq!(tokens, vec!["country", "fleet", "xyz123"]);
            }
            _ => panic!("Wrong request type"),
        }
    }

    #[test]
    fn test_get_country_summaries_request() {
        let json = r#"{"op": "get_country_summaries", "fields": ["name", "type", "flag"]}"#;
        let req: Request = serde_json::from_str(json).unwrap();
        match req {
            Request::GetCountrySummaries { fields } => {
                assert_eq!(fields, vec!["name", "type", "flag"]);
            }
            _ => panic!("Wrong request type"),
        }
    }

    #[test]
    fn test_contains_kv_request() {
        let json =
            r#"{"op": "contains_kv", "pairs": [["war_in_heaven", "yes"], ["version", "3"]]}"#;
        let req: Request = serde_json::from_str(json).unwrap();
        match req {
            Request::ContainsKv { pairs } => {
                assert_eq!(pairs.len(), 2);
                assert_eq!(pairs[0], ("war_in_heaven".to_string(), "yes".to_string()));
                assert_eq!(pairs[1], ("version".to_string(), "3".to_string()));
            }
            _ => panic!("Wrong request type"),
        }
    }

    #[test]
    fn test_get_duplicate_values_request() {
        let json = r#"{"op": "get_duplicate_values", "section": "leaders", "key": "123", "field": "traits"}"#;
        let req: Request = serde_json::from_str(json).unwrap();
        match req {
            Request::GetDuplicateValues {
                section,
                key,
                field,
            } => {
                assert_eq!(section, "leaders");
                assert_eq!(key, "123");
                assert_eq!(field, "traits");
            }
            _ => panic!("Wrong request type"),
        }
    }

    #[test]
    fn test_multi_op_request() {
        let json = r#"{"op": "multi", "ops": [{"op": "get_entry", "section": "country", "key": "0"}, {"op": "count_keys", "keys": ["name"]}]}"#;
        let req: Request = serde_json::from_str(json).unwrap();
        match req {
            Request::Multi { ops } => {
                assert_eq!(ops.len(), 2);
                match &ops[0] {
                    MultiOp::GetEntry { section, key } => {
                        assert_eq!(section, "country");
                        assert_eq!(key, "0");
                    }
                    _ => panic!("Wrong op type for first op"),
                }
                match &ops[1] {
                    MultiOp::CountKeys { keys } => {
                        assert_eq!(keys, &vec!["name"]);
                    }
                    _ => panic!("Wrong op type for second op"),
                }
            }
            _ => panic!("Wrong request type"),
        }
    }

    #[test]
    fn test_multi_op_all_types() {
        // Test that all MultiOp variants can be parsed
        let json = r#"{"op": "multi", "ops": [
            {"op": "extract_sections", "sections": ["meta"]},
            {"op": "get_entry", "section": "country", "key": "0"},
            {"op": "get_entries", "section": "country", "keys": ["0", "1"]},
            {"op": "count_keys", "keys": ["name"]},
            {"op": "contains_tokens", "tokens": ["test"]},
            {"op": "contains_kv", "pairs": [["key", "value"]]},
            {"op": "get_country_summaries", "fields": ["name"]},
            {"op": "get_duplicate_values", "section": "leaders", "key": "0", "field": "traits"}
        ]}"#;
        let req: Request = serde_json::from_str(json).unwrap();
        match req {
            Request::Multi { ops } => {
                assert_eq!(ops.len(), 8);
            }
            _ => panic!("Wrong request type"),
        }
    }
}
