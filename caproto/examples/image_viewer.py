import sys
import time

import caproto as ca
import numpy as np
import matplotlib
matplotlib.use('Qt5Agg')  # noqa
import matplotlib.pyplot as plt

from PyQt5.QtWidgets import QApplication, QLabel
from PyQt5 import QtGui
from PyQt5.QtCore import QThread, pyqtSlot, pyqtSignal


pv_suffixes = {
    'acquire': 'cam1:Acquire',
    'image_mode': 'cam1:ImageMode',

    'array_data': 'image1:ArrayData',
    'enabled': 'image1:EnableCallbacks',

    'unique_id': 'image1:UniqueId_RBV',
    'array_size0': 'image1:ArraySize0_RBV',
    'array_size1': 'image1:ArraySize1_RBV',
    'array_size2': 'image1:ArraySize2_RBV',
    'color_mode': 'image1:ColorMode_RBV'
}


class ImageMonitor(QThread):
    new_image_size = pyqtSignal(int, int)
    new_image = pyqtSignal(int, int, str, object)

    def __init__(self, prefix):
        super().__init__()
        self.pvs = {key: f'{prefix}{suffix}'
                    for key, suffix in pv_suffixes.items()}
        print('PVs:', self.pvs)
        self.running = True

    def stop(self):
        self.running = False


class ImageMonitorSync(ImageMonitor):
    def run(self):
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
        color_mode = caget(self.pvs['color_mode']).data[0].decode('ascii')

        self.new_image_size.emit(width, height)

        print(f'width: {width} height: {height} color_mode: {color_mode}')

        def update(pv_name, response):
            if not self.running:
                raise KeyboardInterrupt

            self.new_image.emit(width, height, color_mode, response.data)

        try:
            camonitor(self.pvs['array_data'], callback=update)
        except Exception as ex:
            print('Failed', ex)
            raise


class ImageMonitorThreaded(ImageMonitor):
    def run(self):
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

        # TODO: ew...
        color_mode = self.pvs['color_mode'].read(
            data_type=ca.ChannelType.STRING)
        color_mode = color_mode.data[0].split(b'\x00', 1)[0].decode('ascii')

        self.new_image_size.emit(width, height)

        print(f'width: {width} height: {height} color_mode: {color_mode}')

        def update(response):
            if not self.running:
                if self.sub:
                    self.sub.unsubscribe()
                    self.sub = None
                return

            self.new_image.emit(width, height, color_mode, response.data)

        self.sub = self.pvs['array_data'].subscribe()
        self.sub.add_callback(update)


def show_statistics(image_times, *, plot_times=False):
    total_images = len(image_times)

    image_times = np.array(image_times)
    times = image_times[:, 0]
    sizes = image_times[:, 1]
    times -= times[0]

    total_size = np.sum(sizes)
    title = (f'Displayed {total_images} images ({total_size // 1e6} MB) in '
             f'{times[-1]:.2f} seconds')
    print(title)

    if plot_times:
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(8, 8))

        ax2.plot(times, sizes, 'o', markersize=0.25)
        ax2.set_xlabel('Elapsed time [sec]')
        ax2.set_ylabel('Image size [bytes]')
    else:
        fig, ax1 = plt.subplots(1, 1, figsize=(8, 8))

    ax1.hist(np.diff(times), )
    ax1.set_xlabel('Delta time [sec]')
    ax1.set_ylabel('Count')

    plt.suptitle(title)
    plt.savefig('display_statistics.pdf')
    plt.show()


class ImageViewer(QLabel):
    def __init__(self, prefix, parent=None):
        super().__init__(parent=parent)

        self.image = None
        self.pixmap = None
        self.image_times = []
        self.image_formats = {
            'Mono': QtGui.QImage.Format_Grayscale8,
        }

        # self.monitor = ImageMonitorSync(prefix)
        self.monitor = ImageMonitorThreaded(prefix)
        self.monitor.new_image_size.connect(self.image_resized)
        self.monitor.new_image.connect(self.display_image)
        self.monitor.start()

    def closeEvent(self, event):
        self.monitor.stop()
        event.accept()
        if self.image_times:
            show_statistics(self.image_times)

    @pyqtSlot(int, int)
    def image_resized(self, width, height):
        self.resize(width, height)

    @pyqtSlot(int, int, str, object)
    def display_image(self, width, height, color_mode, array_data):
        print(width, height, color_mode, len(array_data), array_data[:5],
              array_data.dtype)

        self.image = QtGui.QImage(array_data, width, height,
                                  self.image_formats[color_mode],
                                  )
        self.pixmap = QtGui.QPixmap.fromImage(self.image)
        self.setPixmap(self.pixmap)
        self.image_times.append((time.monotonic(), array_data.size))


if __name__ == '__main__':
    try:
        prefix = sys.argv[1]
    except IndexError:
        prefix = '13SIM1:'

    app = QApplication(sys.argv)

    viewer = ImageViewer(prefix)
    viewer.show()
    sys.exit(app.exec_())
