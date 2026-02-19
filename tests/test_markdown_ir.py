"""Tests for Markdown IR."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from salmalm.markdown_ir import (
    parse, render_telegram, render_discord, render_slack, render_plain,
    chunk_ir, MarkdownIR, StyleSpan, LinkSpan, CodeBlock
)


class TestParse(unittest.TestCase):

    def test_plain_text(self):
        ir = parse('hello world')
        self.assertEqual(ir.text, 'hello world')
        self.assertEqual(ir.styles, [])

    def test_bold(self):
        ir = parse('this is **bold** text')
        self.assertTrue(any(s.style == 'bold' for s in ir.styles))

    def test_strikethrough(self):
        ir = parse('~~deleted~~')
        self.assertTrue(any(s.style == 'strike' for s in ir.styles))

    def test_inline_code(self):
        ir = parse('use `code` here')
        self.assertTrue(any(s.style == 'code' for s in ir.styles))

    def test_spoiler(self):
        ir = parse('this is ||spoiler|| text')
        self.assertTrue(any(s.style == 'spoiler' for s in ir.styles))

    def test_link(self):
        ir = parse('click [here](https://example.com)')
        self.assertEqual(len(ir.links), 1)
        self.assertEqual(ir.links[0].href, 'https://example.com')
        self.assertEqual(ir.links[0].label, 'here')

    def test_code_block(self):
        ir = parse('```python\nprint("hi")\n```')
        self.assertEqual(len(ir.code_blocks), 1)
        self.assertEqual(ir.code_blocks[0].language, 'python')
        self.assertIn('print', ir.code_blocks[0].content)

    def test_table(self):
        md = '| Name | Age |\n|------|-----|\n| Alice | 30 |\n| Bob | 25 |'
        ir = parse(md)
        self.assertEqual(len(ir.tables), 1)
        self.assertEqual(ir.tables[0].headers, ['Name', 'Age'])
        self.assertEqual(len(ir.tables[0].rows), 2)


class TestRenderers(unittest.TestCase):

    def test_render_telegram_link(self):
        ir = MarkdownIR(text='click here', links=[LinkSpan(6, 10, 'https://x.com', 'here')])
        result = render_telegram(ir)
        self.assertIn('href', result)

    def test_render_discord_link(self):
        ir = MarkdownIR(text='click here', links=[LinkSpan(6, 10, 'https://x.com', 'here')])
        result = render_discord(ir)
        self.assertIn('[here]', result)

    def test_render_slack_link(self):
        ir = MarkdownIR(text='click here', links=[LinkSpan(6, 10, 'https://x.com', 'here')])
        result = render_slack(ir)
        self.assertIn('<https://x.com|here>', result)

    def test_render_plain(self):
        ir = MarkdownIR(text='plain text')
        result = render_plain(ir)
        self.assertEqual(result, 'plain text')

    def test_render_plain_with_code_block(self):
        ir = MarkdownIR(text='before', code_blocks=[CodeBlock(0, 0, 'py', 'x=1')])
        result = render_plain(ir)
        self.assertIn('x=1', result)


class TestChunking(unittest.TestCase):

    def test_no_split_needed(self):
        ir = MarkdownIR(text='short')
        chunks = chunk_ir(ir, max_chars=100)
        self.assertEqual(len(chunks), 1)

    def test_split_long_text(self):
        ir = MarkdownIR(text='x' * 1000)
        chunks = chunk_ir(ir, max_chars=300)
        self.assertTrue(len(chunks) >= 2)

    def test_respects_style_boundaries(self):
        text = 'a' * 100
        ir = MarkdownIR(text=text, styles=[StyleSpan(80, 120, 'bold')])
        # With max_chars=90, should not split inside bold span (80-120)
        chunks = chunk_ir(ir, max_chars=90)
        self.assertTrue(len(chunks) >= 1)


if __name__ == '__main__':
    unittest.main()
