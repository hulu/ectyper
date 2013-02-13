from errno import EEXIST
from ectyper.magick import ImageMagick, is_remote
import logging
import os
from random import randint
from time import time
from tornado.web import RequestHandler, asynchronous, HTTPError

__all__ = ["ImageHandler", "CachingImageHandler", "FileCachingImageHandler"]

logger = logging.getLogger("ectyper")

class ImageHandler(RequestHandler):
    """
    Base handler class that provides file and transform 
    operations common to all available image types
    """

    IMAGE_MAGICK_CLASS = ImageMagick

    def __init__(self, *args, **kwargs):
        super(ImageHandler, self).__init__(*args, **kwargs)
        self.magick = None
        self.local_image_dir = None
        self.local_font_dir = None

    def handler(self, *args):
        """
        Primary entry point for your code.  Override this method
        and process the request as necessary.
        """
        raise NotImplementedError()

    @asynchronous
    def get(self, *args):
        ""
        self.calculate_options()
        self.handler(*args)

    def parse_size(self, size):
        return self.parse_2d_param(size)

    def parse_overlay_list(self, input_str):
        """
        Parse the comma separated list of overlay images.  Throws a 500 if the
        user attempts to pass in a relative path.
        """
        if input_str:
            result = []
            paths = input_str.split(',')
            for path in paths:
                filename = os.path.basename(path)
                if filename == path:
                    result.append(filename)
                else:
                    logger.error('Relative path name {0} not allowed for image overlay'.format(path))
                    raise HTTPError(500)
            return result
        else:
            return None

    def parse_2d_param(self, size):
        """
        Parses a string 'NxM' into a 2-tuple.  If either N or M parses into
        a float, it's rounded to the nearest int.  If either value doesn't
        parse properly or the string is malformed, None is returned.
        """
        if not size:
            return None

        try:
            size = map(lambda x: int(round(float(x))), size.split("x", 1))
        except ValueError:
            return None

        if len(size) == 2:
            return (size[0], size[1])

        return None

    def calculate_options(self):
        """
        Builds an ImageMagick object according to the given parameters.
        By default it supports the following params:

         &size=NxM
            Resize the source image to N pixels wide and M pixels high.

         &crop=1
            Crops the image, maintaining aspect ratio, when resizing
            (ignored if size is not provided or maintain_ratio is not 1).
            Defaults to 0.

         &crop_anchor=(top|bottom|left|right|center|middle|topleft|topright
            |bottomleft|bottomright)
            Anchors the crop to one location of the image.
            (ignored if crop and maintain_ratio are not both 1).
            Defaults to center

         &maintain_ratio=1
            Maintain aspect ratio when resizing (ignored if size is not
            provided).

         &extent=1
            Expand the image to the dimension specified by the extent_size or the 
            size parameter. This is useful when maintain_ratio=1 leaves blanks on 
            the edges - set extent=1 and extent_anchor together can determine which 
            side the blank edges are placed

         &extent_size=NxM
            Extent the resized image further to N pixels wide and M pixels high.
            Default to size.

         &extent_anchor=(top|bottom|left|right|center|middle|topleft|topright
            |bottomleft|bottomright)
            Anchors the extent operation to one location of the image.
            (ignored if extent or extent_size does not exist or is invalid).
            Defaults to center

         &extent_background=Hex
             The background color used for extending a source image.
             The color should be specified by its Hex value, e.g. #FF0, #FFFF00, or
             #FFFF00AA.
             (ignored if extent or extent_size does not exist or is invalid).
             Defaults to #00000000 (transparent)

         &extent_compose=(over|add|subtract)
             The compose method used for extending a source image.
             over     - source image is composed over background color.
             add      - source image is added onto background color.
             subtract - source image is subtracted from background color.
             (ignored if extent or extent_size does not exist or is invalid).
             Defaults to "over"

         &extent_shift=NxM
            Shifts the image away from anchor position by N pixels padding on the left
            and M pixels of padding on the top. Currently only positive integer values
            are supported.
            Note, if the shift + image size exceeds the extent_size, weird stuff will
            likely happen.

         &post_crop_size=NxM
            Applies a secondary "post-crop" to the image, after the standard
            image resize is performed. This supports the case where an image 
            needs to be sized to fit a particular dimension using a crop, 
            then the image needs to be chopped up into different regions.
            Defaults to None, meaning that no post-crop is applied.

         &post_crop_anchor=(top|bottom|left|right|center|middle|topleft|topright
            |bottomleft|bottomright)
            Anchors the post-crop to one location of the image.
            (ignored if post_crop_size does not exist or is invalid).
            Defaults to center

         &reflection_height=N
            Flip the image upside down and apply a gradient to mimic a
            reflected image.  reflection_alpha_top and reflection_alpha_bottom
            can be used to set the gradient parameters.

         &reflection_alpha_top=N
            The top value to use when generating the gradient for
            reflection_height, ignored if that parameter is not set.  Should be
            between 0 and 1. Defaults to 1.

         &reflection_alpha_bottom=N
            The bottom value to use when generating the gradient for
            reflection_height, ignored if that parameter is not set.  Should be
            between 0 and 1.  Defaults to 0.

         &splice=1
            Insert a space into the middle or edge of an image of dimensions
            specified by the splice_size. This will result
            in the overall size of the image increasing based on the addition.

         &splice_size=NxM
            Dimensions of space to add into the middle or edge of an image.

         &splice_anchor=(top|bottom|left|right|center|middle|topleft|topright
            |bottomleft|bottomright)
            Anchors the splice operation to one location of the image.
            (ignored if splice or splice_size does not exist or is invalid).
            Defaults to center

         &splice_background=Hex
             The background color used for splicing a source image.
             The color should be specified by its Hex value, e.g. #FF0, #FFFF00, or
             #FFFF00AA.
             (ignored if splice or splice_size does not exist or is invalid).
             Defaults to #00000000 (transparent)

         &splice_compose=(over|add|subtract)
             The compose method used for splicing a source image.
             over     - source image is composed over background color.
             add      - source image is added onto background color.
             subtract - source image is subtracted from background color.
             (ignored if splice or splice_size does not exist or is invalid).
             Defaults to "over"

         &format=(jpeg|png|png16)
            Format to convert the image into.  Defaults to jpeg.
            png16 is 24-bit png pre-dithered for 16-bit (RGB555) screens.

         &normalize=1
            Histogram-based contrast increase. It passes the -normalize operator to ImageMagick.
            The top two percent of the dark pixels will become black and the top one percent of the 
            light pixels will become white. The contrast of the rest of the pixels are maximized.
            All the channels are normalized together to avoid color shift, so pure black or white 
            may not exist in the final image. Defaults to 0, which won't chain any operator to the
            ImageMagick command.

         &equalize=1
            Histogram-based colour redistribution. It passes the -equalize operator to ImageMagick, 
            following the -normalize operator. It redistributes the colour of the image according to 
            uniform distribution. Each channel are changed independently, and color shift may happen.
            Default to 0, which won't chain any operator to the ImageMagick command.

         &contrast_stretch=axb
            Histogram-based contrast adjustment. It passes the -contrast-stretch a%xb% operator to 
            ImageMagick, following the -equalize operator. The top a percent of the dark pixels will 
            become black and the top b percent of the light pixels will become white. The contrast 
            of the rest of the pixels are maximized. All the channels are normalized together to avoid 
            color shift, so pure black or white may not exist in the final image. Defaults to None, which 
            won't chain any operator to the ImageMagick command.

         &brightness_contrast=cxd
            Amplify brightness and contrast by percentages. It passes the -brightness-contrast c%xd% 
            operator to ImageMagick, following the -contrast-stretch operator. Defaults to None, which 
            won't chain any operator to the ImageMagick command.

         &overlay_image=image1.png,image2.png,...
            Applies each image as an overlay on the source image.  The overlay image will be resized
            to match the size of the source image.  Overlays are applied before cropping.  The images
            specified must be present in a local directory, specified by self.local_image_dir.
            Relative paths are not allowed, and a 500 will be thrown if one is encountered (preventing
            clients from accessing files in other directories).

         &text_0=Some%20Text
            text_0 through text_4 are used with their corresponding style params to overlay text onto a
            given image.  Text is applied before cropping.  Text can be of any length, through whether
            the text runs off the image or wraps is defined in the style.

        &style_0=some_style
            style_0 through style_4 are used with their corresponding text params to overlay text onto a 
            given image.  Text is applied before cropping.  Styles must be defined and are obtained 
            through get_style, without modification no styles exist and no text will be applied.


        """

        # Already calculated options, bail.
        if self.magick:
            return

        magick = self.IMAGE_MAGICK_CLASS()

        size = self.parse_size(self.get_argument("size", None))
        
        extent = int(self.get_argument("extent", 0)) == 1
        extent_size = self.parse_size(self.get_argument("extent_size", self.get_argument("size", None)))
        extent_anchor = self.get_argument("extent_anchor", "center")
        extent_background = self.get_argument("extent_background", "#00000000")
        extent_compose = self.restrict_compose_method(self.get_argument("extent_compose", "over"))
        
        splice = int(self.get_argument("splice", 0)) == 1
        splice_size = self.parse_size(self.get_argument("splice_size", self.get_argument("size", None)))
        splice_anchor = self.get_argument("splice_anchor", "center")
        splice_background = self.get_argument("splice_background", "#00000000")
        splice_compose = self.restrict_compose_method(self.get_argument("splice_compose", "over"))

        # shift is a custom setting that will use splice to shift an extent in a desired direction
        extent_shift = self.parse_size(self.get_argument('extent_shift', None))
        shift_align = None
        
        reflection_height = self.get_argument("reflection_height", None)
        maintain_ratio = int(self.get_argument("maintain_ratio", 0)) == 1
        crop = int(self.get_argument("crop", 0)) == 1
        crop_anchor = self.get_argument("crop_anchor", "center")
        post_crop_size = self.parse_size(self.get_argument("post_crop_size", None))
        post_crop_anchor = self.get_argument("post_crop_anchor", "center")
        normalize = int(self.get_argument("normalize", 0)) == 1
        equalize = int(self.get_argument("equalize", 0)) == 1
        contrast_stretch = self.parse_2d_param(self.get_argument("contrast_stretch", None))
        brightness_contrast = self.parse_2d_param(self.get_argument("brightness_contrast", None))
        overlay_image = self.parse_overlay_list(self.get_argument("overlay_image", None))
        texts = []
        styles = []
        for n in range(0,5):
            text = self.get_argument("text_" + str(n), None)
            style = self.get_argument("style_" + str(n), None)
            if text and style:
                texts.append(text)
                styles.append(style)
            else:
                break
        text_validator = self.get_argument("text_validator", None)

        # size=&maintain_ratio=&crop=&crop_anchor=
        if size:
            (w, h) = size
            magick.resize(w, h, maintain_ratio, crop)
            # overlay before cropping
            if overlay_image and self.local_image_dir:
                for img in overlay_image:
                    img_path = os.path.join(self.local_image_dir, img)
                    if os.path.exists(img_path):
                        magick.overlay_with_resize(0, 0, w, h, 'Center', img_path)
                    else:
                        logger.warn('Requested overlay image that does not exist {0}'.format(img_path))
            if maintain_ratio and crop:
                direction = magick.GRAVITIES[crop_anchor]
                # repage before and after we crop.
                magick.options.append("+repage")
                magick.crop(w, h, 0, 0, direction)
                magick.options.append("+repage")
            elif not reflection_height and not extent:
                magick.constrain(w, h)

            if self.validate_texts(texts, text_validator):
                for t, s in zip(texts, styles):
                    style = self.get_style(s)
                    if style:
                        magick.add_styled_text(t, style, self.local_font_dir, w, h)
                
        # extent=1&extent_anchor=&extent_background=&extent_compose=&extent_size=
        if extent and extent_size:
            (w, h) = extent_size
            if extent_shift:
                (shift_left, shift_top) = extent_shift
                
                # Adjust extent by desired shift dimensions
                w = w - abs(shift_left)
                h = h - abs(shift_top)

                # Determine which alignment to use for splice
                shift_align = ''
                if shift_top >= 0:
                    shift_align += 'top'
                else:
                    shift_align += 'bottom'
                if shift_left >= 0:
                    shift_align += 'left'
                else:
                    shift_align += 'right'

            direction = magick.GRAVITIES[extent_anchor]
            magick.options.append("+repage")
            magick.extent(w, h, direction, extent_background, extent_compose)
            magick.options.append("+repage")

        # Currently we do not support both an extent_shift and a splice
        if extent_shift and shift_align:
            (w, h) = extent_shift
            direction = magick.GRAVITIES[shift_align]
            magick.options.append("+repage")
            magick.splice(w, h, direction, extent_background, extent_compose)
            magick.options.append("+repage")
        elif splice and splice_size:
            (w, h) = splice_size
            direction = magick.GRAVITIES[splice_anchor]
            magick.options.append("+repage")
            magick.splice(w, h, direction, splice_background, splice_compose)
            magick.options.append("+repage")

        # post_crop_size=&post_crop_anchor=
        if post_crop_size:
            (w, h) = post_crop_size
            direction = magick.GRAVITIES[post_crop_anchor]
            # repage before and after we crop.
            magick.options.append("+repage")
            magick.crop(w, h, 0, 0, direction)
            magick.options.append("+repage")

        # reflection_height=&reflection_alpha_top=&reflection_alpha_bottom=
        if reflection_height:
            top = self.get_argument("reflection_alpha_top", 1)
            bottom = self.get_argument("reflection_alpha_bottom", 0)
            try:
                reflection_height = int(reflection_height)
                top = max(0.0, min(1.0, float(top)))
                bottom = max(0.0, min(1.0, float(bottom)))
            except:
                reflection_height = None
                top = 1.0
                bottom = 0.0

            if reflection_height:
                magick.reflect(reflection_height, top, bottom)

        # normalize=
        if normalize:
            magick.normalize()

        # equalize=
        if equalize:
            magick.equalize()

        # contrast_stretch=
        if contrast_stretch:
            (a, b) = contrast_stretch
            magick.contrast_stretch(a, b)

        # brightness_contrast=
        if brightness_contrast:
            (c, d) = brightness_contrast
            magick.brightness_contrast(c, d)

        magick.format = magick.JPEG
        format_param = self.get_argument("format", "").lower()
        if format_param[0:3] == "png":
            magick.format = magick.PNG
            if format_param == "png16":
                magick.rgb555_dither()

        self.magick = magick

    def validate_texts(self, texts, validator):
        return True

    def get_style(self, s):
        return None

    def restrict_compose_method(self, method):
        default_method = "over"
        supported_methods = [
            'over', 
            'add', 
            'subtract',
            ]
        return method if method in supported_methods else default_method 

    def set_content_type(self):
        """
        Sets the Content-Type of the request to the mime-type of the image
        according to the calculated ImageMagick parameters.
        """
        assert self.magick
        self.set_header("Content-Type", self.magick.get_mime_type())

    def convert_image(self, source):
        """
        Takes a local path or URL and processes it through ImageMagick convert.
        The result is written to the response (via self.write) and also handles
        finishing the request.  Raises a 404 error if the file is local and
        doesn't exist, or if source is None.
        """
        assert self.magick

        logger.debug("converting %s" % source)
        if not source or (not is_remote(source) and not os.path.isfile(source)):
            raise HTTPError(404)

        self.set_content_type()
        self.magick.convert(source,
            chunk_ready=self.on_conv_chunk_ready,
            complete=self.on_conv_complete,
            error=self.on_conv_error) 

    def on_conv_error(self):
        """
        On conversion error, raise a 500 Server Error and log.
        """
        logger.error("Conversion failed for %s" % self.request.uri)
        raise HTTPError(500)

    def on_conv_chunk_ready(self, chunk):
        """
        When a chunk of the converted image is ready, this callback is
        initiated with the chunk that was just read.
        """
        logger.debug("read %d bytes" % len(chunk))
        self.write(chunk)

    def on_conv_complete(self):
        """
        Once the image is fully converted and all data is read, this callback
        will be initiated.
        """
        self.finish()

