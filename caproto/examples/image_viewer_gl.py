import time
import sys
from PyQt5 import QtWidgets, QtCore, QtGui
from PyQt5.QtWidgets import QOpenGLWidget
from PyQt5.QtGui import QOpenGLBuffer

import matplotlib
import numpy as np
import ctypes
from contextlib import contextmanager

import threading

from PyQt5.QtCore import pyqtSlot
from caproto.examples.image_viewer import (ImageMonitorThreaded,
                                           show_statistics,
                                           get_image_size,
                                           get_array_dimensions)

from caproto import ChannelType


def setup_vertex_buffer(gl, data, shader, shader_variable):
    'Setup a vertex buffer with `data` vertices as `shader_variable` on shader'
    vbo = QOpenGLBuffer(QOpenGLBuffer.VertexBuffer)
    vbo.create()
    with bind(vbo):
        vertices = np.array(data, np.float32)
        count, dim_vertex = vertices.shape
        vbo.allocate(vertices.flatten(), vertices.nbytes)

        attr_loc = shader.attributeLocation(shader_variable)
        shader.enableAttributeArray(attr_loc)
        shader.setAttributeBuffer(attr_loc, gl.GL_FLOAT, 0, dim_vertex)
    return vbo


def initialize_pbo(pbo, data, *, mapped_array=None):
    with bind(pbo):
        full_size = data.nbytes
        width, height, depth = data.shape

        if pbo.isCreated() and pbo.size() >= full_size and mapped_array is not None:
            mapped_array[:] = data.reshape((width, height, depth))
            return mapped_array

    pbo.create()
    with bind(pbo):
        pbo.allocate(data, full_size)

        ptr = pbo.map(QOpenGLBuffer.WriteOnly)
        assert ptr is not None, 'Failed to map pixel buffer array'

        dest = ctypes.cast(int(ptr), ctypes.POINTER(ctypes.c_byte))
        mapped_array = np.ctypeslib.as_array(dest, shape=(width, height, depth))
        pbo.unmap()
    return mapped_array


def update_pbo_texture(gl, pbo, texture, *, array_data, texture_format,
                       source_format, source_type):

    width, height, depth = array_data.shape

    with bind(pbo, texture):
        gl.glTexParameteri(gl.GL_TEXTURE_2D, gl.GL_TEXTURE_MIN_FILTER,
                           gl.GL_LINEAR)
        gl.glTexParameteri(gl.GL_TEXTURE_2D, gl.GL_TEXTURE_MAG_FILTER,
                           gl.GL_LINEAR)
        gl.glTexImage2D(gl.GL_TEXTURE_2D, 0, texture_format, width, height, 0,
                        source_format, source_type, None)


@contextmanager
def bind(*objs, args=None):
    'Bind all objs (optionally with positional arguments); releases at cleanup'
    if args is None:
        args = ()

    for obj in objs:
        obj.bind(*args)
    yield
    for obj in objs[::-1]:
        obj.release()


