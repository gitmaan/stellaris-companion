import os
import sys
from unittest.mock import patch
import pytest
from pathlib import Path

# Ensure the app's root directory is in the Python path
# to allow for correct module imports in the test environment.
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Since we're testing the CLI, we import the main function.
from v2_native_tools import main

@pytest.fixture(autouse=True)
def mock_dependencies():
    """
    Mocks dependencies that are not relevant to the CLI command tests,
    such as file loading and the Companion object initialization.
    This allows tests to run without a real save file or API key.
    """
    with patch('save_loader.find_most_recent_save', return_value=Path('dummy_save.sav')), \
         patch('pathlib.Path.exists', return_value=True), \
         patch('v2_native_tools.Companion') as MockCompanion:
        # Configure the mock Companion instance
        mock_instance = MockCompanion.return_value
        mock_instance.metadata = {'name': 'Test Empire', 'date': '2200.01.01', 'version': '1.0'}
        mock_instance.personality_summary = "A test personality."
        yield

@pytest.fixture
def cleanup_feedback_log():
    """Ensures feedback.log is removed after a test run."""
    yield
    if os.path.exists("feedback.log"):
        os.remove("feedback.log")

def test_feedback_command(capsys, cleanup_feedback_log):
    """
    Tests if the /feedback command writes the provided message to feedback.log
    and prints a confirmation to the console.
    """
    feedback_message = "This is a test feedback message."
    # Simulate user typing the feedback command and then quitting.
    user_inputs = [f"/feedback {feedback_message}", "/quit"]

    with patch('builtins.input', side_effect=user_inputs):
        # We expect the main loop to exit gracefully when it runs out of input.
        try:
            main()
        except StopIteration:
            # This is expected when the mocked input is exhausted.
            pass

    # Verify console output for the user.
    captured = capsys.readouterr()
    assert "Feedback submitted. Thank you!" in captured.out

    # Verify file content.
    assert os.path.exists("feedback.log")
    with open("feedback.log", "r") as f:
        log_content = f.read()
        assert feedback_message in log_content
        assert "[2200.01.01]" in log_content

def test_feedback_command_no_message(capsys, cleanup_feedback_log):
    """
    Tests if the /feedback command shows usage instructions
    when no message is provided.
    """
    # Simulate user typing the feedback command without a message, then quitting.
    user_inputs = ["/feedback", "/quit"]

    with patch('builtins.input', side_effect=user_inputs):
        try:
            main()
        except StopIteration:
            pass

    # Verify the usage message is printed to the console.
    captured = capsys.readouterr()
    assert "Usage: /feedback <message>" in captured.out

    # Verify that the log file was not created.
    assert not os.path.exists("feedback.log")
