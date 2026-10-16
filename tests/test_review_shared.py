"""Persistence and approval invariants common to both demos."""
import hashlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from fastapi import HTTPException

from webui import review


def test_snapshot_approval_and_export(tmp_path, monkeypatch):
    monkeypatch.setattr(review, "STORE", tmp_path)
    source = review._source("base_act/eng/tranfer_of_teachers.xml")
    original = source.read_bytes()
    draft = review.create(review.Start(path="base_act/eng/tranfer_of_teachers.xml"))
    folder = tmp_path / draft["id"]
    assert (folder / "source.xml").read_bytes() == original
    assert draft["source_sha256"] == hashlib.sha256(original).hexdigest()
    with pytest.raises(HTTPException) as exc:
        review.export(draft["id"])
    assert exc.value.status_code == 409
    with pytest.raises(HTTPException) as exc:
        review.approve(draft["id"], review.Approval(revision=1, reviewer="Lawyer"))
    assert exc.value.status_code == 409
    approval = review.approve(draft["id"], review.Approval(revision=0, reviewer="Lawyer"))
    assert approval["approval"]["reviewer"] == "Lawyer"
    assert (folder / "approved.xml").read_bytes() == original
    assert source.read_bytes() == original


def test_rejects_non_base_act_and_traversal():
    for path in ("../data/v0s/eng/BBMP-eng.pdf", "amendment/eng/First_ammendment.xml"):
        with pytest.raises(HTTPException) as exc:
            review._source(path)
        assert exc.value.status_code == 404
