import sys
import time
import threading

import caproto as ca
import numpy as np
import matplotlib
matplotlib.use('Qt5Agg')  # noqa
import matplotlib.pyplot as plt

from PyQt5.QtWidgets import (QApplication, QWidget, QLabel,
                             QVBoxLayout)
from PyQt5 import QtGui, QtCore
from PyQt5.QtCore import QThread, pyqtSlot, pyqtSignal
from caproto import ChannelType


pv_suffixes = {
    'acquire': 'cam1:Acquire',
    'image_mode': 'cam1:ImageMode',

    'array_data': 'image1:ArrayData',
    'enabled': 'image1:EnableCallbacks',

    'unique_id': 'image1:UniqueId_RBV',
    'array_size0': 'image1:ArraySize0_RBV',
    'array_size1': 'image1:ArraySize1_RBV',
    'array_size2': 'image1:ArraySize2_RBV',
    'color_mode': 'image1:ColorMode_RBV',
    'bayer_pattern': 'image1:BayerPattern_RBV',
}


def get_image_size(width, height, depth, color_mode):
    # TODO all wrong
    if color_mode == 'Mono':
        return (width, height)
    elif color_mode == 'RGB1':
        return (height, depth)
    elif color_mode == 'RGB2':
        return (width, depth)
    elif color_mode == 'RGB3':
        return (width, height)


def get_array_dimensions(width, height, depth, color_mode):
    width, height, depth = (sz if sz else 1
                            for sz in (width, height, depth))

    if color_mode == 'Mono':
        return (width, height, depth)
    elif color_mode == 'RGB1':
        return (width, height, depth)
    elif color_mode == 'RGB2':
        return (width, 3, depth)
    elif color_mode == 'RGB3':
        return (width, height, 3)


class ImageMonitor(QThread):
    # new_image_size: width, height, depth, color_mode, bayer_pattern
    new_image_size = pyqtSignal(int, int, int, str, str)

    # new_image: timestamp, width, height, depth, color_mode, bayer_pattern,
    #            ChannelType, array_data
    new_image = pyqtSignal(float, int, int, int, str, str, object, object)

    errored = pyqtSignal(Exception)

    def __init__(self, prefix, *, barrier=None):
        super().__init__()
        self.barrier = barrier
        self.pvs = {key: f'{prefix}{suffix}'
                    for key, suffix in pv_suffixes.items()}
        print('PVs:', self.pvs)
        self.stop_event = threading.Event()

    def stop(self):
        self.stop_event.set()

    def run(self):
        try:
            self._run()
        except Exception as ex:
            self.errored.emit(ex)


class ImageMonitorSync(ImageMonitor):
    def _run(self):
        from caproto.sync.client import (get as caget,
                                         put as caput,
                                         monitor as camonitor)
        caput(self.pvs['enabled'], 1)
        caput(self.pvs['image_mode'], 'Continuous')

        try:
            caput(self.pvs['acquire'], 'Acquire', verbose=True)
        except TimeoutError:
            ...
            # TODO: a wait=false option on sync client?

        width = caget(self.pvs['array_size0']).data[0]
        height = caget(self.pvs['array_size1']).data[0]
        depth = caget(self.pvs['array_size2']).data[0]
        color_mode = caget(self.pvs['color_mode']).data[0].decode('ascii')
        bayer_pattern = caget(self.pvs['bayer_pattern'])
        bayer_pattern = bayer_pattern.data[0].decode('ascii')

        self.new_image_size.emit(width, height, depth, color_mode,
                                 bayer_pattern)

        print(f'width: {width} height: {height} depth: {depth} '
              f'color_mode: {color_mode}')

        def update(pv_name, response):
            if self.stop_event.is_set():
                raise KeyboardInterrupt

            native_type = ca.field_types['native'][response.data_type]
            # TODO server timestamps
            self.new_image.emit(time.time(), width, height, depth, color_mode,
                                bayer_pattern, native_type, response.data)

        if self.barrier is not None:
            # Synchronize with image viewer widget, if necessary
            self.barrier.wait()

        camonitor(self.pvs['array_data'], callback=update)
        self.stop_event.wait()


