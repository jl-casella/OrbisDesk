"""The gp4 orbis_package writes for an embedded runtime: escaped paths, every folder, sources outside app/."""
from pathlib import Path
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from orbis_package import write_gp4


class Gp4Tests(unittest.TestCase):
    def test_paths_with_spaces_and_markup_round_trip(self):
        files = [('eboot.bin', 'eboot.bin'),
                 ('runtime/wine-prefix/drive_c/Program Files/A & B/x "y" <z>.txt',
                  '../runtime/wine-prefix/drive_c/Program Files/A & B/x "y" <z>.txt')]
        directories = {'sce_sys/about', 'runtime/wine-prefix/drive_c/Program Files/A & B', 'runtime/wine-home'}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'pkg.gp4'
            write_gp4(path, 'IV0000-ORBW00002_00-ORBISWINW0010000', files, directories, '2026-11-09 00:00:00')
            root = ET.parse(path).getroot()
        listed = {(f.get('targ_path'), f.get('orig_path')) for f in root.iter('file')}
        self.assertEqual(listed, set(files))
        self.assertEqual(root.find('volume/package').get('content_id'), 'IV0000-ORBW00002_00-ORBISWINW0010000')

        def folders(node, prefix=''):
            for child in node.findall('dir'):
                name = prefix + child.get('targ_name')
                yield name
                yield from folders(child, name + '/')
        found = set(folders(root.find('rootdir')))
        # every declared folder and each of its parents, empty ones included
        for name in directories:
            parts = name.split('/')
            for depth in range(1, len(parts) + 1):
                self.assertIn('/'.join(parts[:depth]), found)


if __name__ == '__main__':
    unittest.main()
