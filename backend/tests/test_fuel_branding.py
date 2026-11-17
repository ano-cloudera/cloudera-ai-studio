"""The demo logo is switched on and off without touching the AMP's own logo."""
from __future__ import annotations

import importlib.util
from pathlib import Path

SAMPLE = Path(__file__).resolve().parents[2] / "samples" / "fuel_distribution"


def _script():
    spec = importlib.util.spec_from_file_location("fuel_apply_branding", SAMPLE / "apply_branding.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_logo_is_a_real_image_and_the_default_logo_is_untouched() -> None:
    script = _script()
    assert script.LOGO.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
    assert script.DEFAULT_PUBLIC.name == "public"
    assert "demo" in script.URL and not script.URL.endswith("Logo.png")  # never the AMP's own file


def test_apply_copies_into_the_demo_folder_only_and_remove_takes_it_away(tmp_path) -> None:
    script = _script()
    (tmp_path / "Logo.png").write_bytes(b"own logo")
    lines = script.apply(tmp_path)
    target = tmp_path / "branding" / "demo" / "pertamina-logo.png"
    assert target.read_bytes() == script.LOGO.read_bytes()
    assert (tmp_path / "Logo.png").read_bytes() == b"own logo"
    assert any("NEXT_PUBLIC_PRODUCT_LOGO=/branding/demo/pertamina-logo.png" in line for line in lines)
    assert any("NEXT_PUBLIC_EMPTY_STATE_LOGO=" in line for line in lines)

    removed = script.apply(tmp_path, remove=True)
    assert not target.exists() and not target.parent.exists()
    assert (tmp_path / "Logo.png").read_bytes() == b"own logo"
    assert any("Unset" in line for line in removed)


def test_the_branding_script_runs_from_the_command_line(tmp_path, capsys) -> None:
    script = _script()
    assert script.main(["--public-dir", str(tmp_path)]) == 0
    assert (tmp_path / "branding" / "demo" / "pertamina-logo.png").exists()
    assert script.main(["--public-dir", str(tmp_path), "--remove"]) == 0
    assert not (tmp_path / "branding" / "demo").exists()
