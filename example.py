import hashlib
from ectyper.handlers import ImageHandler, FileCachingImageHandler
import logging
import os
from tornado import httpclient, ioloop, web
from tornado.options import define, options, parse_command_line
from xml.parsers.expat import ParserCreate

class FlickrExample(ImageHandler):
    """
    Example Flickr handler.  It loads the public Flickr feed and picks the
    first image from the feed to convert, converts it and streams it to the
    client.

    Example calls:
      http://host:8888/recent_flickr?size=200x100&maintain_ratio=1
      http://host:8888/recent_flickr?size=25x25
      http://host:8888/recent_flickr?size=300x300&format=png
    """

    def handler(self, *args):
        http = httpclient.AsyncHTTPClient()
        http.fetch("http://api.flickr.com/services/feeds/photos_public.gne",
            callback=self.on_response)

    def on_response(self, response):
        parser = ParserCreate()

        def _s(name, attrs):
            url = attrs.get("href", None)
            rel = attrs.get("rel", None)
            if name == "link" and url and rel == "enclosure":
                self.convert_image(url)
                parser.StartElementHandler = None

        parser.StartElementHandler = _s
        parser.Parse(response.body, True)

class GravatarCacheExample(FileCachingImageHandler):
    """
    Gravatar already provides resizing capabilities, but this is
    just an example to show how caching would work.

    Example calls:

      http://host:8888/gravatar/example@example.com

      Image would be cached to:
      /tmp/ex/gravatar/example@example.com/base.jpeg

      http://host:8888/gravatar/example@example.com?size=10x10

      Image would be cached to:
      /tmp/ex/gravatar/example@example.com/resize_10_10_0+constrain_10_10.jpeg
    """
    CACHE_PATH = "/tmp/ex"
    
    def handler(self, *args):
        ident = hashlib.md5(args[0].strip().lower()).hexdigest()
        self.convert_image("http://www.gravatar.com/avatar/%s" % ident)

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
    
    def handler(self, *args):
        self.convert_image(os.path.join("images", args[0]))

application = web.Application([
    ('/recent_flickr', FlickrExample),
    ('/gravatar/(.*)', GravatarCacheExample),
    ('/images/(.*)', StreamLocal),
])

if __name__ == "__main__":
    define("debug",
        type=int,
        default=0,
        help="Show all debug log lines from ectyper")
    parse_command_line()

    if options.debug == 1:
        log = logging.getLogger("ectyper")
        log.setLevel(logging.DEBUG)
        log.addHandler(logging.StreamHandler())

    application.listen(8888)
    ioloop.IOLoop.instance().start()
