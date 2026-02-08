use crate::error::{exit_with_error, ErrorKind, SCHEMA_VERSION, TOOL_VERSION};
use anyhow::{Context, Result};
use jomini::text::de::from_windows1252_slice;
use serde_json::{json, Value};
use std::collections::HashMap;
use std::fs::File;
use std::io::Read;
use zip::ZipArchive;

/// Stream entries from a large section in a .sav file as JSONL
pub fn run_save(path: &str, section: &str, schema_version: &str, format: &str) -> Result<()> {
    // Validate schema version
    validate_schema_version(schema_version);

    // Validate format
    if format != "jsonl" {
        exit_with_error(
            ErrorKind::InvalidArgument,
            &format!("Unsupported format: {}. Only 'jsonl' is supported.", format),
        );
    }

    // Read the .sav file (ZIP archive)
    let file = File::open(path).with_context(|| format!("Failed to open file: {}", path))?;
    let mut archive = ZipArchive::new(file).with_context(|| "Failed to read ZIP archive")?;

    // Extract gamestate content
    let gamestate_content = {
        let mut gamestate_file = archive
            .by_name("gamestate")
            .with_context(|| "No gamestate file in archive")?;
        let mut content = Vec::new();
        gamestate_file.read_to_end(&mut content)?;
        content
    };

    // Parse the full gamestate using Windows-1252 encoding
    // (Stellaris saves use Windows-1252, not UTF-8)
    let parsed: HashMap<String, Value> =
        from_windows1252_slice(&gamestate_content).with_context(|| "Failed to parse gamestate")?;

    // Get the requested section
    if let Some(section_value) = parsed.get(section) {
        // First line includes full metadata
        let mut is_first = true;

        // If it's an object with key-value pairs, iterate over them
        if let Value::Object(map) = section_value {
            for (key, value) in map {
                let line = if is_first {
                    is_first = false;
                    json!({
                        "schema_version": SCHEMA_VERSION,
                        "tool_version": TOOL_VERSION,
                        "game": "stellaris",
                        "section": section,
                        "key": key,
                        "value": value
                    })
                } else {
                    json!({
                        "key": key,
                        "value": value
                    })
                };
                println!("{}", serde_json::to_string(&line)?);
            }
        }
    }

    Ok(())
}

/// Validate schema version or exit with error
fn validate_schema_version(schema_version: &str) {
    match schema_version.parse::<u32>() {
        Ok(v) if v == SCHEMA_VERSION => {}
        Ok(v) => {
            exit_with_error(
                ErrorKind::InvalidArgument,
                &format!(
                    "Requested schema version {} is not supported. Supported: {}",
                    v, SCHEMA_VERSION
                ),
            );
        }
        Err(_) => {
            exit_with_error(
                ErrorKind::InvalidArgument,
                &format!("Invalid schema version: {}", schema_version),
            );
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_schema_version() {
        assert_eq!(SCHEMA_VERSION, 1);
    }
}
