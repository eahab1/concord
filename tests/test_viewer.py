import json
from pathlib import Path
import pytest

from concord.cli import main, digest
from concord.config import Design, load
from concord.viewer import attach_result

ROOT = Path(__file__).resolve().parents[1]


def campaign(tmp_path):
    out = tmp_path / "proposals"
    assert main(["propose", str(ROOT / "configs/baseline.yaml"), "--count", "2", "--out", str(out)]) == 0
    return out


def fixture_response(design):
    angles = list(range(-90, 91, 5))
    return {"design_sha256": digest(design), "solver": "TEST FIXTURE ONLY", "analysis_status": "mesh_converged",
            "frequencies_hz": design.manual.frequencies_hz, "angles_deg": angles,
            "horizontal_db": [[-6 * (a / 45)**2 for a in angles] for _ in design.manual.frequencies_hz],
            "vertical_db": [[-6 * (a / 5)**2 for a in angles] for _ in design.manual.frequencies_hz]}


def test_campaign_viewer_and_incremental_publication(tmp_path, monkeypatch):
    import concord.cli as cli
    original = cli.publish
    seen = []
    def observe(out, state):
        seen.append((len(state["candidates"]), state["status"]))
        original(out, state)
    monkeypatch.setattr(cli, "publish", observe)
    out = campaign(tmp_path)
    assert seen == [(1, "generating"), (2, "generating"), (2, "complete")]
    state = json.loads((out / "viewer-state.json").read_text())
    assert state["total"] == 2
    assert (out / "viewer.html").exists()
    for record in [state["baseline"], *state["candidates"]]:
        assert record["result"] is None
        assert digest(load(out / record["config"])) == record["design_sha256"]
        script = (out / "previews" / (record["id"] + ".js")).read_text()
        assert script.startswith("window.concordMesh(")
        assert record["design_sha256"] in script
    assert "https://" not in (out / "viewer.html").read_text()


def test_attach_result_persists_and_rejects_mismatched_results(tmp_path):
    out = campaign(tmp_path)
    design = load(out / "candidate-0000.yaml")
    result = tmp_path / "response.json"
    response = fixture_response(design)
    result.write_text(json.dumps(response))
    assert attach_result(out, "candidate-0000", result)["objective"] == pytest.approx(0)
    state = json.loads((out / "viewer-state.json").read_text())
    assert state["candidates"][0]["result"]["response"]["solver"] == "TEST FIXTURE ONLY"
    assert state["candidates"][1]["result"] is None
    before = (out / "viewer-state.json").read_bytes()
    with pytest.raises(ValueError, match="hash"):
        attach_result(out, "candidate-0001", result)
    response["synthetic"] = True
    result.write_text(json.dumps(response))
    with pytest.raises(ValueError, match="Synthetic"):
        attach_result(out, "candidate-0000", result)
    assert (out / "viewer-state.json").read_bytes() == before
    with pytest.raises(ValueError, match="Candidate"):
        attach_result(out, "../../escape", result)


def test_build_viewer_uses_full_exported_mesh(tmp_path):
    out = tmp_path / "build"
    assert main(["build", str(ROOT / "configs/baseline.yaml"), "--out", str(out)]) == 0
    state = json.loads((out / "viewer-state.json").read_text())
    assert state["baseline"]["triangles"] == 3136
    assert state["baseline"]["resolution"] == "Full exported concept mesh"
    assert state["baseline"]["config"] == "resolved.yaml"
    assert main(["view", str(tmp_path / "missing")]) == 2
