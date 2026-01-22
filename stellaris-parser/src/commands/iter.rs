use anyhow::{Context, Result};
use jomini::text::de::from_utf8_slice;
use serde_json::{json, Value};
use std::collections::HashMap;
use std::fs::File;
use std::io::Read;
use zip::ZipArchive;

const SCHEMA_VERSION: u32 = 1;
const TOOL_VERSION: &str = env!("CARGO_PKG_VERSION");

/// Stream entries from a large section in a .sav file as JSONL
pub fn run_save(path: &str, section: &str, schema_version: &str, format: &str) -> Result<()> {
    // Validate schema version
    let requested_version: u32 = schema_version
        .parse()
        .context("Invalid schema version")?;
    if requested_version != SCHEMA_VERSION {
        eprintln!("{}", json!({
            "schema_version": SCHEMA_VERSION,
            "tool_version": TOOL_VERSION,
            "error": "UnsupportedSchemaVersion",
            "message": format!("Requested schema version {} is not supported. Supported: {}", requested_version, SCHEMA_VERSION)
        }));
        std::process::exit(3);
    }

    if format != "jsonl" {
        eprintln!("{}", json!({
            "schema_version": SCHEMA_VERSION,
            "tool_version": TOOL_VERSION,
            "error": "UnsupportedFormat",
            "message": format!("Unsupported format: {}. Only 'jsonl' is supported.", format)
        }));
        std::process::exit(3);
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

    // Parse the full gamestate
    let parsed: HashMap<String, Value> = from_utf8_slice(&gamestate_content)
        .with_context(|| "Failed to parse gamestate")?;

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

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_schema_version() {
        assert_eq!(SCHEMA_VERSION, 1);
    }
}
