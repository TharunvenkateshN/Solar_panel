"""Classifier adapter: simulated stand-in now, trained .joblib model later."""
import json

import joblib
import pytest
from sklearn.ensemble import RandomForestClassifier
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import LabelEncoder, StandardScaler

from conftest import make_engine, run, ticks
from app.config import SimConfig
from app.ml.features import FEATURE_COLS
from app.ml.joblib_model import MODEL_FILE, JoblibClassifier
from app.ml.loader import load_classifier

CLASSES = ["Healthy_Clean", "Partial_Shading", "Soiling_Dusty"]


def test_missing_model_falls_back_to_simulated_with_visible_reason(models_dir):
    clf, info = load_classifier(models_dir, SimConfig())
    assert info["mode"] == "simulated" and "not found" in info["fallback_reason"]


def test_model_required_but_missing_is_unavailable_not_simulated(models_dir):
    clf, info = load_classifier(models_dir, SimConfig(), "model")
    assert info["mode"] == "unavailable" and info["error"]


async def _collect_training_rows(tmp_path):
    rows, labels = [], []
    for sid, label in (("healthy", "Healthy_Clean"), ("soiled", "Soiling_Dusty"), ("shading", "Partial_Shading")):
        e = await make_engine(tmp_path, sid, auto=False)
        for _ in range(8):
            e.tick(); await e.wait_idle()
            f = e.last_result["features"]["iv_features"]
            rows.append([f[c] for c in FEATURE_COLS]); labels.append(label)
    return rows, labels


def _write_model(models_dir, rows, labels, schema_cols=None, classes_override=None):
    le = LabelEncoder().fit(classes_override or labels)
    pipe = Pipeline([("scaler", StandardScaler()), ("clf", RandomForestClassifier(n_estimators=30, random_state=0))])
    pipe.fit(rows, le.transform(labels))
    joblib.dump({"pipe": pipe, "label_encoder": le, "feature_cols": FEATURE_COLS}, models_dir / MODEL_FILE)
    (models_dir / "model_metadata.json").write_text(json.dumps(
        {"model_name": "Random_Forest", "classes": list(le.classes_), "n_training_samples": len(rows),
         "loo_accuracy": 0.0, "CAVEATS": ["test model"]}))
    (models_dir / "feature_schema.json").write_text(json.dumps({"feature_cols": schema_cols or FEATURE_COLS}))


def test_trained_model_dropped_in_is_used_by_the_pipeline(tmp_path, models_dir):
    """The integration path for the real model: same files the notebook writes, no code changes."""
    async def go():
        rows, labels = await _collect_training_rows(tmp_path)
        _write_model(models_dir, rows, labels)
        e = await make_engine(tmp_path, "soiled", auto=False)
        e.models_dir = models_dir
        info = e.reload_classifier()
        assert info["mode"] == "trained_model" and info["name"] == "Random_Forest"
        await ticks(e, 2)
        ml = e.last_result["ml"]
        assert ml["mode"] == "trained_model"
        assert ml["label"] in CLASSES                      # whatever the model says is reported as-is
        assert ml["confidence"] is not None and 0 < ml["confidence"] <= 1
        assert set(ml["probabilities"]) == set(CLASSES)
        st = {s["id"]: s for s in e.stages()}["ml"]
        assert st["details"]["Mode"] == "Trained model"
    run(go())


def test_corrupt_model_file_is_visible_and_never_replaced_by_a_guess(tmp_path, models_dir):
    async def go():
        (models_dir / MODEL_FILE).write_bytes(b"not a joblib file")
        e = await make_engine(tmp_path, "soiled", auto=False)
        e.models_dir = models_dir
        info = e.reload_classifier()
        assert info["mode"] == "unavailable" and "Could not load" in info["error"]
        await ticks(e, 2)
        r = e.last_result
        assert r["ml"]["label"] is None and r["decision"]["ml_class"] == "MODEL_UNAVAILABLE"
        assert r["decision"]["final_status"] == "MODEL_UNAVAILABLE" and r["decision"]["recommended_action"] == "MODEL_UNAVAILABLE"
        assert e.history[-1]["action"] == "MODEL_UNAVAILABLE"
    run(go())


def test_hotspot_alert_still_raised_when_model_unavailable(tmp_path, models_dir):
    async def go():
        (models_dir / MODEL_FILE).write_bytes(b"junk")
        e = await make_engine(tmp_path, "hotspot", auto=False)
        e.models_dir = models_dir
        e.reload_classifier(); await ticks(e, 1)
        assert e.last_result["decision"]["recommended_action"] == "HOTSPOT_ALERT"
    run(go())


def test_model_with_wrong_classes_is_rejected(models_dir):
    rows = [[float(i + j) for j in range(len(FEATURE_COLS))] for i in range(6)]
    labels = ["Healthy_Clean", "Healthy_Clean", "Hotspot", "Hotspot", "Soiling_Dusty", "Soiling_Dusty"]
    _write_model(models_dir, rows, labels)
    clf, info = load_classifier(models_dir, SimConfig())
    assert info["mode"] == "unavailable" and "do not match" in info["error"]


def test_schema_mismatch_is_rejected(models_dir):
    rows = [[float(i + j) for j in range(len(FEATURE_COLS))] for i in range(6)]
    labels = CLASSES * 2
    _write_model(models_dir, rows, labels, schema_cols=FEATURE_COLS[:-1])
    clf, info = load_classifier(models_dir, SimConfig())
    assert info["mode"] == "unavailable" and "feature_schema" in info["error"]


def test_inference_failure_returns_error_prediction_not_exception(models_dir):
    rows = [[float(i + j) for j in range(len(FEATURE_COLS))] for i in range(6)]
    _write_model(models_dir, rows, CLASSES * 2)
    clf = JoblibClassifier.load(models_dir)
    pred = clf.predict({"iv_features": {"Voc": 1.0}})            # missing features
    assert pred.label is None and "missing features" in pred.error


def test_force_simulated_even_when_model_exists(models_dir):
    rows = [[float(i + j) for j in range(len(FEATURE_COLS))] for i in range(6)]
    _write_model(models_dir, rows, CLASSES * 2)
    clf, info = load_classifier(models_dir, SimConfig(), "simulated")
    assert info["mode"] == "simulated"


def test_feature_bundle_has_the_notebook_schema(tmp_path):
    async def go():
        e = await make_engine(tmp_path, "healthy", auto=False)
        f = e.last_result["features"]["iv_features"]
        assert list(f) == FEATURE_COLS and len(f) == 19
        assert f["Pmpp"] == pytest.approx(e.last_result["electrical"]["power_W"], rel=0.08)
        assert f["Voc"] > f["Vmpp"] > 0 and f["Isc"] > f["Impp"] > 0
        assert f["Irradiance"] > 0 and 20 < f["Temperature"] < 80
    run(go())
