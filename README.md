Ectyper
==========

Set of Tornado request handlers that allows on-the-fly conversion of images
according to a request's query string options.  Ectyper, by default, provides
a way to resize, reflect and reformat images.

Synopsis
==========

    from ectyper.handlers import ImageHandler
    import os
    from tornado import web, ioloop
  
    class StreamLocal(ImageHandler):
        """
        Trivial local file handler.  It loads files in images directory, converts
        it and streams it to the client.
    
        Example calls:      
          Resize:
          http://host:8888/images/hulu.jpg?size=200x96
          
          Reformat:
          http://host:8888/images/hulu.jpg?format=png
          
          Reflect:
          http://host:8888/images/hulu.jpg?size=200x96&format=png&reflection_height=60
        """
        
        def calculate_options(self):
            super(StreamLocal, self).calculate_options()
  
            # By default Ectyper uses "convert" as found in the PATH of the running
            # python process, use this to override.
            if self.magick:
                self.magick.convert_path = "/path/to/imagemagick/convert"
  
        def handler(self, *args):
            self.convert_image(os.path.join("/path/to/images", args[0]))
  
    app = web.Application([
        ('/images/(.*)', StreamLocal),
    ])
  
    if __name__ == "__main__":
        app.listen(8888)
        ioloop.IOLoop.instance().start()

Description
==========

Ectyper provides a primary ImageHandler class (extending Tornado's RequestHandler
class).  This class parses each request's query string and converts it into a
command-line call into ImageMagick's convert.  This class is wrapped by
ectyper.magick.ImageMagick which can be overridden to provide other options.

A request into an ImageHandler will automatically generate an ImageMagick
object based on standard options (see help(ectyper.handlers.ImageHandler) for
more).  Once your handler calls convert_image() with a local file path or a
remote URL, ImageHandler kicks off an ImageMagick convert process with the
calculated options and streams the result to the browser.  You can optionally
extend CachingImageHandler or FileCachingImageHandler to stream the output
elsewhere for caching purposes.

Full list of options supported by default:

    size=NxM
       Resize the source image to N pixels wide and M pixels high.

    crop=1
       Crops the image, maintaining aspect ratio, when resizing
       (ignored if size is not provided or maintain_ratio is not 1).
       Defaults to 0.

    crop_anchor=(top|bottom|left|right|center|middle|topleft|topright
       |bottomleft|bottomright)
       Anchors the crop to one location of the image.
       (ignored if crop and maintain_ratio are not both 1).
       Defaults to center

    maintain_ratio=1
       Maintain aspect ratio when resizing (ignored if size is not
       provided).

    post_crop_size=NxM
       Applies a secondary "post-crop" to the image, after the standard
       image resize is performed. This supports the case where an image 
       needs to be sized to fit a particular dimension using a crop, 
       then the image needs to be chopped up into different regions.
       Defaults to None, meaning that no post-crop is applied.

    post_crop_anchor=(top|bottom|left|right|center|middle|topleft|topright
       |bottomleft|bottomright)
       Anchors the post-crop to one location of the image.
       (ignored if post_crop_size does not exist or is invalid).
       Defaults to center

    reflection_height=N
       Flip the image upside down and apply a gradient to mimic a
       reflected image.  reflection_alpha_top and reflection_alpha_bottom
       can be used to set the gradient parameters.

    reflection_alpha_top=N
       The top value to use when generating the gradient for
       reflection_height, ignored if that parameter is not set.  Should be
       between 0 and 1. Defaults to 1.

    reflection_alpha_bottom=N
       The bottom value to use when generating the gradient for
       reflection_height, ignored if that parameter is not set.  Should be
       between 0 and 1.  Defaults to 0.

    format=(jpeg|png|png16)
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

Examples
==========

See example.py for more.

License
==========

Copyright (C) 2010-2011 by Hulu, LLC

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in
all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
THE SOFTWARE.

Contact
==========

For support or for further questions, please contact:

      ectyper-dev@googlegroups.com
