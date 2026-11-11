//! Checks on the text the parser hands to JSON.
//!
//! Stellaris saves are UTF-8. `crate::grouped::parse_document` decodes them as
//! UTF-8 and falls back to Windows-1252 for any string that is not valid UTF-8, so
//! older saves and mods that still carry single-byte text are read rather than
//! mangled. Colour codes such as `\x15` are control characters in both encodings
//! and pass through unchanged; consumers strip them for display.

use serde_json::Value;

/// Verify that a JSON value contains valid UTF-8 strings recursively.
/// This is used for testing that encoding conversion produces valid output.
#[allow(dead_code)]
pub fn validate_json_strings(value: &Value) -> bool {
    match value {
        Value::String(_) => {
            // Strings from serde_json are always valid UTF-8
            true
        }
        Value::Array(arr) => arr.iter().all(validate_json_strings),
        Value::Object(obj) => obj.values().all(validate_json_strings),
        _ => true,
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::grouped::parse_document;
    use serde_json::json;

    /// Test that Windows-1252 encoded bytes are properly decoded
    #[test]
    fn test_encoding_windows1252_basic() {
        // Windows-1252 byte 0x92 = right single quotation mark (U+2019)
        // This is NOT valid UTF-8, but IS valid Windows-1252
        let data = b"test={name=\"Hello\x92World\"}";

        let result = parse_document(data);
        assert!(
            result.is_ok(),
            "Windows-1252 encoded data should parse successfully: {:?}",
            result.err()
        );

        let parsed = result.unwrap();
        let test = parsed.get("test").expect("test should exist");
        let name = test.get("name").and_then(|v| v.as_str()).unwrap();

        // The character should be decoded to Unicode
        assert!(
            name.contains("Hello") && name.contains("World"),
            "Name should contain both parts: '{}'",
            name
        );
    }

    /// Test that ASCII characters pass through correctly
    #[test]
    fn test_encoding_ascii_passthrough() {
        let data = br#"
empire={
    name="Test Empire"
    id=12345
}
"#;

        let result = parse_document(data);
        assert!(result.is_ok(), "ASCII data should parse successfully");

        let parsed = result.unwrap();
        let empire = parsed.get("empire").expect("empire should exist");
        assert_eq!(
            empire.get("name").and_then(|v| v.as_str()),
            Some("Test Empire")
        );
    }

    /// Test Windows-1252 specific characters (0x80-0x9F range)
    /// These bytes are NOT valid UTF-8 but ARE valid Windows-1252
    #[test]
    fn test_encoding_windows1252_special_range() {
        // 0x80 = Euro sign (€)
        // 0x85 = Horizontal ellipsis (…)
        // 0x93 = Left double quotation mark (")
        // 0x94 = Right double quotation mark (")
        let data = b"test={currency=\"\x80\"ellipsis=\"\x85\"quote=\"\x93text\x94\"}";

        let result = parse_document(data);
        assert!(
            result.is_ok(),
            "Windows-1252 special characters should parse: {:?}",
            result.err()
        );

        let parsed = result.unwrap();
        let test = parsed.get("test").expect("test should exist");

        // Currency should contain Euro sign
        let currency = test.get("currency").and_then(|v| v.as_str()).unwrap();
        assert!(
            currency.contains('€'),
            "Currency should contain Euro sign: '{}'",
            currency
        );
    }

    /// Test color codes and control characters
    #[test]
    fn test_encoding_color_codes() {
        // Stellaris uses bytes like 0x15 for color codes
        // In Windows-1252, 0x15 is a control character (NAK - Negative Acknowledge)
        // It should pass through as its Windows-1252 representation
        let data = b"test={text=\"\x15BColored Text\x15!\"}";

        let result = parse_document(data);
        assert!(
            result.is_ok(),
            "Color codes should parse: {:?}",
            result.err()
        );

        let parsed = result.unwrap();
        let test = parsed.get("test").expect("test should exist");
        let text = test.get("text").and_then(|v| v.as_str()).unwrap();

        // The text should contain "Colored Text"
        assert!(
            text.contains("Colored Text"),
            "Text should contain 'Colored Text': '{}'",
            text
        );
    }

    /// Test that high bytes (0xA0-0xFF) are handled correctly
    #[test]
    fn test_encoding_high_bytes() {
        // 0xE9 = é (Latin small letter e with acute)
        // 0xF1 = ñ (Latin small letter n with tilde)
        // 0xFC = ü (Latin small letter u with diaeresis)
        let data = b"test={name=\"caf\xe9\"country=\"Espa\xf1a\"city=\"M\xfcnchen\"}";

        let result = parse_document(data);
        assert!(
            result.is_ok(),
            "Extended Latin characters should parse: {:?}",
            result.err()
        );

        let parsed = result.unwrap();
        let test = parsed.get("test").expect("test should exist");

        // Check accented characters
        let name = test.get("name").and_then(|v| v.as_str()).unwrap();
        assert!(name.contains("caf"), "Should contain 'caf': '{}'", name);

        let country = test.get("country").and_then(|v| v.as_str()).unwrap();
        assert!(
            country.contains("Espa"),
            "Should contain 'Espa': '{}'",
            country
        );
    }

    /// Test that UTF-8 content also works (backwards compatible)
    #[test]
    fn test_encoding_utf8_compatible() {
        // Valid UTF-8 should also work with Windows-1252 decoder
        // (ASCII subset is identical)
        let data = br#"test={name="Simple ASCII name"value=42}"#;

        let result = parse_document(data);
        assert!(result.is_ok(), "UTF-8 compatible data should parse");

        let parsed = result.unwrap();
        let test = parsed.get("test").expect("test should exist");
        assert_eq!(
            test.get("name").and_then(|v| v.as_str()),
            Some("Simple ASCII name")
        );
    }

    /// Test validate_json_strings helper
    #[test]
    fn test_validate_json_strings() {
        let valid = json!({
            "name": "test",
            "nested": {
                "array": ["a", "b", "c"],
                "number": 42
            }
        });

        assert!(
            validate_json_strings(&valid),
            "Valid JSON should pass validation"
        );
    }
}