class CachingImageHandler(ImageHandler):
    """
    ImageHandler that caches requests as necessary. You should override the
    get_cache_name, on_cache_hit and on_cache_write methods.
    """
    @asynchronous
    def get(self, *args):
        self.calculate_options()
        if self.is_cached():
            self.set_content_type()
            self.on_cache_hit()
            self.finish()
        else:
            self.on_cache_miss()
            self.handler(*args)

    def on_conv_chunk_ready(self, chunk):
        """
        Call into write handler on chunk ready.
        """
        super(CachingImageHandler, self).on_conv_chunk_ready(chunk)
        self.on_cache_write(chunk)

    def on_conv_complete(self):
        """
        Hook our cache write complete on conversion complete.
        """
        super(CachingImageHandler, self).on_conv_complete()
        self.on_cache_write_complete()

    def is_cached(self):
        """
        Return True if this request is already cached.
        """
        raise NotImplementedError()

    def on_cache_hit(self):
        """
        Called if is_cached() returns True.  The Content-Type header will be set
        and self.finish() will be called immediately after this method returns.
        """
        raise NotImplementedError()

    def on_cache_miss(self):
        """
        Called if is_cached() returns False, right before self.handler is
        called.
        """
        raise NotImplementedError()

    def on_cache_write(self, chunk):
        """
        Writes the given chunk to cache.
        """
        raise NotImplementedError()

    def on_cache_write_complete(self):
        """
        Closes cache store for the current entry, if required.
        """
        pass

