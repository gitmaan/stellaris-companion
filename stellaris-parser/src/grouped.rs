//! Parse Clausewitz text to JSON without losing repeated keys.
//!
//! Clausewitz writes lists as a key repeated inside one block:
//! `ethos={ ethic="a" ethic="b" }`. Deserializing a block into a plain map keeps
//! only the last value, so every reader of such a key silently loses data. Here a
//! key that occurs more than once in a block becomes an array of its values, in
//! save order; a key that occurs once keeps its value unchanged.
//!
//! Stellaris saves are UTF-8. Text that is not valid UTF-8 (older saves, some mods)
//! is read as Windows-1252, which is what the engine used before.

use std::borrow::Cow;
use std::collections::{HashMap, HashSet};
use std::fmt;

use jomini::{Encoding, TextDeserializer, TextTape, Utf8Encoding, Windows1252Encoding};
use serde::de::{Deserialize, Deserializer, MapAccess, SeqAccess, Visitor};
use serde_json::{Map, Number, Value};

/// Parse a whole Clausewitz document (a save's `gamestate` or `meta`).
pub fn parse_document(data: &[u8]) -> Result<HashMap<String, Value>, jomini::Error> {
    let tape = TextTape::from_slice(data)?;
    let Root(map) = TextDeserializer::from_encoded_tape(&tape, SaveEncoding).deserialize()?;
    Ok(map.into_iter().collect())
}

/// UTF-8, falling back to Windows-1252 for a string that is not valid UTF-8.
#[derive(Clone, Copy)]
struct SaveEncoding;

impl Encoding for SaveEncoding {
    fn decode<'a>(&self, data: &'a [u8]) -> Cow<'a, str> {
        if std::str::from_utf8(data).is_ok() {
            Utf8Encoding::decode(data)
        } else {
            Windows1252Encoding::decode(data)
        }
    }
}

struct Root(Map<String, Value>);

impl<'de> Deserialize<'de> for Root {
    fn deserialize<D: Deserializer<'de>>(deserializer: D) -> Result<Self, D::Error> {
        // The document root is always key/value pairs and jomini requires a map hint there.
        match deserializer.deserialize_map(GroupedVisitor)? {
            Value::Object(map) => Ok(Root(map)),
            _ => Ok(Root(Map::new())),
        }
    }
}

struct Grouped(Value);

impl<'de> Deserialize<'de> for Grouped {
    fn deserialize<D: Deserializer<'de>>(deserializer: D) -> Result<Self, D::Error> {
        deserializer.deserialize_any(GroupedVisitor).map(Grouped)
    }
}

struct GroupedVisitor;

impl<'de> Visitor<'de> for GroupedVisitor {
    type Value = Value;

    fn expecting(&self, formatter: &mut fmt::Formatter) -> fmt::Result {
        formatter.write_str("any Clausewitz value")
    }

    fn visit_bool<E>(self, value: bool) -> Result<Value, E> {
        Ok(Value::Bool(value))
    }

    fn visit_i64<E>(self, value: i64) -> Result<Value, E> {
        Ok(Value::Number(value.into()))
    }

    fn visit_u64<E>(self, value: u64) -> Result<Value, E> {
        Ok(Value::Number(value.into()))
    }

    fn visit_f64<E>(self, value: f64) -> Result<Value, E> {
        Ok(Number::from_f64(value).map_or(Value::Null, Value::Number))
    }

    fn visit_str<E>(self, value: &str) -> Result<Value, E> {
        Ok(Value::String(value.to_owned()))
    }

    fn visit_string<E>(self, value: String) -> Result<Value, E> {
        Ok(Value::String(value))
    }

    fn visit_unit<E>(self) -> Result<Value, E> {
        Ok(Value::Null)
    }

    fn visit_none<E>(self) -> Result<Value, E> {
        Ok(Value::Null)
    }

    fn visit_some<D: Deserializer<'de>>(self, deserializer: D) -> Result<Value, D::Error> {
        Grouped::deserialize(deserializer).map(|Grouped(value)| value)
    }

    fn visit_seq<A: SeqAccess<'de>>(self, mut seq: A) -> Result<Value, A::Error> {
        let mut items = Vec::new();
        while let Some(Grouped(value)) = seq.next_element()? {
            items.push(value);
        }
        Ok(Value::Array(items))
    }

    fn visit_map<A: MapAccess<'de>>(self, mut access: A) -> Result<Value, A::Error> {
        let mut map = Map::new();
        // Keys already turned into a group, so a value that is itself an array is
        // not mistaken for one.
        let mut grouped: HashSet<String> = HashSet::new();
        while let Some(key) = access.next_key::<String>()? {
            let Grouped(value) = access.next_value()?;
            match map.get_mut(&key) {
                None => {
                    map.insert(key, value);
                }
                Some(existing) => {
                    if grouped.contains(&key) {
                        if let Value::Array(items) = existing {
                            items.push(value);
                        }
                    } else {
                        let first = existing.take();
                        *existing = Value::Array(vec![first, value]);
                        grouped.insert(key);
                    }
                }
            }
        }
        Ok(Value::Object(map))
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn repeated_keys_become_a_list_in_save_order() {
        let parsed = parse_document(
            br#"country={ 0={ ethos={ ethic="ethic_fanatic_egalitarian" ethic="ethic_xenophile" } } }"#,
        )
        .unwrap();
        assert_eq!(
            parsed["country"]["0"]["ethos"]["ethic"],
            json!(["ethic_fanatic_egalitarian", "ethic_xenophile"])
        );
    }

    #[test]
    fn a_single_key_keeps_its_value() {
        let parsed = parse_document(br#"a={ ethic="one" list={ 1 2 } }"#).unwrap();
        assert_eq!(parsed["a"]["ethic"], json!("one"));
        assert_eq!(parsed["a"]["list"], json!(["1", "2"]));
    }

    #[test]
    fn repeated_blocks_and_repeated_lists_are_kept_whole() {
        let parsed =
            parse_document(br#"a={ p={ id=1 } p={ id=2 } p={ id=3 } l={ 1 2 } l={ 3 } }"#).unwrap();
        assert_eq!(
            parsed["a"]["p"],
            json!([{"id": "1"}, {"id": "2"}, {"id": "3"}])
        );
        assert_eq!(parsed["a"]["l"], json!([["1", "2"], ["3"]]));
    }

    #[test]
    fn text_that_is_not_utf8_is_read_as_windows_1252() {
        let parsed = parse_document(b"city=\"M\xfcnchen\" price=\"\x80\"").unwrap();
        assert_eq!(parsed["city"], json!("München"));
        assert_eq!(parsed["price"], json!("€"));
    }

    #[test]
    fn names_are_read_as_utf8() {
        let parsed = parse_document("name=\"Fédération 星海共同体\"".as_bytes()).unwrap();
        assert_eq!(parsed["name"], json!("Fédération 星海共同体"));
    }
}