class ImageMonitorThreaded(ImageMonitor):
    def _run(self):
        from caproto.threading.client import Context, SharedBroadcaster
        broadcaster = SharedBroadcaster(log_level='INFO')
        context = Context(broadcaster, log_level='INFO')

        self.pvs = {key: pv for key, pv in
                    zip(self.pvs, context.get_pvs(*self.pvs.values()))
                    }
        for pv in self.pvs.values():
            pv.wait_for_connection()

        self.pvs['enabled'].write([1], wait=True)
        self.pvs['image_mode'].write(b'Continuous', wait=True)
        self.pvs['acquire'].write(b'Acquire', wait=False)

        width = self.pvs['array_size0'].read().data[0]
        height = self.pvs['array_size1'].read().data[0]
        depth = self.pvs['array_size2'].read().data[0]

        color_mode = self.pvs['color_mode'].read(
            data_type=ca.ChannelType.STRING)
        color_mode = color_mode.data[0].decode('ascii')

        bayer_pattern = self.pvs['bayer_pattern'].read(
            data_type=ca.ChannelType.STRING)
        bayer_pattern = bayer_pattern.data[0].decode('ascii')

        self.new_image_size.emit(width, height, depth, color_mode,
                                 bayer_pattern)

        print(f'width: {width} height: {height} depth: {depth} '
              f'color_mode: {color_mode}')

        def update(response):
            if self.stop_event.is_set():
                if self.sub is not None:
                    self.sub.clear()
                    self.sub = None
                return

            native_type = ca.field_types['native'][response.data_type]
            self.new_image.emit(response.metadata.timestamp, width, height,
                                depth, color_mode, bayer_pattern,
                                native_type, response.data)

        array_data = self.pvs['array_data']
        dtype = ca.field_types['time'][array_data.channel.native_data_type]

        if self.barrier is not None:
            # Synchronize with image viewer widget, if necessary
            self.barrier.wait()

        self.sub = self.pvs['array_data'].subscribe(data_type=dtype)
        # NOTE: threading client requires that the callback function stays in
        # scope, as it uses a weak reference.
        self.sub.add_callback(update)
        print('Monitor has begun')
        self.stop_event.wait()


def show_statistics(image_times, *, plot_times=True):
    total_images = len(image_times)

    image_times = np.array(image_times)
    frame_times = image_times[:, 0]
    display_times = image_times[:, 1]
    sizes = image_times[:, 2]

    time_base = frame_times[0]
    frame_times -= time_base
    display_times -= time_base

    frame_times = frame_times[:len(display_times)]

    if not len(frame_times):
        return

    avg_frame = np.average(np.diff(frame_times))

    total_size = np.sum(sizes)
    title = (f'Displayed {total_images} images ({total_size // 1e6} MB) '
             f'in {display_times[-1]:.1f} sec\n'
             f'Frame time average from server timestamps is '
             f'{int(avg_frame * 1000)} ms')
    print()
    print(title)

    fig, ax1 = plt.subplots(1, 1)

    max_range = avg_frame * 15
    bins = int(max_range / 0.002)  # 2ms bins

    ax1.hist((display_times - frame_times), label='IOC to screen latency', alpha=0.5,
             range=(0.0, max_range),
             bins=bins,
             )
    ax1.hist(np.diff(display_times), label='Frame-to-frame', alpha=0.5,
             range=(0.0, max_range),
             bins=bins,
             )
    ax1.set_xlabel('Time [sec]')
    ax1.set_ylabel('Count')
    plt.legend()

    plt.suptitle(title)
    plt.savefig('display_statistics.pdf')
    plt.show()