class ImageViewerWidget(QOpenGLWidget):
    image_formats = {
        # Monochromatic image
        ('Mono', ChannelType.CHAR): ('GL_RED', 'GL_UNSIGNED_BYTE'),
        ('Mono', ChannelType.INT): ('GL_RED', 'GL_UNSIGNED_SHORT'),
        ('Mono', ChannelType.LONG): ('GL_RED', 'GL_UNSIGNED_INT'),
        ('Mono', ChannelType.FLOAT): ('GL_RED', 'GL_FLOAT'),
        ('Mono', ChannelType.DOUBLE): ('GL_RED', 'GL_DOUBLE'),

        # RGB image with pixel color interleave, data array is [3, NX, NY]
        ('RGB1', ChannelType.CHAR): ('GL_RGB', 'GL_UNSIGNED_BYTE'),
        ('RGB1', ChannelType.INT): ('GL_RGB', 'GL_UNSIGNED_SHORT'),
        ('RGB1', ChannelType.LONG): ('GL_RGB', 'GL_UNSIGNED_INT'),
        ('RGB1', ChannelType.FLOAT): ('GL_RGB', 'GL_FLOAT'),
        ('RGB1', ChannelType.DOUBLE): ('GL_RGB', 'GL_DOUBLE'),

        # RGB image with line/row color interleave, data array is [NX, 3, NY]
        ('RGB2', ChannelType.CHAR): ('GL_RGB', 'GL_UNSIGNED_BYTE'),
        ('RGB2', ChannelType.INT): ('GL_RGB', 'GL_UNSIGNED_SHORT'),
        ('RGB2', ChannelType.LONG): ('GL_RGB', 'GL_UNSIGNED_INT'),
        ('RGB2', ChannelType.FLOAT): ('GL_RGB', 'GL_FLOAT'),
        ('RGB2', ChannelType.DOUBLE): ('GL_RGB', 'GL_DOUBLE'),

        # # RGB image with plane color interleave, data array is [NX, NY, 3]
        ('RGB3', ChannelType.CHAR): ('GL_RGB', 'GL_UNSIGNED_BYTE'),
        ('RGB3', ChannelType.INT): ('GL_RGB', 'GL_UNSIGNED_SHORT'),
        ('RGB3', ChannelType.LONG): ('GL_RGB', 'GL_UNSIGNED_INT'),
        ('RGB3', ChannelType.FLOAT): ('GL_RGB', 'GL_FLOAT'),
        ('RGB3', ChannelType.DOUBLE): ('GL_RGB', 'GL_DOUBLE'),

        # TODO need a shader to support Bayer and YUV formats.

        # # Bayer pattern image, 1 value per pixel, with color filter on detector
        # 'Bayer': (np.uint8, 'GL_RED', 'GL_UNSIGNED_BYTE'),

        # # YUV image, 3 bytes encodes 1 RGB pixel
        # 'YUV444': (np., 'GL_RED', 'GL_UNSIGNED_BYTE'),

        # # YUV image, 4 bytes encodes 2 RGB pixel
        # 'YUV422': (np., 'GL_RED', 'GL_UNSIGNED_BYTE'),

        # # YUV image, 6 bytes encodes 4 RGB pixels
        # 'YUV421': (np., 'GL_RED', 'GL_UNSIGNED_BYTE'),
    }

    bayer_patterns = {
        # First line RGRG, second line GBGB...
        "RGGB": '',
        # First line GBGB, second line RGRG...
        "GBRG": '',
        # First line GRGR, second line BGBG...
        "GRBG": '',
        # First line BGBG, second line GRGR...
        "BGGR": '',
    }

    vertex_src = """\
        #version 410 core

        in vec3 position;
        in vec2 texCoord;
        uniform mat4 mvp;

        // Output of vertex shader stage, to fragment shader:
        out VS_OUT
        {
                vec2 texc;
        } vs_out;

        void main(void)
        {
            gl_Position = mvp * vec4(position, 1.0);
            vs_out.texc = texCoord;
        }
"""

    fragment_src = """\
        #version 410 core

        uniform highp sampler2D image;
        uniform highp sampler2D LUT;
        layout(location=0, index=0) out vec4 fragColor;

        // Input from vertex shader stage
        in VS_OUT
        {
            vec2 texc;
        } fs_in;

        // Output is a color for each pixel
        out vec4 color;

        void main(void)
        {
            // 1. original value would give a black and white image
            // float orig = texture(image, fs_in.texc).r;
            // color = vec4(orig, 0.0, 0.0, 1.0);

            // 2. simple texture() lookup
            float orig = texture(image, fs_in.texc).r;
            color = texture(LUT, vec2(orig, 0.0)).rgba;

            // 3. texelFetch (doesn't work)
            // float orig = texture(image, fs_in.texc).r;
            // int coord = int(orig * 255);
            // color = texelFetch(LUT, vec2(coord, 0)).rgba;
        }
"""

    def __init__(self, prefix, *, format=None, version_profile=None,
                 default_colormap='viridis'):
        self.prefix = prefix

        if format is None:
            format = QtGui.QSurfaceFormat()
            format.setVersion(3, 3)
            format.setProfile(QtGui.QSurfaceFormat.CoreProfile)
            format.setSamples(4)
            QtGui.QSurfaceFormat.setDefaultFormat(format)

        if version_profile is None:
            version_profile = QtGui.QOpenGLVersionProfile()
            version_profile.setVersion(4, 1)
            version_profile.setProfile(QtGui.QSurfaceFormat.CoreProfile)

        self.format = format
        self.version_profile = version_profile

        super().__init__()

        self.image_times = []

        self.load_colormaps()

        self.init_barrier = threading.Barrier(2)
        self.monitor = ImageMonitorThreaded(prefix, barrier=self.init_barrier)
        self.monitor.new_image_size.connect(self.image_resized)
        self.monitor.new_image.connect(self.display_image)
        self.monitor.errored.connect(self.monitor_errored)
        self.monitor.start()

        self.gl_initialized = False

        self._state = 'connecting'
        self.colormap = default_colormap

        assert default_colormap in self.lutables
        self.title = ''

    @property
    def state(self):
        return self._state

    @state.setter
    def state(self, state):
        self._state = state
        self._update_title()

    @property
    def title(self):
        return self._title

    @title.setter
    def title(self, title):
        self._title = title
        self._update_title()

    def _update_title(self):
        title = (f'caproto ADImage viewer - {self.prefix} - '
                 f'{self.state} - {self.colormap} - {self._title}')
        self.setWindowTitle(title)

    def closeEvent(self, event):
        self.monitor.stop()
        event.accept()
        if self.image_times:
            show_statistics(self.image_times)

    @pyqtSlot(Exception)
    def monitor_errored(self, ex):
        self.title = repr(ex)

    @pyqtSlot(int, int, int, str, str)
    def image_resized(self, width, height, depth, color_mode, bayer_pattern):
        width, height = get_image_size(width, height, depth, color_mode)
        self.resize(width, height)

    @pyqtSlot(float, int, int, int, str, str, object, object)
    def display_image(self, frame_timestamp, width, height, depth, color_mode,
                      bayer_pattern, dtype, array_data):
        if not self.gl_initialized:
            return

        format, type_ = self.image_formats[(color_mode, dtype)]

        width, height, depth = get_array_dimensions(width, height, depth,
                                                    color_mode)
        array_data = array_data.reshape((width, height, depth))

        self.makeCurrent()
        self.mapped_image = initialize_pbo(self.image_pbo, array_data,
                                           mapped_array=self.mapped_image)
        update_pbo_texture(self.gl, self.image_pbo, self.image_texture,
                           array_data=array_data,
                           texture_format=self.gl.GL_RGB32F,
                           source_format=format,
                           source_type=type_)
        self.update()

        if not len(self.image_times) and (time.time() - frame_timestamp > 1):
            print('(TODO) Ignoring old frame for statistics')
            return

        self.image_times.append((frame_timestamp, time.time(), array_data.nbytes))

    def initializeGL(self):
        self.gl = self.context().versionFunctions(self.version_profile)
        assert self.gl is not None

        print('-------------------------------------------------------------')
        print("GL version :", self.gl.glGetString(self.gl.GL_VERSION))
        print("GL vendor  :", self.gl.glGetString(self.gl.GL_VENDOR))
        print("GL renderer:", self.gl.glGetString(self.gl.GL_RENDERER))
        print("GL glsl    :", self.gl.glGetString(self.gl.GL_SHADING_LANGUAGE_VERSION))
        print('-------------------------------------------------------------')

        # Turn the 'GL_*' strings into actual enum values
        self.image_formats = {
            format_key: [getattr(self.gl, name) for name in format_values]
            for format_key, format_values in self.image_formats.items()
        }

        # Image texture - pixel buffer object used to map memory to this
        self.image_texture = QtGui.QOpenGLTexture(QtGui.QOpenGLTexture.Target2D)
        self.image_texture.allocateStorage()

        # Pixel buffer object used to do fast copies to GPU memory
        self.image_pbo = QOpenGLBuffer(QOpenGLBuffer.PixelUnpackBuffer)
        self.image_pbo.setUsagePattern(QOpenGLBuffer.StreamDraw)
        self.mapped_image = None  # to be mapped later when size is determined

        self.shader = QtGui.QOpenGLShaderProgram(self)
        self.shader.addShaderFromSourceCode(QtGui.QOpenGLShader.Vertex,
                                            self.vertex_src)
        self.shader.addShaderFromSourceCode(QtGui.QOpenGLShader.Fragment,
                                            self.fragment_src)
        self.shader.link()

        with bind(self.shader):
            self.matrix = QtGui.QMatrix4x4()
            self.matrix.ortho(0, 1,  # left-right
                              1, 0,  # top-bottom
                              0, 1)  # near-far
            self.shader.setUniformValue("mvp", self.matrix)

            # image: texture unit 0
            self.shader.setUniformValue('image', 0)
            # LUT: texture unit 1
            self.shader.setUniformValue('LUT', 1)

        # Vertices for rendering to screen
        self.vao_offscreen = QtGui.QOpenGLVertexArrayObject(self)
        self.vao_offscreen.create()
        self.vao = QtGui.QOpenGLVertexArrayObject(self)
        self.vao.create()

        with bind(self.vao):
            self.vertices = [(0.0, 0.0, 0.0),
                             (1.0, 0.0, 0.0),
                             (0.0, 1.0, 0.0),
                             (1.0, 1.0, 0.0),
                             ]

            self.vbo_vertices = setup_vertex_buffer(
                self.gl, data=self.vertices, shader=self.shader,
                shader_variable="position")

            self.tex = [(0.0, 0.0),
                        (1.0, 0.0),
                        (0.0, 1.0),
                        (1.0, 1.0),
                        ]
            self.vbo_tex = setup_vertex_buffer(
                self.gl, data=self.tex, shader=self.shader,
                shader_variable="texCoord")

        self.gl.glClearColor(0.0, 1.0, 0.0, 0.0)

        self.lut_texture = QtGui.QOpenGLTexture(QtGui.QOpenGLTexture.Target2D)
        self.lut_texture.allocateStorage()

        self.select_lut(self.colormap)

        print('OpenGL initialized')
        self.init_barrier.wait()

        self.state = 'Initialized'
        self.gl_initialized = True

    def load_colormaps(self):
        self.lutables = {}
        for key, cm in matplotlib.cm.cmap_d.items():
            if isinstance(cm, matplotlib.colors.LinearSegmentedColormap):
                continue
                # cm = matplotlib.colors.from_levels_and_colors(
                #     levels=range(256),
                #     colors=)

            colors = np.asarray(cm.colors, dtype=np.float32)
            self.lutables[key] = colors.reshape((len(colors), 1, 3))

    def select_lut(self, key):
        lut_data = self.lutables[key]

        lut_pbo = QOpenGLBuffer(QOpenGLBuffer.PixelUnpackBuffer)
        lut_pbo.setUsagePattern(QOpenGLBuffer.StreamDraw)
        initialize_pbo(lut_pbo, data=lut_data)
        update_pbo_texture(self.gl, lut_pbo, self.lut_texture,
                           array_data=lut_data,
                           texture_format=self.gl.GL_RGB32F,
                           source_format=self.gl.GL_RGB,
                           source_type=self.gl.GL_FLOAT)
        self.colormap = key
        self._update_title()

    def paintGL(self):
        if self.image_texture is None:
            return

        with bind(self.image_texture, args=(0, )):  # bind to 'image'
            with bind(self.lut_texture, args=(1, )):  # bind to 'LUT'
                with bind(self.shader, self.vao):
                    self.gl.glDrawArrays(self.gl.GL_TRIANGLE_STRIP, 0,
                                         len(self.vertices))

    def resizeGL(self, w, h):
        self.gl.glViewport(0, 0, w, max(h, 1))

    def keyPressEvent(self, event):
        if event.key() == QtCore.Qt.Key_Escape:
            self.close()
        elif event.key() == QtCore.Qt.Key_Space:
            keys = list(self.lutables.keys())
            next_idx = (keys.index(self.colormap) + 1) % len(keys)
            self.colormap = keys[next_idx]
            self.select_lut(self.colormap)


if __name__ == '__main__':
    try:
        prefix = sys.argv[1]
    except IndexError:
        prefix = '13SIM1:'

    print(f'Prefix: {prefix} Backend: Threaded/GL')
    app = QtWidgets.QApplication(sys.argv)
    win = ImageViewerWidget(prefix=prefix)
    win.show()
    app.exec_()
