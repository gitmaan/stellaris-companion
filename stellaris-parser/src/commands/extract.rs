use anyhow::{Context, Result};
use jomini::text::de::from_utf8_slice;
use serde_json::{json, Map, Value};
use std::collections::HashMap;
use std::fs::File;
use std::io::{BufWriter, Read, Write};
use zip::ZipArchive;

const SCHEMA_VERSION: u32 = 1;
const TOOL_VERSION: &str = env!("CARGO_PKG_VERSION");

/// Run extraction on a .sav file (ZIP archive containing gamestate and meta)
pub fn run_save(path: &str, sections: &str, schema_version: &str, output: &str) -> Result<()> {
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

    let section_list: Vec<&str> = sections.split(',').map(|s| s.trim()).collect();

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

    // Extract meta content if requested
    let meta_content = if section_list.contains(&"meta") {
        let mut meta_file = archive
            .by_name("meta")
            .with_context(|| "No meta file in archive")?;
        let mut content = Vec::new();
        meta_file.read_to_end(&mut content)?;
        Some(content)
    } else {
        None
    };

    // Parse and extract sections
    let result = extract_sections(&gamestate_content, meta_content.as_deref(), &section_list)?;

    // Output
    write_output(&result, output)?;

    Ok(())
}

/// Run extraction on an already-extracted gamestate file (debug command)
pub fn run_gamestate(path: &str, sections: &str, schema_version: &str, output: &str) -> Result<()> {
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

    let section_list: Vec<&str> = sections.split(',').map(|s| s.trim()).collect();

    // Read the raw gamestate file
    let mut file = File::open(path).with_context(|| format!("Failed to open file: {}", path))?;
    let mut content = Vec::new();
    file.read_to_end(&mut content)?;

    // Parse and extract sections
    let result = extract_sections(&content, None, &section_list)?;

    // Output
    write_output(&result, output)?;

    Ok(())
}

fn extract_sections(gamestate: &[u8], meta: Option<&[u8]>, sections: &[&str]) -> Result<Value> {
    let mut result = Map::new();
    result.insert("schema_version".to_string(), json!(SCHEMA_VERSION));
    result.insert("tool_version".to_string(), json!(TOOL_VERSION));
    result.insert("game".to_string(), json!("stellaris"));

    // Parse the full gamestate once
    let parsed: HashMap<String, Value> = from_utf8_slice(gamestate)
        .with_context(|| "Failed to parse gamestate")?;

    // Extract requested sections from gamestate
    for section in sections {
        if *section == "meta" {
            if let Some(meta_bytes) = meta {
                let meta_parsed: HashMap<String, Value> = from_utf8_slice(meta_bytes)
                    .with_context(|| "Failed to parse meta file")?;
                result.insert("meta".to_string(), json!(meta_parsed));
            }
        } else if let Some(value) = parsed.get(*section) {
            result.insert(section.to_string(), value.clone());
        }
    }

    Ok(Value::Object(result))
}

fn write_output(result: &Value, output: &str) -> Result<()> {
    let json_str = serde_json::to_string_pretty(result)?;

    if output == "-" {
        println!("{}", json_str);
    } else {
        let file = File::create(output)?;
        let mut writer = BufWriter::new(file);
        writer.write_all(json_str.as_bytes())?;
    }

    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_schema_version_validation() {
        // Schema version 1 should be valid
        assert_eq!(SCHEMA_VERSION, 1);
    }
}
