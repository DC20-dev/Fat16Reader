import struct

from directory_entry import DirectoryEntry
from file_info import FileInfo


class Fat16Reader:
    """Simple FAT16 reader. It is intended only as a study case on this filesystem; some features may not be supported.
    
    The commands to navigate the image are inspired by terminal commands (ex. cd -> change directory...)"""

    # boot sector -> infos for traversing the filesystem
    #   * reserved sectors at offset 14 (0x0E), 16 bits little endian
    #   * size of a sector at offset 11 (0x0B), 16 bits little endian
    #   * size of cluster expressed in sectors at offset 13 (0x0D), 8 bit
    #
    # FAT area right after the reserved sectors
    #   * size of this area at offset 22 (0x16) of the boot sector, 16 bits little endian
    #   * multiple copies of FAT are stored, the number of copies is at offset 16 (0x10) of boot sector, 8 bit
    #
    # root directory follows the FAT area
    # root directory entries at offset 17(0x11) of boot cluster, 16 bit little endian
    #   each 32 bytes contain:
    #     * name and extension of the entry at first 11 bytes (8B name, 3B extension)
    #     * a bitmask with info about the entry at 12th byte
    #     * a 16 bit little endian value indicating the start cluster at 26th byte
    #     * the size of the file in bytes at the last 4 bytes (froom 28th to 32nd)

    _attributes = {
        0x01: "read_only",
        0x02: "hidden",
        0x04: "system",
        0x08: "volume_id",
        0x10: "directory",
        0x20: "archive",
    }
    _fat_16_notable_values = {
        0x0000: "free cluster",
        0x0001: "not allowed",
        0xFFF7: "one or more bad sectors in cluster",
        0xFFF8: "end of file",
        0xFFFF: "end of file"
    }
    _entry_size = 32
    _fat_cluster_read_start = 2
    # bytes 0&1 are for other stuff

    def __init__(self, file_path: str, do_print_on_commands: bool = False):
        self.do_print_on_commands = do_print_on_commands
        with open(file_path, "rb") as f:
            self.image = f.read()
        self.volume_id = ""
        self._read_boot_sector()
        # start from root dir
        self._current_root = self._root_directory_offset
        # reads the entries in the root dir
        self._current_entries = self._read_directory(self._current_root)

    def _read_boot_sector(self):
        # reserved sectors info (boot sector mainly)
        self._reserved_sectors = self._read_ushort(14)
        self._sector_size = self._read_ushort(11)
        self._cluster_size = self.image[13]  # expressed in sectors
        # fat area info
        self._fat_offset = self._reserved_sectors * self._sector_size
        self._fat_size = self._read_ushort(22)
        self._fat_copies = self.image[16]
        # root directory info
        self._root_directory_offset = self._fat_offset + \
            (self._fat_size * self._fat_copies * self._sector_size)
        self._root_directory_entries = self._read_ushort(17)
        self._root_directory_size = self._root_directory_entries * self._entry_size
        # clusters start
        self._clusters_offset = self._root_directory_offset + self._root_directory_size

    def _read_directory(self, offset) -> list[DirectoryEntry]:
        """Reads the entries from the provided directory offset"""
        entry_offset = offset
        entries = []
        while self.image[entry_offset] != 0x00:
            # if the entry_offset (first byte of the entry)
            # contains 0x00 it means that the end of dir is reached
            entries.append(self._read_entry(entry_offset))
            entry_offset += self._entry_size
        return entries

    def _read_entry(self, byte_offset) -> DirectoryEntry:
        # filename
        name = self.image[byte_offset:byte_offset + 8]
        extension = self.image[byte_offset + 8:byte_offset+11]
        entry_filename = name.decode("utf-8").strip()
        entry_extension = extension.decode("utf-8").strip()
        # attributes
        attributes_byte = self.image[byte_offset+11]
        entry_attributes = []
        for attribute in self._attributes:
            if attributes_byte & attribute:  # bitwise and, it returns 1 for every match
                entry_attributes.append(self._attributes[attribute])
        # datetime
        creation_time = self._read_ushort(byte_offset+14)
        creation_date = self._read_ushort(byte_offset+16)
        # it's the same for last modified and accessed (different offsetes); let's just skip those
        # cluster number
        cluster_number = self._read_ushort(byte_offset+26)
        # file size in bytes
        filesize = struct.unpack(
            "<I", self.image[byte_offset+28:byte_offset+32])[0]
        return DirectoryEntry(
            entry_filename, entry_extension, entry_attributes, creation_date,
            creation_time, cluster_number, filesize)

    def _check_next_in_fat(self, cluster_number):
        """checks the fat area at the provided offset and returns either 
        True if there is another cluster for the file or False if not"""
        fat_16_value = self._read_ushort(self._fat_offset + cluster_number*2)
        has_next_cluster = True
        if fat_16_value in self._fat_16_notable_values:
            # there is no other cluster for the file (or a problem on the cluster),
            # let's just assume they are all EOF but send the value so that
            # we can print the correct message if needed
            has_next_cluster = False
        return (has_next_cluster, fat_16_value)

    def _read_ushort(self, offset):
        """shorthand for a recurring operation"""
        return struct.unpack("<H", self.image[offset:offset+2])[0]

    def _get_clusters_list(self, entry: DirectoryEntry) -> list[int]:
        # check all of the clusters involved in this directory and store them
        # creating the linked list to traverse and find all the entries
        if (entry.cluster_number == 0):
            # in this case we have ".." and a cluster value of 0x00, which is not possible;
            # this is the case where the parent dir is the root dir, so let's just skip this
            # operation because the root has no cluster linked list
            return []
        clusters_list = [entry.cluster_number]
        next_cluster_tuple = self._check_next_in_fat(entry.cluster_number)
        while next_cluster_tuple[0] == True:
            clusters_list.append(next_cluster_tuple[1])
            next_cluster_tuple = self._check_next_in_fat(next_cluster_tuple[1])
        return clusters_list

    def _cd_set_current_entries(self, linked_list):
        self._current_entries = []
        for cluster in linked_list:
            # get the offset where the cluster starts
            cluster_start = self._clusters_offset + \
                self._cluster_size * self._sector_size * \
                (cluster - self._fat_cluster_read_start)
            # it can only be a directory because cd won't run otherwise, so let's parse the dir
            self._current_entries.extend(self._read_directory(cluster_start))

    def _compose_file(self, clusters_list, entry:DirectoryEntry):
        file = FileInfo(entry.filename, entry.extension, entry.filesize, b'')
        bytes = entry.filesize
        file_bytes = []
        cluster_bytes = self._cluster_size * self._sector_size
        for cluster in clusters_list:
            # get the offset where the cluster starts
            cluster_start = self._clusters_offset + \
                self._cluster_size * self._sector_size * \
                (cluster - self._fat_cluster_read_start)
            if bytes >= cluster_bytes:
                # file contains all this cluster
                file_bytes.append(self.image[cluster_start:cluster_start+cluster_bytes])
                bytes -= cluster_bytes
            else:
                # this is only/last cluster, so we take all the remaining bytes
                file_bytes.append(self.image[cluster_start:cluster_start+bytes])
        file.bytes = file_bytes[0]
        return file

    # "SHELL" COMMANDS

    def ls(self):
        """Shows info about the current directory"""
        if self.do_print_on_commands:
            pass
        return self._current_entries

    def cd(self, directory_name) -> list[DirectoryEntry]:
        """Changes the directory to the one requested"""
        found = False
        for entry in self._current_entries:
            if "directory" in entry.attributes and entry.filename == directory_name:
                clusters_linked_list = self._get_clusters_list(entry)
                if len(clusters_linked_list) > 0:
                    self._cd_set_current_entries(clusters_linked_list)
                else:
                    # it's the root directory entry
                    self._current_entries = self._read_directory(
                        self._root_directory_offset)
                found = True
        if not found and self.do_print_on_commands:
            # prints the message instead of raising the exception,
            # useful if it's used inline
            print("There is no such directory")
            return None
        elif not found and not self.do_print_on_commands:
            raise self.NotADirectoryException()
        # let's return the entries to support a classical usage (so no printing involved)
        return self._current_entries

    def open_file(self, filename):
        "Opens a file"
        found = False
        for entry in self._current_entries:
            if entry.filename == filename:
                # exists
                found = True
                if "archive" in entry.attributes or "read_only" in entry.attributes:
                    # is a file
                    clusters_list = self._get_clusters_list(entry)
                    file = self._compose_file(clusters_list, entry)
        if not found and self.do_print_on_commands:
            print("There is no such file")
            return None
        if not found and not self.do_print_on_commands:
            raise self.NotAFileException()
        return file

    def print_first_n_bytes(self, n):
        """DEBUG ONLY"""
        print("bytes: " + self.image[0:n].hex(" "))

    class ClusterOffsetException(Exception):
        def __init__(self, message="Not a valid fat cluster offset"):
            super().__init__(message)

    class NotADirectoryException(Exception):
        def __init__(self, message="There is no such directory"):
            super().__init__(message)
            
    class NotAFileException(Exception):
        def __init__(self, message="There is no such file"):
            super().__init__(message)
