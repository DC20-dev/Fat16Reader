class FileInfo:
    """Container class for file info"""

    def __init__(self, filename, extension, filesize, bytes: bytearray):
        self.filename = filename
        self.extension = extension
        self.filesize = filesize
        self.bytes = bytes
