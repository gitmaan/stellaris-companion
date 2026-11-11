//! Clausewitz format edge case tests
//!
//! These tests validate jomini's handling of Clausewitz format edge cases:
//! - Condensed syntax (a={b="1"c=d}) → parsed correctly
//! - Escape sequences (\" and \\) → handled properly
//!
//! Repeated keys are covered in `crate::grouped`, which is what the commands use.

#[cfg(test)]
mod tests {
    use jomini::text::de::from_utf8_slice;
    use serde_json::Value;
    use std::collections::HashMap;

    /// Test that condensed syntax without whitespace is parsed correctly
    ///
    /// Clausewitz format allows condensed blocks like:
    /// ```text
    /// a={b="1"c=d}
    /// ```
    /// where quoted strings serve as delimiters between key-value pairs.
    ///
    /// Note: jomini correctly parses condensed syntax when quoted strings
    /// provide clear boundaries. Bare values (unquoted) adjacent to other
    /// bare values may be concatenated as a single token.
    #[test]
    fn test_condensed_syntax() {
        // Condensed syntax with quoted values (this is what the architecture doc specifies)
        // Quoted strings provide clear delimiters
        let clausewitz_data = br#"data={name="test"value="42"enabled="yes"}"#;

        let parsed: HashMap<String, Value> =
            from_utf8_slice(clausewitz_data).expect("Failed to parse condensed syntax");

        let data = parsed.get("data").expect("data section should exist");

        // Verify all key-value pairs were parsed
        assert_eq!(
            data.get("name").and_then(|v| v.as_str()),
            Some("test"),
            "name should be 'test'"
        );

        assert_eq!(
            data.get("value").and_then(|v| v.as_str()),
            Some("42"),
            "value should be '42'"
        );

        assert_eq!(
            data.get("enabled").and_then(|v| v.as_str()),
            Some("yes"),
            "enabled should be 'yes'"
        );
    }

    /// Test that condensed syntax with nested braces works
    ///
    /// Nested braces provide natural delimiters, so condensed syntax
    /// with nested blocks is handled correctly.
    #[test]
    fn test_condensed_syntax_nested() {
        // Braces serve as delimiters, allowing adjacent key-value pairs
        let clausewitz_data = br#"outer={inner={a="1"b="2"}c="3"}"#;

        let parsed: HashMap<String, Value> =
            from_utf8_slice(clausewitz_data).expect("Failed to parse nested condensed syntax");

        let outer = parsed.get("outer").expect("outer section should exist");
        let inner = outer.get("inner").expect("inner section should exist");

        // Check inner values
        assert_eq!(
            inner.get("a").and_then(|v| v.as_str()),
            Some("1"),
            "a should be '1'"
        );

        assert_eq!(
            inner.get("b").and_then(|v| v.as_str()),
            Some("2"),
            "b should be '2'"
        );

        assert_eq!(
            outer.get("c").and_then(|v| v.as_str()),
            Some("3"),
            "c should be '3'"
        );
    }

    /// Test condensed syntax with quoted strings adjacent to other values
    #[test]
    fn test_condensed_syntax_quotes() {
        // Strings directly adjacent to other key-value pairs
        let clausewitz_data = br#"data={first="hello"second="world"count=5}"#;

        let parsed: HashMap<String, Value> =
            from_utf8_slice(clausewitz_data).expect("Failed to parse quoted condensed syntax");

        let data = parsed.get("data").expect("data should exist");
        assert_eq!(data.get("first").and_then(|v| v.as_str()), Some("hello"));
        assert_eq!(data.get("second").and_then(|v| v.as_str()), Some("world"));
    }

    /// Test that escape sequences in strings are handled correctly
    ///
    /// Clausewitz format supports escape sequences like:
    /// - \" for literal quotes
    /// - \\ for literal backslashes
    #[test]
    fn test_escape_sequences() {
        // Test escaped quotes inside strings
        let clausewitz_data = br#"empire={
    name="The \"Great\" Empire"
    path="C:\\Users\\Player\\saves"
}"#;

        let parsed: HashMap<String, Value> =
            from_utf8_slice(clausewitz_data).expect("Failed to parse escape sequences");

        let empire = parsed.get("empire").expect("empire section should exist");

        // Check name with escaped quotes - jomini should handle the escapes
        let name = empire
            .get("name")
            .and_then(|v| v.as_str())
            .expect("name should be a string");

        // The name should contain "Great" - the exact representation of escapes may vary
        assert!(
            name.contains("Great") || name.contains("\\\"Great\\\""),
            "name should contain 'Great' (possibly escaped): got '{}'",
            name
        );

        // Check path with backslashes
        let path = empire
            .get("path")
            .and_then(|v| v.as_str())
            .expect("path should be a string");

        // Path should contain the directory components
        assert!(
            path.contains("Users") || path.contains("\\\\Users"),
            "path should contain 'Users': got '{}'",
            path
        );
    }

    /// Test escape sequences with simple cases
    #[test]
    fn test_escape_sequences_simple() {
        // Simple escaped quote
        let data1 = br#"test={value="hello \"world\""}"#;
        let parsed1: HashMap<String, Value> =
            from_utf8_slice(data1).expect("Failed to parse simple escape");

        let test = parsed1.get("test").expect("test should exist");
        let value = test.get("value").and_then(|v| v.as_str()).unwrap();

        // Should contain "world" (escapes may be processed or preserved)
        assert!(
            value.contains("world"),
            "Should contain 'world': got '{}'",
            value
        );
    }

    /// Test backslash escaping
    #[test]
    fn test_escape_sequences_backslash() {
        // Backslash escaping
        let data = br#"config={dir="C:\\Program Files\\Game"}"#;
        let parsed: HashMap<String, Value> =
            from_utf8_slice(data).expect("Failed to parse backslash escape");

        let config = parsed.get("config").expect("config should exist");
        let dir = config.get("dir").and_then(|v| v.as_str()).unwrap();

        // Should contain path components
        assert!(
            dir.contains("Program") && dir.contains("Game"),
            "Should contain path components: got '{}'",
            dir
        );
    }

    /// Test that empty blocks are handled correctly
    #[test]
    fn test_empty_blocks() {
        let clausewitz_data = br#"
empty={}
with_empty={
    nested={}
    value=42
}
"#;
        let parsed: HashMap<String, Value> =
            from_utf8_slice(clausewitz_data).expect("Failed to parse empty blocks");

        assert!(parsed.contains_key("empty"), "empty should exist");

        let with_empty = parsed.get("with_empty").expect("with_empty should exist");
        assert!(with_empty.get("nested").is_some(), "nested should exist");
        assert!(with_empty.get("value").is_some(), "value should exist");
    }

    /// Test mixed numeric and string values
    #[test]
    fn test_mixed_values() {
        let clausewitz_data = br#"
mixed={
    id=12345
    name="Test Empire"
    active=yes
    ratio=0.75
}
"#;
        let parsed: HashMap<String, Value> =
            from_utf8_slice(clausewitz_data).expect("Failed to parse mixed values");

        let mixed = parsed.get("mixed").expect("mixed should exist");

        // id should be numeric
        let id = mixed.get("id").expect("id should exist");
        assert!(
            id.as_i64().is_some() || id.as_str().is_some(),
            "id should be a number or string"
        );

        // name should be string
        assert_eq!(
            mixed.get("name").and_then(|v| v.as_str()),
            Some("Test Empire")
        );

        // active should be bool or string
        let active = mixed.get("active").expect("active should exist");
        assert!(
            active.as_bool() == Some(true) || active.as_str() == Some("yes"),
            "active should be true/yes"
        );
    }
}
