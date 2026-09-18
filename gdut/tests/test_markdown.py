import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from ingest import load_documents, split_pages, replace_collection
from ingest_md.ingest import load_sections, split_sections
from app.rag import PolicyRAG


def write_pdf(path):
    from pypdf import PdfWriter
    from pypdf.generic import DictionaryObject, NameObject, DecodedStreamObject
    writer = PdfWriter()
    writer.add_blank_page(width=300, height=300)
    page = writer.add_blank_page(width=300, height=300)
    font = DictionaryObject({NameObject('/Type'): NameObject('/Font'), NameObject('/Subtype'): NameObject('/Type1'), NameObject('/BaseFont'): NameObject('/Helvetica')})
    page[NameObject('/Resources')] = DictionaryObject({NameObject('/Font'): DictionaryObject({NameObject('/F1'): font})})
    stream = DecodedStreamObject()
    stream.set_data(b'BT /F1 12 Tf 10 100 Td (Policy for year two.) Tj ET')
    page[NameObject('/Contents')] = stream
    writer.write(path)


class MarkdownTests(unittest.TestCase):
    def test_utf8_hierarchy_and_original_content(self):
        with tempfile.TemporaryDirectory() as folder:
            Path(folder, '政策.MD').write_text('\ufeff# 奖学金\n总则\n## 申请条件\n大二条件\n### 材料 ###\n- 成绩单\n## 时间\n十月\n', encoding='utf-8')
            docs = load_sections(folder)
        self.assertEqual([d.metadata['section'] for d in docs], ['奖学金', '奖学金 > 申请条件', '奖学金 > 申请条件 > 材料', '奖学金 > 时间'])
        self.assertEqual(docs[2].page_content, '### 材料 ###\n- 成绩单')
        self.assertTrue(all(d.metadata['file_type'] == 'md' and 'page' not in d.metadata for d in docs))

    def test_preamble_no_heading_blank_and_fenced_code(self):
        self.assertEqual(split_sections('纯文本政策', 'a.md')[0].metadata['section'], '正文')
        self.assertEqual(split_sections(' \n\t', 'a.md'), [])
        docs = split_sections('前言\n# 标题\n```md\n## 示例标题\n```\n~~~\n# 示例\n~~~\n#### 四级正文\n内容\n', 'a.md')
        self.assertEqual([d.metadata['section'] for d in docs], ['正文', '标题'])
        self.assertIn('## 示例标题', docs[1].page_content)
        self.assertIn('#### 四级正文', docs[1].page_content)

    def test_empty_and_bad_encoding(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder, 'a.md')
            path.write_text(' \n', encoding='utf-8')
            self.assertEqual(load_sections(folder, allow_empty=True), [])
            with self.assertRaisesRegex(ValueError, '未更新'):
                load_sections(folder)
            path.write_bytes(b'\xff\xfeinvalid')
            with self.assertRaisesRegex(ValueError, 'UTF-8'):
                load_sections(folder)

    def test_markdown_only_and_duplicate_basenames(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'md').mkdir()
            (root / 'md' / 'policy.md').write_text('# 政策\n正文', encoding='utf-8')
            self.assertEqual(len(load_documents(root)), 1)
            (root / 'policy.md').write_text('旧目录资料', encoding='utf-8')
            docs = load_documents(root)
            self.assertEqual({d.metadata['source'] for d in docs}, {'policy.md', 'md/policy.md'})

    def test_split_keeps_section_and_token_limit(self):
        docs = split_sections('# 规则\n' + '申请政策。' * 200 + '\n## 时间\n十月', 'a.md')
        tokenizer = Mock()
        tokenizer.encode.side_effect = lambda text, **kwargs: list(text)
        chunks = split_pages(docs, tokenizer)
        self.assertTrue(all(len(c.page_content) <= 400 for c in chunks))
        self.assertEqual({c.metadata['section'] for c in chunks}, {'规则', '规则 > 时间'})
        self.assertTrue(all('page' not in c.metadata for c in chunks))

    def test_mixed_rebuild_delete_and_empty_preserve_index(self):
        import chromadb
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'pdf').mkdir()
            (root / 'md').mkdir()
            write_pdf(root / 'pdf' / 'policy.pdf')
            (root / 'md' / 'policy.md').write_text('# 申请\n条件', encoding='utf-8')
            (root / 'legacy.md').write_text('旧位置文档', encoding='utf-8')
            client = chromadb.EphemeralClient()
            client.get_or_create_collection('unrelated')
            docs = load_documents(root)
            self.assertEqual(len(docs), 3)
            self.assertEqual(next(d for d in docs if d.metadata['file_type'] == 'pdf').metadata['page'], 2)
            for _ in range(2):
                replace_collection(client, docs, [[1., 0.]] * len(docs))
            self.assertEqual(client.get_collection('campus_policy').count(), 3)
            (root / 'md' / 'policy.md').unlink()
            (root / 'legacy.md').unlink()
            docs = load_documents(root)
            replace_collection(client, docs, [[1., 0.]] * len(docs))
            self.assertEqual({m['file_type'] for m in client.get_collection('campus_policy').get()['metadatas']}, {'pdf'})
            (root / 'pdf' / 'policy.pdf').unlink()
            # Verify the actual orchestrator never touches the old index on empty input.
            with patch('ingest.load_environment'), patch('ingest.load_documents', side_effect=lambda _: load_documents(root)), patch('ingest.embeddings') as encoder:
                from ingest import main
                with self.assertRaisesRegex(ValueError, '未更新'):
                    main()
                encoder.assert_not_called()
            self.assertEqual(client.get_collection('campus_policy').count(), 1)
            self.assertIsNotNone(client.get_collection('unrelated'))

    def test_api_followup_mixed_citations(self):
        from fastapi.testclient import TestClient
        from app.server import create_app
        from langchain_core.documents import Document
        store, llm = Mock(), Mock()
        store.similarity_search.return_value = [
            Document(page_content='PDF 条款', metadata={'source': 'policy.pdf', 'page': 2}),
            *split_sections('# 申请条件\n大二条款', 'policy.md'),
        ]
        llm.invoke.side_effect = [SimpleNamespace(content='大二申请条件？'), SimpleNamespace(content='符合条件。')]
        with TestClient(create_app(PolicyRAG(store, llm, '规则 {context}'), with_gradio=False)) as client:
            result = client.post('/api/chat', json={'message': '那大二呢？', 'history': [
                {'role': 'user', 'content': '大一申请条件？'}, {'role': 'assistant', 'content': '大一条款'}]})
        self.assertEqual(result.status_code, 200)
        sources = result.json()['sources']
        self.assertEqual(sources[0]['label'], 'policy.pdf，第 2 页')
        self.assertEqual(sources[1]['label'], 'policy.md，章节：申请条件')
        self.assertNotIn('page', sources[1])
        self.assertIn('# 申请条件', sources[1]['text'])
        messages = llm.invoke.call_args.args[0]
        self.assertIn('【policy.md，章节：申请条件】', messages[0][1])
        self.assertEqual(messages[-1], ('human', '那大二呢？'))
        store.similarity_search.assert_called_once_with('大二申请条件？', k=4)


if __name__ == '__main__':
    unittest.main()
