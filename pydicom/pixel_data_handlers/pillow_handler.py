import sys
import io
import pydicom
import pydicom.encaps
from pydicom.config import logger
have_numpy = True
try:
    import numpy
except ImportError:
    have_numpy = False
    raise

have_pillow = True
try:
    from PIL import Image as PILImg
except ImportError:
    # If that failed, try the alternate import syntax for PIL.
    try:
        import Image as PILImg
    except ImportError:
        # Neither worked, so it's likely not installed.
        have_pillow = False
        raise
sys_is_little_endian = (sys.byteorder == 'little')

def get_pixeldata(self):
    """Use PIL to decompress compressed Pixel Data.

    Returns
    -------
    bytes or str
        The decompressed Pixel Data

    Raises
    ------
    ImportError
        If PIL is not available.
    NotImplementedError
        If unable to decompress the Pixel Data.
    """
    logger.debug( "Trying to use Pillow to read pixel array (has pillow = %s)", have_pillow)
    if not have_pillow:
        msg = "The pillow package is required to use pixel_array for " \
              "this transfer syntax {0}, and pillow could not be " \
              "imported.".format(self.file_meta.TransferSyntaxUID)
        raise ImportError(msg)
    # Make NumPy format code, e.g. "uint16", "int32" etc
    # from two pieces of info:
    #    self.PixelRepresentation -- 0 for unsigned, 1 for signed;
    #    self.BitsAllocated -- 8, 16, or 32
    format_str = '%sint%d' % (('u', '')[self.PixelRepresentation],
                              self.BitsAllocated)
    try:
        numpy_format = numpy.dtype(format_str)
    except TypeError:
        msg = ("Data type not understood by NumPy: "
               "format='%s', PixelRepresentation=%d, BitsAllocated=%d")
        raise TypeError(msg % (format_str, self.PixelRepresentation,
                               self.BitsAllocated))

    if self.is_little_endian != sys_is_little_endian:
        numpy_format = numpy_format.newbyteorder('S')

    # decompress here
    if self.file_meta.TransferSyntaxUID in pydicom.uid.JPEGLossyCompressedPixelTransferSyntaxes:
        logger.debug("This is a JPEG lossy format")
        if self.BitsAllocated > 8:
            raise NotImplementedError("JPEG Lossy only supported if Bits "
                                      "Allocated = 8")
        generic_jpeg_file_header = b'\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x01\x00\x01\x00\x01\x00\x00'
        frame_start_from = 2
    elif self.file_meta.TransferSyntaxUID in pydicom.uid.JPEG2000CompressedPixelTransferSyntaxes:
        logger.debug("This is a JPEG 2000 format")
        generic_jpeg_file_header = b''
        # generic_jpeg_file_header = b'\x00\x00\x00\x0C\x6A\x50\x20\x20\x0D\x0A\x87\x0A'
        frame_start_from = 0
    else:
        logger.debug("This is a another pillow supported format")
        generic_jpeg_file_header = b''
        frame_start_from = 0
    try:
        UncompressedPixelData = ''
        if 'NumberOfFrames' in self and self.NumberOfFrames > 1:
            # multiple compressed frames
            CompressedPixelDataSeq = pydicom.encaps.decode_data_sequence(self.PixelData)
            for frame in CompressedPixelDataSeq:
                data = generic_jpeg_file_header + frame[frame_start_from:]
                fio = io.BytesIO(data)
                try:
                    decompressed_image = PILImg.open(fio)
                except IOError as e:
                    try:
                        message = str(e)
                    except Exception:
                        try:
                            message = unicode(e)
                        except Exception:
                            message = ''
                    raise NotImplementedError(message)
                UncompressedPixelData += decompressed_image.tobytes()
        else:
            # single compressed frame
            UncompressedPixelData = pydicom.encaps.defragment_data(self.PixelData)
            UncompressedPixelData = generic_jpeg_file_header + UncompressedPixelData[frame_start_from:]
            try:
                fio = io.BytesIO(UncompressedPixelData)
                decompressed_image = PILImg.open(fio)
            except IOError as e:
                try:
                    message = str(e)
                except Exception:
                    try:
                        message = unicode(e)
                    except Exception:
                        message = ''
                raise NotImplementedError(message)
            UncompressedPixelData = decompressed_image.tobytes()
    except Exception:
        raise
    logger.debug("Successfully read %s pixel bytes", len(UncompressedPixelData))
    pixel_array = numpy.fromstring(UncompressedPixelData, numpy_format)
    if self.file_meta.TransferSyntaxUID in pydicom.uid.JPEG2000CompressedPixelTransferSyntaxes and self.BitsStored == 16:
        # WHY IS THIS EVEN NECESSARY??
        pixel_array &= 0x7FFF
    return pixel_array
