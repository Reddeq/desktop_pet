import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'src'))
from updater import extract_zip, is_update_available, version_tuple


class UpdaterTests(unittest.TestCase):
    def test_version_padding_and_invalid_release(self):
        self.assertEqual(version_tuple(' v1.2 '), version_tuple('1.2.0'))
        with patch('updater.get_latest_release_info', return_value={'version': '1.2-rc1'}):
            self.assertEqual(is_update_available(), (False, None))

    def test_unique_staging_and_bad_members(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive = root / 'update.zip'
            with zipfile.ZipFile(archive, 'w') as output:
                output.writestr('DesktopPet.exe', 'test fixture')
            with patch('updater.tempfile.mkdtemp', side_effect=[str(root / 'one'), str(root / 'two')]):
                first = extract_zip(str(archive))
                second = extract_zip(str(archive))
            self.assertNotEqual(first, second)
            self.assertTrue((Path(first) / 'DesktopPet.exe').is_file())
            for member in ['../outside.txt', '/absolute.txt', 'C:/absolute.txt', 'folder/../../bad']:
                with self.subTest(member=member):
                    with zipfile.ZipFile(archive, 'w') as output:
                        output.writestr(member, 'bad')
                    staging = root / 'bad-staging'
                    staging.mkdir()
                    with patch('updater.tempfile.mkdtemp', return_value=str(staging)):
                        self.assertIsNone(extract_zip(str(archive)))
                    self.assertFalse(staging.exists())


if __name__ == '__main__':
    unittest.main()