class FileCachingImageHandler(CachingImageHandler):
    """
    Image handler that caches files on disk according to the filter chain defined
    by the query.
    """

    CACHE_PATH  = '/tmp'
    CREATE_MODE = 0755

    def __init__(self, *args, **kwargs):
        super(FileCachingImageHandler, self).__init__(*args, **kwargs)
        self.cache_fd = None
        self.cacheable = True
        self.identifier = None
        self.write_path = None
        self.final_path = None
        self.wrote_bytes = 0

    def is_cached(self):
        (fname, fullpath) = self.get_cache_name()

        result = None
        try:
            result = os.stat(fullpath)
        except OSError:
            result = None

        return result and result.st_size > 0

    def on_cache_hit(self):
        fullpath = self.get_cache_name()[1]
        if os.path.isfile(fullpath):
            fh = open(fullpath)
            self.write(fh.read())
            fh.close()
        else:
            raise HTTPError(404)

    def get_cache_name(self):
        # Build filename from filter chain
        filename = "base"
        if len(self.magick.filters) > 0:
            filename = "+".join(self.magick.filters)
        if self.identifier:
            filename += "%s-" % self.identifier
        filename += ".%s" % self.magick.format

        # Build /(request.path)/(filename)
        relpath = os.path.join('/', self.request.path, filename)

        # Normalize double slashes and dot notation as necessary
        relpath = os.path.normpath(relpath)

        # Strip leading slash
        relpath = relpath.lstrip('/')

        # Generate full path on disk
        fullpath = os.path.realpath(os.path.join(self.CACHE_PATH, relpath))

        return (relpath, fullpath)

    def on_cache_miss(self):
        pass

    def on_cache_write(self, chunk):
        if not self.cacheable:
            return

        if not self.cache_fd:
            self.final_path = self.get_cache_name()[1]

            # Generate a temporary write path
            self.write_path = "%s.cache.%d.%d" % (
                self.final_path, time(), randint(0, 10000))

            # Open the cache file for writing if the final and write paths do not
            # yet exist
            if not os.path.exists(self.final_path) and \
                    not os.path.exists(self.write_path):
                dname = os.path.dirname(self.write_path) 

                # Create intermediate directories as needed
                try:
                    if not os.path.isdir(dname):
                        os.makedirs(dname, mode=self.CREATE_MODE)
                except OSError, e:
                    if e.errno != EEXIST:
                        raise

                self.cache_fd = open(self.write_path, "wb")

            else:
                self.cache_fd = None
                self.write_path = None
                self.final_path = None

        if self.cache_fd and chunk:
            self.cache_fd.write(chunk)
            self.wrote_bytes += len(chunk)

    def on_cache_write_complete(self):
        if self.cache_fd:
            self.cache_fd.close()
            self.cache_fd = None

        if self.write_path and self.final_path:
            # Rename for future hits, if we wrote bytes out,
            # otherwise kill the file.
            if self.wrote_bytes > 0:
                os.rename(self.write_path, self.final_path)
            else:
                os.remove(self.write_path)
