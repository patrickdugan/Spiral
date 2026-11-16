import hashlib
import json
from pathlib import Path
import runpy
import tempfile
import unittest

ROOT=Path(__file__).resolve().parent.parent
export_pages=runpy.run_path(str(ROOT/'scripts/build-pages.py'))['export_pages']


class StaticExportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        (ROOT/'.runtime').mkdir(exist_ok=True)

    def test_public_export_is_allowlisted_and_works_under_a_project_subpath(self):
        (ROOT/'.runtime').mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ROOT/'.runtime') as directory:
            target=Path(directory)/'site'
            export_pages(target)
            self.assertEqual({p.relative_to(target).as_posix() for p in target.rglob('*') if p.is_file()},
                {'index.html','styles.css','icon.svg','app.js','hosted.js','demo-data.json','.nojekyll',
                 'results/cashu-ark-integration.json','results/cashu-ark-exit-integration.json'})
            html=(target/'index.html').read_text(encoding='utf-8')
            self.assertNotIn('src="/',html);self.assertNotIn('href="/',html)
            self.assertIn('Hosted fixture demo',html)
            self.assertLess(html.index('./hosted.js'),html.index('./app.js'))
            self.assertIn('id="ark-connection" hidden',html)
            data=json.loads((target/'demo-data.json').read_text(encoding='utf-8'))
            self.assertEqual(len(data['runs']),8);self.assertEqual(len(data['plans']),376)
            self.assertEqual(data['status']['hosting'],'static-fixtures')
            for archive in data['archives'].values():
                self.assertEqual(hashlib.sha256(archive['text'].encode()).hexdigest(),archive['manifest']['sha256'])
                self.assertNotIn('beneficiary',archive['text'])

    def test_export_refuses_to_mix_existing_files_into_a_public_bundle(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'.runtime') as directory:
            target=Path(directory);private=target/'wallet.sqlite';private.write_bytes(b'private')
            with self.assertRaisesRegex(ValueError,'empty'):
                export_pages(target)
            self.assertEqual(private.read_bytes(),b'private')
