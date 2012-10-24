from errno import ESRCH
from fcntl import fcntl, F_GETFL, F_SETFL
import logging
import os.path
from os import O_NONBLOCK
from subprocess import Popen, PIPE
from tornado.ioloop import IOLoop
from urlparse import urlparse

__all__ = ["ImageMagick", "is_remote"]

logger = logging.getLogger("ectyper")

def is_remote(path):
    """
    Returns true if the given path is a remote HTTP or HTTPS URL.
    """
    return urlparse(path).scheme in set(["http", "https"])

def _valid_pct(s):
    """
    Returns true if the given string represents a positive integer
    followed by the '%' character.
    """
    if isinstance(s, basestring) and s.endswith('%'):
        try:
            s = int(s[0:-1])
            if s >= 0:
                return True
        except ValueError:
            pass

    return False

def _proc_failed(proc):
    """
    Returns true if the given subprocess.Popen has terminated and
    returned a non-zero code.
    """
    rcode = proc.poll()
    return rcode is not None and rcode != 0

def _non_blocking_fileno(fh):
    fd = fh.fileno()
    try:
        flags = fcntl(fd, F_GETFL)
        fcntl(fd, F_SETFL, flags | O_NONBLOCK)
    except IOError, e:
        # Failed to set to non-blocking, warn and continue.
        logger.warning("Couldn't setup non-blocking pipe: %s" % str(e))
    return fd

def _make_blocking(fd):
    try:
        flags = fcntl(fd, F_GETFL)
        fcntl(fd, F_SETFL, flags & ~O_NONBLOCK)
    except IOError, e:
        # Failed to set to blocking, warn and continue.
        logger.warning("Couldn't set blocking: %s" % str(e))

def _list_prepend(dest, src):
    """
    Prepends the src to the dest list in place.
    """
    for i in xrange(len(src)):
        dest.insert(0, src[len(src)-i-1])

def _proc_terminate(proc):
    try:
        if proc.poll() is None:
            proc.terminate()
            proc.wait()
    except OSError, e:
        if e.errno != ESRCH:
            raise