class ImageMonitorPyepics(ImageMonitor):
    def _run(self):
        import epics

        self.epics = epics
        epics.ca.use_initial_context()
        self.pvs = {key: epics.PV(pv, auto_monitor=True)
                    for key, pv in self.pvs.items()}
        for pv in self.pvs.values():
            pv.wait_for_connection()

        self.pvs['enabled'].put(1)
        self.pvs['image_mode'].put('Continuous', wait=True)
        self.pvs['acquire'].put('Acquire')

        width = self.pvs['array_size0'].get()
        height = self.pvs['array_size1'].get()
        depth = self.pvs['array_size2'].get()

        color_mode = self.pvs['color_mode'].get(as_string=True)
        bayer_pattern = self.pvs['bayer_pattern'].get(as_string=True)

        self.new_image_size.emit(width, height, depth, color_mode,
                                 bayer_pattern)

        native_type = self.epics.ca.native_type

        def update(value=None, **kw):
            if self.stop_event.is_set():
                self.pvs['array_data'].remove_callback(self.sub)
                return

            field_type = self.pvs['array_data']._args['ftype']
            self.new_image.emit(time.time(), width, height, depth, color_mode,
                                bayer_pattern,
                                ChannelType(native_type(field_type)),
                                value)

        if self.barrier is not None:
            # Synchronize with image viewer widget, if necessary
            self.barrier.wait()

        self.sub = self.pvs['array_data'].add_callback(update)
        self.stop_event.wait()


class ImageViewer(QWidget):
    def __init__(self, prefix, backend, parent=None):
        super().__init__(parent=parent)

        self.layout = QVBoxLayout()
        self.status_label = QLabel('Status')
        self.layout.addWidget(self.status_label)

        self.image_label = QLabel()
        self.layout.addWidget(self.image_label)

        self.setLayout(self.layout)

        self.image = None
        self.pixmap = None
        self.image_times = []
        self.image_formats = {
            ('Mono', ChannelType.CHAR): QtGui.QImage.Format_Grayscale8,
            # TODO: others could be implemented
        }

        if backend == 'sync':
            self.monitor = ImageMonitorSync(prefix)
        elif backend == 'threaded':
            self.monitor = ImageMonitorThreaded(prefix)
        elif backend == 'pyepics':
            self.monitor = ImageMonitorPyepics(prefix)
        else:
            raise ValueError('Unknown backend')

        self.monitor.new_image_size.connect(self.image_resized)
        self.monitor.new_image.connect(self.display_image)
        self.monitor.errored.connect(self.monitor_errored)
        self.monitor.start()

    def closeEvent(self, event):
        self.monitor.stop()
        event.accept()
        if self.image_times:
            show_statistics(self.image_times)

    @pyqtSlot(Exception)
    def monitor_errored(self, ex):
        self.status_label.setText(f'{ex.__class__.__name__}: {ex}')
        print(repr(ex))

    @pyqtSlot(int, int, int, str, str)
    def image_resized(self, width, height, depth, color_mode, bayer_pattern):
        self.resize(width, height)
        self.status_label.setText(f'Image: {width}x{height} ({color_mode})')

    @pyqtSlot(float, int, int, int, str, str, object, object)
    def display_image(self, timestamp, width, height, depth, color_mode,
                      bayer_pattern, data_type, array_data):
        print(timestamp, width, height, color_mode, len(array_data),
              array_data[:5], array_data.dtype)

        image_format = self.image_formats[(color_mode, data_type)]
        self.image = QtGui.QImage(array_data, width, height, image_format)
        self.pixmap = QtGui.QPixmap.fromImage(self.image)
        self.image_label.setPixmap(self.pixmap)
        self.image_times.append((timestamp, time.time(), array_data.nbytes))

    def keyPressEvent(self, event):
        if event.key() == QtCore.Qt.Key_Escape:
            self.close()


if __name__ == '__main__':
    try:
        prefix = sys.argv[1]
    except IndexError:
        prefix = '13SIM1:'

    try:
        backend = sys.argv[2]
    except IndexError:
        backend = 'threaded'

    print(f'Prefix: {prefix} Backend: {backend}')
    app = QApplication(sys.argv)

    viewer = ImageViewer(prefix, backend)
    viewer.show()
    sys.exit(app.exec_())
