"""System prompt composition tests.

Guards the "display contract" appended to the system prompt so the rich chat
rendering (tables, code fences, callouts, mermaid) stays discoverable by the
model.
"""
import sys
from pathlib import Path

# Make sure we can import app modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.agent.prompts.system import get_system_prompt


def test_system_prompt_is_formatted():
    prompt = get_system_prompt()
    assert "{workspace}" not in prompt
    assert "Your dedicated workspace is:" in prompt


def test_system_prompt_includes_display_contract():
    prompt = get_system_prompt()
    assert "Output & Display" in prompt
    # The console vocabulary the frontend renders:
    assert "**Tables**" in prompt
    assert "```mermaid" in prompt
    assert "[!NOTE]" in prompt
    assert "GitHub-flavored Markdown" in prompt
    assert "Do not emit raw HTML" in prompt