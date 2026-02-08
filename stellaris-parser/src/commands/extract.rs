use crate::error::{exit_with_error, ErrorKind, SCHEMA_VERSION, TOOL_VERSION};
use anyhow::{Context, Result};
use jomini::text::de::from_windows1252_slice;
use serde_json::{json, Map, Value};
use std::collections::HashMap;
use std::fs::File;
use std::io::{BufWriter, Read, Write};
use zip::ZipArchive;

/// Run extraction on a .sav file (ZIP archive containing gamestate and meta)
pub fn run_save(path: &str, sections: &str, schema_version: &str, output: &str) -> Result<()> {
    // Validate schema version
    validate_schema_version(schema_version);

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
    validate_schema_version(schema_version);

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

    // Parse the full gamestate once using Windows-1252 encoding
    // (Stellaris saves use Windows-1252, not UTF-8)
    let parsed: HashMap<String, Value> =
        from_windows1252_slice(gamestate).with_context(|| "Failed to parse gamestate")?;

    // Extract requested sections from gamestate
    for section in sections {
        if *section == "meta" {
            if let Some(meta_bytes) = meta {
                let meta_parsed: HashMap<String, Value> = from_windows1252_slice(meta_bytes)
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

/// Read gamestate and optionally meta from a .sav ZIP archive
pub fn read_sav_file(path: &str) -> Result<(Vec<u8>, Option<Vec<u8>>)> {
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

    // Try to extract meta content (may not always need it)
    let meta_content = match archive.by_name("meta") {
        Ok(mut meta_file) => {
            let mut content = Vec::new();
            meta_file.read_to_end(&mut content)?;
            Some(content)
        }
        Err(_) => None,
    };

    Ok((gamestate_content, meta_content))
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::path::Path;

    #[test]
    fn test_schema_version_validation() {
        // Schema version 1 should be valid
        assert_eq!(SCHEMA_VERSION, 1);
    }

    #[test]
    fn test_sav_reading_file_structure() {
        // Test that we can detect ZIP structure from a .sav file
        // This test uses the actual test_save.sav if available
        let test_path = "../test_save.sav";
        if Path::new(test_path).exists() {
            let result = read_sav_file(test_path);
            assert!(
                result.is_ok(),
                "Should be able to read test_save.sav as ZIP"
            );
            let (gamestate, meta) = result.unwrap();
            assert!(!gamestate.is_empty(), "Gamestate should not be empty");
            assert!(meta.is_some(), "Meta should be present in test save");
            assert!(
                !meta.as_ref().unwrap().is_empty(),
                "Meta should not be empty"
            );
        }
    }

    #[test]
    fn test_sav_reading_nonexistent_file() {
        // Test that nonexistent files return proper error
        let result = read_sav_file("nonexistent.sav");
        assert!(result.is_err(), "Should fail for nonexistent file");
        let err_msg = format!("{:#}", result.unwrap_err());
        assert!(
            err_msg.contains("Failed to open file"),
            "Error should mention file open failure"
        );
    }
}
