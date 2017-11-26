import threading
from collections import namedtuple

import PIL
import zbar
from kivy.app import App
from kivy.clock import mainthread
from kivy.garden.xcamera import XCamera as Camera
from kivy.lang import Builder
from kivy.properties import ListProperty
from kivy.uix.anchorlayout import AnchorLayout
from kivy.utils import platform

# Pillow is not currently available for Android:
# https://github.com/kivy/python-for-android/pull/786
try:
    # Pillow
    PIL.Image.frombytes
    PIL.Image.Image.tobytes
except AttributeError:
    # PIL
    PIL.Image.frombytes = PIL.Image.frombuffer
    PIL.Image.Image.tobytes = PIL.Image.Image.tostring


class ZBarCam(AnchorLayout):
    """
    Widget that use the Camera and zbar to detect qrcode.
    When found, the `symbols` will be updated.
    """
    resolution = ListProperty([640, 480])

    symbols = ListProperty([])

    Qrcode = namedtuple(
            'Qrcode', ['type', 'data', 'bounds', 'quality', 'count'])

    def __init__(self, **kwargs):
        super(ZBarCam, self).__init__(**kwargs)
        self._detect_qrcode_frame_thread = None
        self._camera = Camera(
                play=True,
                resolution=self.resolution)
        self._remove_shoot_button()
        self._enable_android_autofocus()
        self._camera._camera.bind(on_texture=self._on_texture)
        self.add_widget(self._camera)
        # create a scanner used for detecting qrcode
        self.scanner = zbar.ImageScanner()

    def _remove_shoot_button(self):
        """
        Removes the "shoot button", see:
        https://github.com/kivy-garden/garden.xcamera/pull/3
        """
        xcamera = self._camera
        shoot_button = xcamera.children[0]
        xcamera.remove_widget(shoot_button)

    def _enable_android_autofocus(self):
        """
        Enables autofocus on Android.
        """
        if platform != 'android':
            return
        camera = self._camera._camera._android_camera
        params = camera.getParameters()
        params.setFocusMode('continuous-video')
        camera.setParameters(params)

    def _on_texture(self, instance):
        """
        Starts the QRCode detector thread.
        """
        # if a thread is already alive/working skip it
        if self._detect_qrcode_frame_thread \
                and self._detect_qrcode_frame_thread.is_alive():
            return
        kwargs = {
            'instance': None,
            'camera': instance,
            'texture': instance.texture,
            # have to pass the pixels separately or we get the exception:
            # `Shader didnt link, check info log.`
            'pixels': instance.texture.pixels,
        }
        self._detect_qrcode_frame_thread = threading.Thread(
            target=self._detect_qrcode_frame, kwargs=kwargs)
        self._detect_qrcode_frame_thread.start()

    @mainthread
    def _update_symbols(self, symbols):
        """
        OpenGL related operations (widget, canvas, property manipulation etc.)
        should be done only in the main thread.
        """
        self.symbols = symbols

    def _detect_qrcode_frame(self, instance, camera, texture, pixels):
        size = texture.size
        fmt = texture.colorfmt.upper()
        pil_image = PIL.Image.frombytes(mode=fmt, size=size, data=pixels)
        # convert to greyscale; since zbar only works with it
        pil_image = pil_image.convert('L')
        width, height = pil_image.size
        raw_image = pil_image.tobytes()
        zimage = zbar.Image(width, height, "Y800", raw_image)
        result = self.scanner.scan(zimage)
        if result == 0:
            self.symbols = []
            return
        # we detected qrcode extract and dispatch them
        symbols = []
        for symbol in zimage:
            qrcode = ZBarCam.Qrcode(
                type=symbol.type,
                data=symbol.data,
                quality=symbol.quality,
                count=symbol.count,
                bounds=None)
            symbols.append(qrcode)
        self._update_symbols(symbols)

    def start(self):
        self._camera.play = True

    def stop(self):
        self._camera.play = False


DEMO_APP_KV_LANG = """
#:import platform kivy.utils.platform
BoxLayout:
    orientation: 'vertical'
    ZBarCam:
        id: zbarcam
        allow_stretch: True
        # Android camera rotation workaround, refs:
        # https://github.com/AndreMiras/garden.zbarcam/issues/3
        canvas.before:
            PushMatrix
            Rotate:
                angle: -90 if platform == 'android' else 0
                origin: self.center
        canvas.after:
            PopMatrix
    Label:
        size_hint: None, None
        size: self.texture_size[0], 50
        text: ", ".join([str(symbol.data) for symbol in zbarcam.symbols])
"""


class DemoApp(App):

    def build(self):
        return Builder.load_string(DEMO_APP_KV_LANG)


if __name__ == '__main__':
    DemoApp().run()
