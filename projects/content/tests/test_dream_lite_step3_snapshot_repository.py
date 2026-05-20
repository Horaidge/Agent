from __future__ import annotations

import unittest

from storage.dream_lite_step3_snapshot_repository import DreamLiteStep3SnapshotRepository


class _FakeUpdateResult:
    acknowledged = True


class _FakeCollection:
    def __init__(self) -> None:
        self.docs: dict[str, dict] = {}

    def update_one(self, flt: dict, update: dict, upsert: bool = False) -> _FakeUpdateResult:
        doc_id = str(flt.get("_id"))
        base = self.docs.get(doc_id, {"_id": doc_id})
        patch = dict(update.get("$set") or {})
        base.update(patch)
        self.docs[doc_id] = base
        return _FakeUpdateResult()

    def find_one(self, flt: dict) -> dict | None:
        return self.docs.get(str(flt.get("_id")))


class DreamLiteStep3SnapshotRepositoryTests(unittest.TestCase):
    def test_upsert_and_get_latest(self) -> None:
        repo = DreamLiteStep3SnapshotRepository(_FakeCollection())  # type: ignore[arg-type]
        ok = repo.upsert_latest_sync(
            user_id=7,
            payload={"frames_for_step4_json": [{"index": 0}], "environments_text": "env"},
            updated_by="test",
        )
        self.assertTrue(ok)
        snap = repo.get_latest_sync(user_id=7)
        self.assertIsNotNone(snap)
        self.assertEqual((snap or {}).get("environments_text"), "env")
        self.assertEqual((snap or {}).get("updated_by"), "test")


if __name__ == "__main__":
    unittest.main()
