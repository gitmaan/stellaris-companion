use clap::{Parser, Subcommand};

mod commands;
mod edge_cases;
mod error;
mod output;

#[derive(Parser)]
#[command(name = "stellaris-parser")]
#[command(about = "Fast Clausewitz format parser for Stellaris saves")]
#[command(version)]
struct Cli {
    #[command(subcommand)]
    command: Commands,
}

#[derive(Subcommand)]
enum Commands {
    /// Extract specific sections as JSON from a .sav file
    ExtractSave {
        /// Path to .sav file
        path: String,
        /// Comma-separated section names
        #[arg(long)]
        sections: String,
        /// Schema version for JSON contract
        #[arg(long, default_value = "1")]
        schema_version: String,
        /// Output file (- for stdout)
        #[arg(long, default_value = "-")]
        output: String,
    },
    /// Iterate entries in a section (JSONL output) from a .sav file
    IterSave {
        /// Path to .sav file
        path: String,
        /// Section name
        #[arg(long)]
        section: String,
        /// Schema version for JSON contract
        #[arg(long, default_value = "1")]
        schema_version: String,
        /// Output format
        #[arg(long, default_value = "jsonl")]
        format: String,
    },
    /// Extract sections from an already-extracted gamestate file (debug only)
    ExtractGamestate {
        /// Path to gamestate file
        path: String,
        /// Comma-separated section names
        #[arg(long)]
        sections: String,
        /// Schema version for JSON contract
        #[arg(long, default_value = "1")]
        schema_version: String,
        /// Output file (- for stdout)
        #[arg(long, default_value = "-")]
        output: String,
    },
    /// Start a session server (parse once, respond to multiple queries via stdin/stdout)
    Serve {
        /// Path to .sav file
        #[arg(long)]
        path: String,
    },
}

fn main() {
    // Custom error handling for clap to use exit code 3 for invalid arguments
    let cli = match Cli::try_parse() {
        Ok(cli) => cli,
        Err(e) => {
            // Print clap's formatted error message to stderr
            let _ = e.print();
            // Exit with code 3 for invalid arguments (per architecture spec)
            std::process::exit(3);
        }
    };

    let result = match cli.command {
        Commands::ExtractSave {
            path,
            sections,
            schema_version,
            output,
        } => commands::extract::run_save(&path, &sections, &schema_version, &output),
        Commands::IterSave {
            path,
            section,
            schema_version,
            format,
        } => commands::iter::run_save(&path, &section, &schema_version, &format),
        Commands::ExtractGamestate {
            path,
            sections,
            schema_version,
            output,
        } => commands::extract::run_gamestate(&path, &sections, &schema_version, &output),
        Commands::Serve { path } => commands::serve::run(&path),
    };

    if let Err(e) = result {
        error::handle_error(e);
    }
}
