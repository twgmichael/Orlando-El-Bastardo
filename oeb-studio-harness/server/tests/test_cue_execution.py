import importlib.util
import os
from pathlib import Path


def _find_tool_path(filename: str) -> Path:
    env_override = os.environ.get("OEB_TOOLS_DIR")
    candidates = []
    if env_override:
        candidates.append(Path(env_override) / filename)
    candidates.append(Path("/tools") / filename)
    for parent in Path(__file__).resolve().parents:
        candidates.append(parent / "tools" / "oeb_blender" / filename)

    for candidate in candidates:
        if candidate.is_file():
            return candidate

    raise FileNotFoundError(
        f"Could not locate tools/oeb_blender/{filename}. Set OEB_TOOLS_DIR to its "
        "containing directory if running outside the repo checkout or "
        "the oeb-studio-harness-local Docker stack."
    )


def load_module():
    spec = importlib.util.spec_from_file_location(
        "cue_execution_for_test",
        _find_tool_path("cue_execution.py"),
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_to_frame_converts_seconds_to_1_based_frame():
    module = load_module()
    assert module.to_frame(0.0, 24.0) == 1
    assert module.to_frame(1.0, 24.0) == 25
    assert module.to_frame(0.3, 24.0) == 8


def test_to_frame_rounds_to_nearest():
    module = load_module()
    assert module.to_frame(0.29, 24.0) == 8
    assert module.to_frame(0.27, 24.0) == 7
