import sys
from pathlib import Path

# llm_utils requires Python>=3.12 in pyproject.toml but is compatible with 3.11.
# Add it to sys.path so tests don't need PYTHONPATH set externally.
sys.path.insert(0, str(Path(__file__).parent.parent / "llm_utils"))
