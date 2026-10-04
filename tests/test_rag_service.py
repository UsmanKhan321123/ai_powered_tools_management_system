import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import rag_service


class RagIndexingTests(unittest.TestCase):
    def test_index_text_document_persists_manifest_and_skips_unchanged_content(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            collection = Mock()
            embedding_model = Mock()
            embedding_model.encode.return_value.tolist.return_value = [[0.1, 0.2]]

            with (
                patch.object(rag_service, "DOCUMENTS_DIR", root / "manuals"),
                patch.object(rag_service, "CHROMA_DIR", root / "chroma"),
                patch.object(rag_service, "MANIFEST_PATH", root / "manifest.json"),
                patch.object(rag_service, "_get_collection", return_value=collection),
                patch.object(
                    rag_service,
                    "_get_embedding_model",
                    return_value=embedding_model,
                ),
            ):
                first = rag_service.index_text_document(
                    "manual.txt",
                    "Stop the machine before inspecting the cooling fan.",
                )
                second = rag_service.index_text_document(
                    "manual.txt",
                    "Stop the machine before inspecting the cooling fan.",
                )

                self.assertEqual(first["status"], "indexed")
                self.assertEqual(second["status"], "already_indexed")
                self.assertEqual(
                    rag_service.list_indexed_documents(),
                    [{"filename": "manual.txt", "chunks": 1}],
                )

            collection.add.assert_called_once()
            embedding_model.encode.assert_called_once()


if __name__ == "__main__":
    unittest.main()
