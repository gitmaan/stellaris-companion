use serde_json::json;

pub const SCHEMA_VERSION: u32 = 1;
pub const TOOL_VERSION: &str = env!("CARGO_PKG_VERSION");

/// Error types that map to specific exit codes
pub enum ErrorKind {
    FileNotFound,
    ParseError,
    InvalidArgument,
}

impl ErrorKind {
    pub fn exit_code(&self) -> i32 {
        match self {
            ErrorKind::FileNotFound => 1,
            ErrorKind::ParseError => 2,
            ErrorKind::InvalidArgument => 3,
        }
    }

    pub fn error_type(&self) -> &'static str {
        match self {
            ErrorKind::FileNotFound => "FileNotFound",
            ErrorKind::ParseError => "ParseError",
            ErrorKind::InvalidArgument => "InvalidArgument",
        }
    }
}

/// Print error as JSON to stderr and exit with appropriate code
pub fn exit_with_error(kind: ErrorKind, message: &str) -> ! {
    let error_json = json!({
        "schema_version": SCHEMA_VERSION,
        "tool_version": TOOL_VERSION,
        "error": kind.error_type(),
        "message": message
    });
    eprintln!("{}", error_json);
    std::process::exit(kind.exit_code());
}

/// Convert an anyhow error to a JSON error and exit
pub fn handle_error(err: anyhow::Error) -> ! {
    let message = format!("{:#}", err);

    // Determine error kind from message content
    let kind = if message.contains("No such file or directory")
        || message.contains("Failed to open file")
        || message.contains("cannot find the file")
        || message.contains("The system cannot find")
    {
        ErrorKind::FileNotFound
    } else if message.contains("Failed to parse")
        || message.contains("Failed to read ZIP")
        || message.contains("No gamestate file")
        || message.contains("No meta file")
    {
        ErrorKind::ParseError
    } else {
        ErrorKind::ParseError // Default to parse error for other issues
    };

    exit_with_error(kind, &message);
}
