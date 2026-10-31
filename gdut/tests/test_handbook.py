import hashlib
import re
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from ingest import split_pages, load_documents
from ingest_md.handbook import ANNOTATION_VERSION, HANDBOOK, split_handbook


class HandbookTests(unittest.TestCase):
    def test_chapter_section_h5_and_continuation(self):
        text = ("### 普通高等学校学生管理规定\n##### 第三章 学籍管理\n"
                "##### 第一节 入学与注册\n第十条 保留资格，参考第十一条。\n"
                "第十一条 复查。\n" + "复查内容。" * 150 +
                "\n##### 第二节 考核\n第十三条 考核成绩。\n")
        docs = split_handbook(text)
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
                              '第四条 依照 第十一条 规定处理。\n第五条 权益。')
        ids = [d.metadata['doc_id'] for d in docs if 'doc_id' in d.metadata]
        self.assertEqual(ids, ['gdut26-sm-ch01-a004', 'gdut26-sm-ch01-a005'])

    def test_chapterless_articles_are_separate_and_track_source_changes(self):
        text = ('### 广东工业大学全日制本科学生奖学金评定办法\n'
                '第四条 奖学金项目。\n第五条 奖金标准。\n')
        docs = split_handbook(text)
        articles = [d for d in docs if 'doc_id' in d.metadata]
        self.assertEqual([d.metadata['doc_id'] for d in articles],
                         ['gdut26-scholarship-a004', 'gdut26-scholarship-a005'])
        self.assertEqual(articles[0].page_content, '第四条 奖学金项目。')
        self.assertTrue(all(d.metadata['annotation_version'] == ANNOTATION_VERSION for d in docs))
        self.assertTrue(all(d.metadata['source_sha256'] == hashlib.sha256(text.encode()).hexdigest()
                            for d in docs))
        changed = split_handbook(text.replace('奖金标准。', '新的奖金标准。'))
        self.assertNotEqual(docs[0].metadata['source_sha256'], changed[0].metadata['source_sha256'])

    def test_duplicate_article_ids_are_rejected(self):
        with self.assertRaisesRegex(ValueError, 'Duplicate handbook article ID'):
            split_handbook('### 普通高等学校学生管理规定\n##### 第一章 总则\n'
                           '第一条 原文。\n第一条 重复。')

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

    def test_local_handbook_covers_dataset_articles_without_groups(self):
        path = Path(__file__).parents[1] / 'docs' / 'md' / HANDBOOK
        if not path.exists():
            self.skipTest('Local handbook not installed')
        docs = split_handbook(path.read_text(encoding='utf-8-sig'))
        ids = [d.metadata['doc_id'] for d in docs if 'doc_id' in d.metadata]
        self.assertEqual(len(ids), len(set(ids)))
        import yaml
        dataset = Path(__file__).parents[2] / 'rag_eval/evals/datasets/guangdong_university_2026_rag_eval.md'
        samples = yaml.safe_load(re.search(r'```yaml\s*(.*?)\s*```', dataset.read_text(encoding='utf-8'), re.S)[1])
        required = {doc_id for row in samples for doc_id in row['relevant_doc_ids']}
        self.assertTrue(required <= set(ids), required - set(ids))
        self.assertTrue(all(re.search(r'-a\d{3}$', doc_id) for doc_id in ids))
        self.assertIn('gdut26-scholarship-a004', ids)
        self.assertIn('gdut26-dorm-ch06-a031', ids)
        self.assertIn('gdut26-dorm-ch06-a032', ids)
        pet = next(d for d in docs if d.metadata.get('doc_id') == 'gdut26-dorm-ch03-a014')
        self.assertIn('禁止在宿舍区内饲养宠物', pet.page_content)


if __name__ == '__main__':
    unittest.main()
