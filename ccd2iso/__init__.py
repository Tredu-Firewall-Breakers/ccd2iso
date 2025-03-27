# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Tool to convert CloneCD .img files to ISO 9660 .iso files."""

from typing import Any
from io import BytesIO
import contextlib
import tkinter.filedialog as fileDialog
import os
import progressbar
from ctypes import c_ubyte, Structure, Union, sizeof
import sys

__version__ = "0.0.1"
DATA_SIZE = 2048

#
# Structures
#

class ccd_sectheader_header(Structure):
    _fields_ = [
        ('sectaddr_min', c_ubyte),
        ('sectaddr_sec', c_ubyte),
        ('sectaddr_frac', c_ubyte),
        ('mode', c_ubyte),
    ]

class ccd_sectheader(Structure):
    _fields_ = [
        ('synchronization', c_ubyte * 12),
        ('header', ccd_sectheader_header),
    ]

class ccd_mode1(Structure):
    _fields_ = [
        ('data', c_ubyte * DATA_SIZE),
        ('edc', c_ubyte * 4),
        ('unused', c_ubyte * 8),
        ('ecc', c_ubyte * 276),
    ]

class ccd_mode2(Structure):
    _fields_ = [
        ('sectsubheader', c_ubyte * 8),  # Unknown structure
        ('data', c_ubyte * DATA_SIZE),
        ('edc', c_ubyte * 4),
        ('ecc', c_ubyte * 276),
    ]

class ccd_content(Union):
    """Represents various modes a content block could be in.

    Other modes exist, such as for multisession data.
    """
    _fields_ = [
        ('mode1', ccd_mode1),
        ('mode2', ccd_mode2),
    ]

class ccd_sector(Structure):
    """Individual sector in the disc image."""
    _fields_ = [
        ('sectheader', ccd_sectheader),
        ('content', ccd_content),
    ]

#
# Exceptions
#

class IncompleteSectorError(Exception):
    """Raised when there are less bytes in the sector than expected."""
    pass

class SessionMarkerError(Exception):
    """Raised when a session marker is reached.

    The image might contain multisession data, and only the first session was
    exported.
    """
    pass

class UnrecognizedSectorModeError(Exception):
    """Raised when a sector mode isn't supported by ccd2iso."""
    pass

#
# Functions
#

def convert(src_file: BytesIO, dst_file: BytesIO, progress: bool = False, size: int = None) -> None:
    """Converts a CloneCD disc image bytestream to an ISO 9660 bytestream.

    src_file -- CloneCD disc image bytestream (typically with a .img extension)
    dst_file -- destination bytestream to write to in ISO 9660 format
    progress -- whether to output a progress bar to stdout
    size -- size of src_file, used to calculate sectors remaining for progress
    """

    sect_num = 0
    expected_size = sizeof(ccd_sector)
    max_value = int(size / expected_size) if size else progressbar.UnknownLength
    print(max_value, progress)

    # Initialize progress bar if enabled
    progress_bar = progressbar.ProgressBar(maxval=max_value) if progress else None
    if progress_bar:
        progress_bar.start()

    try:
        while bytes_read := src_file.read(expected_size):
            src_sect = ccd_sector.from_buffer_copy(bytes_read)
            if sizeof(src_sect) < expected_size:
                raise IncompleteSectorError(
                    'Error: Sector %d is incomplete, with only %d bytes instead of %d. This might not be a CloneCD disc image.' %
                    (sect_num, sizeof(src_sect), expected_size))

            if src_sect.sectheader.header.mode == 1:
                bytes_written = dst_file.write(src_sect.content.mode1.data)
            elif src_sect.sectheader.header.mode == 2:
                bytes_written = dst_file.write(src_sect.content.mode2.data)
            elif src_sect.sectheader.header.mode == b'\xe2':
                raise SessionMarkerError('Error: Found a session marker, this image might contain multisession data. Only the first session was exported.')
            else:
                raise UnrecognizedSectorModeError('Error: Unrecognized sector mode (%x) at sector %d!' % (src_sect.sectheader.header.mode, sect_num))

            sect_num += 1

            # Update progress bar if enabled
            if progress_bar:
                progress_bar.update(sect_num)
    finally:
        # Finish progress bar if enabled
        if progress_bar:
            progress_bar.finish()

def main():
    # Check source file
    src_file = fileDialog.askopenfile(mode='r', filetypes=[("CloneCD Image", "*.img")])
    dst_file = None

    # ask for source file
    if not src_file:
        print('Error: No file selected.')
        sys.exit(0)
    else:
        print('Source file:', src_file.name)

    # ask if user wants to create a new .iso file in the same directory
    if input('Create new .iso file in the same directory? (y/n) ').lower() == 'y':
        import tempfile
        # get current directory
        current_dir = os.path.dirname(src_file.name)
        dst_file = tempfile.NamedTemporaryFile(dir = current_dir, delete=False)
        print('Destination file:', dst_file.name, 'Current Directory:', current_dir)
    else:
        # ask for destination file
        dst_file = fileDialog.asksaveasfile(mode='wb', defaultextension='.iso', filetypes=[("ISO 9660 Image", "*.iso")])
        if not dst_file:
            print('Error: No file selected.')
            sys.exit(0)
        else:
            print('Destination file:', dst_file.name)

    # Run conversion
    try:
        runQuiet = input('Run in quiet mode? (y/n) ').lower()
        if runQuiet == 'y':
            runQuiet = True
        else:
            runQuiet = False
        print('Converting...')
        convert(src_file, dst_file, progress=not runQuiet, size = os.path.getsize(src_file.name))
    except KeyboardInterrupt:
        print('Cancelled.')
        dst_file.close()
        os.remove(dst_file.name)
        sys.exit(1)
    except Exception as error:
        print(error)
        dst_file.close()
        os.remove(dst_file.name)
        sys.exit(1)

    # Clean up
    src_file.close()
    dst_file.close()
    try:
        os.replace(dst_file.name, src_file.name + '.iso')
    except PermissionError:
        print("Error: Couldn't overwrite", dst_file.name, "with", src_file.name + '.iso')  
        print('The .iso file might be mounted or marked read-only.')
        print(dst_file.name, 'contains the ISO data')
    print('Done.')

if __name__ == '__main__':
    main()