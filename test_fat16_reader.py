import unittest
from fat16_reader import Fat16Reader


class Fat16Test(unittest.TestCase):
    def setUp(self):
        self.reader = Fat16Reader("test.img", True)

    def test_print(self):
        # visual test
        self.reader.print_first_n_bytes(8)

    def test_reserved_sectors(self):
        self.assertEqual(self.reader._reserved_sectors, 1)

    def test_sector_size(self):
        self.assertEqual(self.reader._sector_size, 512)

    def test_cluster_size(self):
        self.assertEqual(self.reader._cluster_size, 1)

    def test_fat_offset(self):
        self.assertEqual(self.reader._fat_offset, 0x200)

    def test_fat_size(self):
        self.assertEqual(self.reader._fat_size, 32)

    def test_fat_copies(self):
        self.assertEqual(self.reader._fat_copies, 2)

    def test_root_directory_offset(self):
        self.assertEqual(self.reader._root_directory_offset, 0x8200)

    def test_root_directory_entries(self):
        self.assertEqual(self.reader._root_directory_entries, 512)

    def test_clusters_offset(self):
        self.assertEqual(self.reader._clusters_offset, 0xc200)

    def test_read_entry(self):
        entry = self.reader._read_entry(0x8200)
        self.assertEqual(entry.filename, "DUMMY")
        self.assertEqual(entry.extension, "")
        self.assertEqual(entry.attributes, ["volume_id"])
        self.assertEqual(entry.cluster_number, 0)
        self.assertEqual(entry.filesize, 0)

    def test_read_root_directory(self):
        entries = self.reader._read_directory(
            self.reader._root_directory_offset)
        self.assertEqual(len(entries), 4)
        self.assertEqual(entries[0].filename, "DUMMY")
        self.assertEqual(entries[1].filename, "TEST")
        self.assertEqual(entries[2].filename, "HELLO")
        self.assertEqual(entries[3].filename, "WORLD")

    def test_cd_get_cluster_list(self):
        entries = self.reader._read_directory(
            self.reader._root_directory_offset)
        list = self.reader._get_clusters_list(entries[1])
        self.assertEqual(list, [2])

    def test_cd(self):
        test_entries = self.reader.cd("TEST")
        self.assertEqual(len(test_entries), 4)
        self.assertEqual(test_entries[0].filename, ".")
        self.assertEqual(test_entries[1].filename, "..")
        self.assertEqual(test_entries[2].filename, "ONE")
        self.assertEqual(test_entries[3].filename, "TWO")

    def test_cd_parent(self):
        self.reader.cd("TEST")
        test_entries = self.reader.cd("..")
        self.assertEqual(test_entries[2].filename, "HELLO")

    def test_cd_self(self):
        test_entries = self.reader.cd("TEST")
        self.assertEqual(test_entries[0].filename, ".")
        test_entries = self.reader.cd(".")
        self.assertEqual(len(test_entries), 4)

    def test_no_such_directory(self):
        self.reader.do_print_on_commands = False
        self.assertRaises(Fat16Reader.NotADirectoryException, lambda: self.reader.cd(""))

    def test_open_file(self):
        entries = self.reader.cd("TEST")
        file = self.reader.open_file("ONE")
        self.assertEqual(file.filename, "ONE")
        self.assertEqual(file.extension, "TXT")
        self.assertEqual(file.filesize, 4)
        self.assertEqual(file.bytes, b'one\n')
        self.assertEqual(str(file.bytes, "utf-8"), "one\n")

    def test_no_such_file(self):
        self.reader.do_print_on_commands = False
        self.assertRaises(Fat16Reader.NotAFileException ,lambda: self.reader.open_file(""))

    def test_ls(self):
        self.reader.ls()
        self.reader.cd("TEST")
        self.reader.ls()

if __name__ == "__main__":
    unittest.main()
