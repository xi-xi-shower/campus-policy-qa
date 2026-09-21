import json
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from ingest import split_pages, load_documents
from ingest_md.handbook import HANDBOOK, split_handbook


class HandbookTests(unittest.TestCase):
    def test_chapter_section_h5_and_continuation(self):
        text = ("### 普通高等学校学生管理规定\n##### 第三章 学籍管理\n"
                "##### 第一节 入学与注册\n第十条 保留资格，参考第十一条。\n"
                "第十一条 复查。\n" + "复查内容。" * 150 +
                "\n##### 第二节 考核\n第十三条 考核成绩。\n")
        docs = split_handbook(text, apply_mapping=False)
        by_id = {d.metadata['doc_id']: d for d in docs if 'doc_id' in d.metadata}
        self.assertEqual(set(by_id), {'gdut26-sm-ch03-s01-a010', 'gdut26-sm-ch03-s01-a011',
                                      'gdut26-sm-ch03-s02-a013'})
        tokenizer = Mock()
        tokenizer.encode.side_effect = lambda text, **kwargs: list(text)
        chunks = split_pages([by_id['gdut26-sm-ch03-s01-a011']], tokenizer)
        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(d.metadata['doc_id'] == 'gdut26-sm-ch03-s01-a011' for d in chunks))
        self.assertTrue(all(len(d.page_content) <= 400 for d in chunks))

    def test_reference_in_body_does_not_replace_article_id(self):
        docs = split_handbook('### 普通高等学校学生管理规定\n##### 第一章 总则\n'
                              '第四条 依照第十一条规定处理。\n第五条 权益。', apply_mapping=False)
        ids = [d.metadata['doc_id'] for d in docs if 'doc_id' in d.metadata]
        self.assertEqual(ids, ['gdut26-sm-ch01-a004', 'gdut26-sm-ch01-a005'])

    def test_source_changes_fail_closed(self):
        with self.assertRaisesRegex(ValueError, 'Handbook changed'):
            split_handbook('changed source')

    def test_same_handbook_pdf_is_not_indexed_twice(self):
        import tempfile
        from langchain_core.documents import Document
        with tempfile.TemporaryDirectory() as folder:
            with patch('ingest.load_pages', side_effect=[[
                Document(page_content='duplicate', metadata={'source': HANDBOOK.replace('.md', '.pdf'), 'file_type': 'pdf'}),
                Document(page_content='other', metadata={'source': 'other.pdf', 'file_type': 'pdf'})], []]), \
                 patch('ingest.load_sections', side_effect=[[], [
                     Document(page_content='reviewed', metadata={'source': HANDBOOK, 'file_type': 'md'})]]):
                docs = load_documents(folder)
        self.assertEqual([d.page_content for d in docs], ['other', 'reviewed'])

    def test_local_handbook_matches_all_map_boundaries(self):
        path = Path(__file__).parents[1] / 'docs' / 'md' / HANDBOOK
        if not path.exists():
            self.skipTest('Local handbook not installed')
        docs = split_handbook(path.read_text(encoding='utf-8-sig'))
        ids = [d.metadata['doc_id'] for d in docs if 'doc_id' in d.metadata]
        self.assertEqual(len(ids), len(set(ids)))
        mapping = json.loads((Path(__file__).parents[1] / 'ingest_md/handbook_map.json').read_text(encoding='utf-8'))
        self.assertTrue({g['id'] for g in mapping['groups']} <= set(ids))
        pet = next(d for d in docs if d.metadata.get('doc_id') == 'gdut26-dorm-ch03-a014')
        self.assertIn('禁止在宿舍区内饲养宠物', pet.page_content)


if __name__ == '__main__':
    unittest.main()
