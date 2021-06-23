import numpy as np
import pandas as pd
from PyQt5 import QtWidgets, QtCore, QtGui
import zipfile
import traceback, sys
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from mpl_toolkits import mplot3d
import matplotlib.pyplot as plt
from pyqtgraph import PlotWidget, plot
import pyqtgraph as pg
import pyqtgraph.opengl as gl


class WorkerSignals(QtCore.QObject):
    """
    Defines the signals available from a running worker thread.

    Supported signals are:

    finished
        No data

    error
        tuple (exctype, value, traceback.format_exc() )

    result
        object data returned from processing, anything

    """
    finished = QtCore.pyqtSignal()
    error = QtCore.pyqtSignal(tuple)
    result = QtCore.pyqtSignal(object)


# a worker to process IO-threaded stuff
class Worker(QtCore.QRunnable):
    """
    Worker thread

    Inherits from QRunnable to handler worker thread setup, signals and wrap-up.

    :param callback: The function callback to run on this worker thread. Supplied args and
                     kwargs will be passed through to the runner.
    :type callback: function
    :param args: Arguments to pass to the callback function
    :param kwargs: Keywords to pass to the callback function

    """

    def __init__(self, fn, *args, **kwargs):
        super(Worker, self).__init__()
        # Store constructor arguments (re-used for processing)
        self.fn = fn
        self.args = args
        self.kwargs = kwargs
        self.signals = WorkerSignals()

    @QtCore.pyqtSlot()
    def run(self):
        """
        Initialise the runner function with passed args, kwargs.
        """

        # Retrieve args/kwargs here; and fire processing using them
        try:
            result = self.fn(
                *self.args, **self.kwargs
            )
        except:
            traceback.print_exc()
            exctype, value = sys.exc_info()[:2]
            self.signals.error.emit((exctype, value, traceback.format_exc()))
        else:
            self.signals.result.emit(result)  # Return the result of the processing
        finally:
            self.signals.finished.emit()  # Done


def _open_file(file_name):
    if file_name:
        if file_name.endswith(".braidz"):
            archive = zipfile.ZipFile(file=file_name, mode='r')
            df = pd.read_csv(
                archive.open('kalman_estimates.csv.gz'),
                comment="#",
                compression="gzip")

        elif file_name.endswith(".h5"):
            df = pd.read_hdf(file_name, key='kalman_estimates', mode='r')

    return df


class MainWindow(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Braidz GUI")
        self.setGeometry(100, 100, 800, 600)
        self.file_name = None
        self.df = pd.DataFrame([])

        self.thread_pool = QtCore.QThreadPool()

        self.initialize_ui()

    def initialize_ui(self):
        outer_layout = QtWidgets.QHBoxLayout()  # main two-column layout
        left_layout = QtWidgets.QVBoxLayout()  # left layout for open file button, filter menu, and item list

        # button to open file
        self.open_button = QtWidgets.QPushButton("Browse...")
        self.open_button.clicked.connect(self.open_file)

        # status line
        self.status_line = QtWidgets.QLabel()
        self.status_line.setText("Waiting...")

        # grid layout for limits and obs numbers
        self.grid_layout = QtWidgets.QFormLayout()
        self.grid_layout.addRow("Min Obs.", QtWidgets.QLineEdit())
        self.grid_layout.addRow("Xlim", QtWidgets.QLineEdit())
        self.grid_layout.addRow("Ylim", QtWidgets.QLineEdit())
        self.grid_layout.addRow("Zlim", QtWidgets.QLineEdit())

        # list view
        self.obj_list_widget = QtWidgets.QListWidget()
        #self.obj_list_widget.setSelectionMode(QtWidgets.QListWidget.MultiSelection)
        self.obj_list_widget.itemClicked.connect(self._obj_selected)

        # configure left layout
        left_layout.addWidget(self.open_button)
        left_layout.addWidget(self.status_line)
        left_layout.addLayout(self.grid_layout)
        left_layout.addWidget(self.obj_list_widget)

        # plot frame
        # figure_frame = QtWidgets.QFrame()
        self.figure_widget = gl.GLViewWidget()

        # configure outer layout
        outer_layout.addLayout(left_layout, 1)
        outer_layout.addWidget(self.figure_widget, 4)

        self.setLayout(outer_layout)

    def open_file(self):
        options = QtWidgets.QFileDialog.Options()
        self.file_name, _ = QtWidgets.QFileDialog.getOpenFileName(self,
                                                                  caption="Open File",
                                                                  filter="Braidz (*.braidz);;flydra h5 (*.h5)",
                                                                  options=options)
        self.status_line.setText("Opening file...")
        worker = Worker(_open_file, self.file_name)
        worker.signals.finished.connect(self._thread_complete)
        worker.signals.result.connect(self._get_data)
        self.thread_pool.start(worker)

    def populate_list(self):
        for obj, _ in self.df.groupby('obj_id'):
            self.obj_list_widget.addItem(str(obj))

    def filter_objects(self):
        pass

    def _obj_selected(self, item):
        traces = []
        obj_id = int(item.text())
        obj_idx = (self.df['obj_id'] == obj_id).values
        pts = np.column_stack((self.df[obj_idx]['x'].values,
                               self.df[obj_idx]['y'].values,
                               self.df[obj_idx]['z'].values))
        traces.append(gl.GLLinePlotItem(pos=pts))
        self.plot_obj(traces)

    def plot_obj(self, traces):
        for trace in traces:
            self.figure_widget.addItem(trace)

    def _thread_complete(self):
        self.status_line.setText("Finished opening")
        self.populate_list()

    def _get_data(self, result):
        self.df = result


if __name__ == '__main__':
    app = QtWidgets.QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())