class ImageMagick(object):
    """
    Wraps the command-line verison of ImageMagick and provides a way to:
     - Chain image operations (i.e. resize -> reflect -> convert)
     - Asynchronously process the chain of operations
    Chaining happens in the order that you call each method.
    """
    JPEG = "jpeg"
    PNG = "png"

    GRAVITIES = {
        "left": "West",
        "right": "East",
        "top": "North",
        "bottom": "South",
        "middle": "Center",
        "center": "Center",
        "topleft": "NorthWest",
        "topright": "NorthEast",
        "bottomleft": "SouthWest",
        "bottomright": "SouthEast",
    }

    def __init__(self):
        ""
        self.options = []
        self.filters = []
        self.format = self.PNG
        self.convert_path = None
        self.curl_path = None
        self.ioloop = IOLoop.instance()

    def _chain_op(self, name, operation, prepend):
        """
        Private helper.  Chains the given operation/name either prepending
        or appending depending on the passed in boolean value of prepend.
        """
        if prepend:
            self.filters.insert(0, name)
            _list_prepend(self.options, operation)
        else:
            self.filters.append(name)
            self.options.extend(operation)

    def reflect(self, out_height, top_alpha, bottom_alpha, prepend=False):
        """
        Flip the image upside down and crop to the last out_height pixels.  Top
        and bottom alpha sets parameters for the linear gradient from the top
        to bottom.
        """
        opt_name = 'reflect_%0.2f_%0.2f_%0.2f' % (out_height, top_alpha, bottom_alpha)

        crop_param = 'x%d!' % out_height
        rng = top_alpha - bottom_alpha
        opt = [
            '-gravity', 'NorthWest',
            '-alpha', 'on',
            '-flip',
            '(',
                '+clone', '-crop', crop_param, '-delete', '1-100',
                '-channel', 'G', '-fx', '%0.2f-(j/h)*%0.2f' % (top_alpha, rng),
                '-separate',
            ')',
            '-alpha', 'off', '-compose', 'copy_opacity', '-composite',
            '-crop', crop_param, '-delete', '1-100'
        ]
        self._chain_op(opt_name, opt, prepend)

    def crop(self, w, h, x, y, g, prepend=False):
        """
        Crop the image to (w, h) offset to (x, y) with gravity g.  w, h, x, and
        y should be integers (w, h should be positive).

        w and h can optionally be integer strings ending with '%'.
        
        g should be one of NorthWest, North, NorthEast, West, Center, East,
        SouthWest, South, SouthEast (see your ImageMagick's -gravity list for
        details).
        """
        (w, h) = [v if _valid_pct(v) else int(v) for v in (w, h)]

        x = "+%d" % x if x >= 0 else str(x)
        y = "+%d" % y if y >= 0 else str(y)

        self._chain_op(
            'crop_%s_%sx%s%s%s' % (g, w, h, x, y),
            ['-gravity', g, '-crop', '%sx%s%s%s' % (w, h, x, y)],
            prepend)

    def overlay(self, x, y, g, image_filename, prepend=False):
        """
        Overlay image specified by image_filename onto the current image,
        offset by (x, y) with gravity g. x and y should be integers.

        g should be one of NorthWest, North, NorthEast, West, Center, East,
        SouthWest, South, SouthEast (see your ImageMagick's -gravity list for
        details).
        """
        opt_name = 'overlay_%d_%d_%s' % (x, y, os.path.basename(image_filename))
        x = "+%d" % x if x >= 0 else str(x)
        y = "+%d" % y if y >= 0 else str(y)
        self._chain_op(
            opt_name,
            [
                image_filename,
                '-gravity', g,
                '-geometry', "%s%s" % (x, y),
                '-composite'
            ],
            prepend)

    def resize(self, w, h, maintain_ratio, will_crop, prepend=False):
        """
        Resizes the image to the given size.  w and h are expected to be
        positive integers.  If maintain_ratio evaluates to True, the original
        aspect ratio of the image will be preserved. With maintain_ratio True:
        if will_crop is true, then the result will fill and possibly overflow
        the dimensions; otherwise it will scale to fit inside the dimensions.
        """

        resize_type = 1
        size = "%dx%d" % (w, h)
        if not maintain_ratio:
            size += "!"
            resize_type = 0
        elif will_crop:
            size += "^"
            resize_type = 2

        name = 'resize_%d_%d_%d' % (w, h, resize_type)
        opt = ['-resize', size]
        self._chain_op(name, opt, prepend)

    def constrain(self, w, h, prepend=False):
        """
        Constrain the image to the given size.  w and h are expected to be
        positive integers.  This operation is useful after a resize in which
        aspect ratio was preserved.
        """
        extent = "%dx%d" % (w, h)
        self._chain_op(
            'constrain_%d_%d' % (w, h),
            [
                '-gravity', 'Center',
                '-background', 'transparent',
                '-extent', extent
            ],
            prepend)

    def normalize(self, prepend=False):
        """
        Add -normalize operator. The top two percent of the dark pixels will become 
        black and the top one percent of the light pixels will become white. The 
        contrast of the rest of the pixels are maximized.
        """
        self._chain_op("normalize", ["-normalize"], prepend)

    def equalize(self, prepend=False):
        """
        Add the -equalize operator. It redistributes the colour of the image uniformly.
        """
        self._chain_op("equalize", ["-equalize"], prepend)

    def contrast_stretch(self, a, b, prepend=False):
        """
        Add the -contrast-stretch a%xb% operator. The top a percent of the dark pixels 
        will become black and the top b percent of the light pixels will become white. 
        The contrast of the rest of the pixels are maximized. 

        a and b are expected to be integers.
        """
        white_and_black_point = "%d%%x%d%%" % (a, b)
        name = "contrast_stretch_%d_%d" % (a, b)
        opt = ['-contrast-stretch', white_and_black_point]
        self._chain_op(name, opt, prepend)

    def brightness_contrast(self, a, b, prepend=False):
        """
        Add the -brightness-contrast a%xb% operator. a and b represent the percentage change
        of brighteness and contrast, respectively.
        a and b are expected to be integers.
        """
        brightness_and_contrast = "%d%%x%d%%" % (a, b)
        name = "brightness_contrast_%d_%d" % (a, b)
        opt = ['-brightness-contrast', brightness_and_contrast]
        self._chain_op(name, opt, prepend)

    def rgb555_dither(self, _colormap=None):
        """
        Reduce color channels to 5-bit by dithering, preserving Alpha channel.
        Intented for better look on 16-bit screens.
        """
        name = 'rgb555_dither'
        if _colormap is None:
            _colormap = os.path.dirname(__file__) + "/gs5bit.png"
        opt = [
            '-background', 'white',
            '(',
                '+clone', '-channel', 'RGB', '-separate',
                '-type', 'TrueColor', '-remap', _colormap,
            ')',
            '(',
                '-clone', '0', '-channel', 'A', '-separate',
                '-alpha', 'copy',
            ')',
            '-delete', '0', '-channel', 'RGBA', '-combine'
        ]
        self._chain_op(name, opt, False)

    def get_mime_type(self):
        """
        Return the mime type for the current set of options.
        """
        if self.format == self.PNG:
            return "image/png"
        elif self.format == self.JPEG:
            return "image/jpeg"
        return "application/octet-stream"

    def format_options(self):
        """
        Returns standard ImageMagick options for converting into this instance's format.
        """
        opts = []

        if self.format == self.PNG:
            # -quality 95
            #  9 = zlib compression level 9
            #  5 = adaptive filtering
            opts.extend(["-quality", "95"])
            
            # 8 bits per index
            opts.extend(["-depth", "8"])

            # Support alpha transparency
            opts.append("png32:-")
        elif self.format == self.JPEG:
            # Q=85 with 4:2:2 downsampling
            opts.extend(["-quality", "85"])
            opts.extend(["-sampling-factor", "2x1"])

            # Enforce RGB colorspace incase input image has a different
            # colorspace
            opts.extend(["-colorspace", "sRGB"])

            # Strip EXIF data
            opts.extend(["-strip"])
            opts.append("jpeg:-")
        else:
            # Default to whatever is defined in format
            opts.append("%s:-" % self.format)

        return opts

    def convert_cmdline(self, path, stdin=False):
        command = [
            'convert' if not self.convert_path else self.convert_path,
            '-' if stdin else path
        ]
        command.extend(self.options)
        command.append('-quiet')
        command.extend(self.format_options())
        return command

    def convert(self, path, chunk_ready=None, complete=None, error=None):
        """
        Converts the image at the given path according to the filter chain.  If
        write_chunk, close, and error are provided, the image is provided
        asynchronously via those callbacks.  Otherwise, this method blocks and
        returns the processed image as a string.

         - chunk_ready(chunk): piece of the processed image as a string.  There is
           no minimum or maximum size.
         - complete(): Called when the processing has completed.
         - error(): Called if there was an error processing the image.
        """

        source = None
        if is_remote(path):
            source = Popen(
                ['curl' if not self.curl_path else self.curl_path, '-sfL', path],
                stdout=PIPE,
                close_fds=True)

            # Make sure curl hasn't died yet, generally this won't trigger
            # since the process won't kick off until we actually start reading
            # from it.
            if _proc_failed(source):
                if callable(error):
                    error()
                return

        command = self.convert_cmdline(path, source is not None)
        logger.debug("CONVERT %s (opts: %s)" % (path, repr(self.options)))

        convert = Popen(command,
            stdin=source.stdout if source else None,
            stdout=PIPE,
            stderr=PIPE,
            close_fds=True)

        if source:
            source.stdout.close()

        if all(map(callable, [chunk_ready, complete, error])):
            # Non-blocking case
            def _cleanup(fd):
                self.ioloop.remove_handler(fd)

                if source:
                    _proc_terminate(source)
                _proc_terminate(convert)

            def _on_read(fd, events):
                if (source and _proc_failed(source)) or _proc_failed(convert):
                    _cleanup(fd)
                    error()

                else:
                    chunk = convert.stdout.read()
                    if len(chunk) == 0 or convert.returncode == 0:

                        # Block to ensure we get the whole output, without this
                        # we generate corrupted images
                        _make_blocking(convert.stdout.fileno())
                        chunk += convert.stdout.read()
                        convert.stdout.close()
                        convert.wait()
                        if len(chunk) > 0:
                            chunk_ready(chunk)
                            chunk = ""

                        _cleanup(fd)
                        if convert.poll() == 0:
                            complete()
                        else:
                            error()
                    else:
                        chunk_ready(chunk)

            def _on_error_read(fd, events):
                buf = convert.stderr.read()
                if not buf:
                    convert.stderr.close()
                else:
                    logger.error("Conversion error: %s" % buf)

            # Make output non-blocking
            fd = convert.stdout.fileno()

            self.ioloop.add_handler(
                _non_blocking_fileno(convert.stdout),
                _on_read,
                IOLoop.READ)
            self.ioloop.add_handler(
                _non_blocking_fileno(convert.stderr),
                _on_error_read,
                IOLoop.READ)

        else:
            # Blocking case (if no handlers are passed)
            output = convert.communicate()[0]
            if (source and source.returncode != 0) or convert.returncode != 0:
                return None
            return output
