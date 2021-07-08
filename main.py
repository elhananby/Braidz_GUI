import random
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg
from matplotlib.figure import Figure
from itertools import compress

from fastnumbers import fast_real

import matplotlib.pyplot as plt
import matplotlib as mpl
from mpl_toolkits.mplot3d import Axes3D

import numpy as np
import pandas as pd
from PyQt5 import QtWidgets, QtCore, QtGui
import zipfile
import traceback, sys
import re

from braid_analysis import braid_slicing

import matplotlib

matplotlib.use('Qt5Agg')


class MplCanvas(FigureCanvasQTAgg):

    def __init__(self, parent=None, width=5, height=4, dpi=100, proj='3d'):
        fig = Figure(figsize=(width, height), dpi=dpi)
        super(MplCanvas, self).__init__(fig)
        if proj == '3d':
            self.axes = fig.add_subplot(111, projection='3d')
        else:
            self.axes = fig.add_subplot(111)
        self.axes.clear()

    def plot_data(self, x, y, z):
        self.axes.set_xlim((-0.25, 0.25))
        self.axes.set_ylim((-0.25, 0.25))
        self.axes.set_zlim((0., 0.3))
        self.axes.plot(x, y, z)

    def plot_hist(self, vals):
        self.axes.clear()
        self.axes.hist(vals, bins=100, orientation='horizontal')

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


class MainWindow(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Braidz GUI")
        self.setGeometry(100, 100, 800, 600)
        self.file_name = None

        self.df = pd.DataFrame([])
        self.min_obs = 1000
        self.xlim = [-.25, .25]
        self.ylim = [-.25, .25]
        self.zlim = [0., 0.3]
        self.dist = 0.0

        self.axes_to_filter = ['x', 'y', 'z']

        self.keep_plot = True

        self.thread_pool = QtCore.QThreadPool()

        self.initialize_ui()

    def initialize_ui(self):
        self.outer_layout = QtWidgets.QHBoxLayout()  # main two-column layout
        self.left_layout = QtWidgets.QVBoxLayout()  # left layout for open file button, filter menu, and item list
        self.right_layout = QtWidgets.QVBoxLayout()

        # open button
        self.open_button = QtWidgets.QPushButton("Browse...")
        self.open_button.clicked.connect(self.open_file_callback)

        # status line
        self.status_line = QtWidgets.QLabel()
        self.status_line.setText("Waiting...")

        # grid layout for limits and obs numbers
        self.grid_layout = QtWidgets.QFormLayout()

        # widget for minimum observation
        self.min_obs_widget = QtWidgets.QLineEdit()
        self.min_obs_widget.setText(str(self.min_obs))
        self.min_obs_widget.setDisabled(True)
        self.min_obs_widget.returnPressed.connect(self.update_values)

        # widget for x-axis limits
        self.xlim_widget = QtWidgets.QLineEdit()
        self.xlim_widget.setText(str(self.xlim))
        self.xlim_widget.setDisabled(True)
        self.xlim_widget.returnPressed.connect(self.update_values)

        # widget for y-axis limits
        self.ylim_widget = QtWidgets.QLineEdit()
        self.ylim_widget.setText(str(self.ylim))
        self.ylim_widget.setDisabled(True)
        self.ylim_widget.returnPressed.connect(self.update_values)

        # widget for z-axis limits
        self.zlim_widget = QtWidgets.QLineEdit()
        self.zlim_widget.setText(str(self.zlim))
        self.zlim_widget.setDisabled(True)
        self.zlim_widget.returnPressed.connect(self.update_values)

        # widget for setting minimum distance
        self.dist_widget = QtWidgets.QLineEdit()
        self.dist_widget.setText(str(self.dist))
        self.dist_widget.setDisabled(True)
        self.dist_widget.returnPressed.connect(self.update_values)

        # widget to select which distance we're interested in
        self.axes_selector = QtWidgets.QHBoxLayout()

        self.x_selector = QtWidgets.QCheckBox("x")
        self.x_selector.setChecked(True)
        self.x_selector.stateChanged.connect(self.axes_select)
        self.x_selector.setDisabled(True)

        self.y_selector = QtWidgets.QCheckBox("y")
        self.y_selector.setChecked(True)
        self.y_selector.stateChanged.connect(self.axes_select)
        self.y_selector.setDisabled(True)

        self.z_selector = QtWidgets.QCheckBox("z")
        self.z_selector.setChecked(True)
        self.z_selector.stateChanged.connect(self.axes_select)
        self.z_selector.setDisabled(True)

        self.axes_selector.addWidget(self.x_selector)
        self.axes_selector.addWidget(self.y_selector)
        self.axes_selector.addWidget(self.z_selector)

        # setup all widgets in a grid
        self.grid_layout.addRow("Min Obs.", self.min_obs_widget)
        self.grid_layout.addRow("Xlim", self.xlim_widget)
        self.grid_layout.addRow("Ylim", self.ylim_widget)
        self.grid_layout.addRow("Zlim", self.zlim_widget)
        self.grid_layout.addRow("Dist", self.dist_widget)
        self.grid_layout.addRow("Axes", self.axes_selector)

        # list view
        self.obj_list_widget = QtWidgets.QListWidget()
        self.obj_list_widget.setSelectionMode(QtWidgets.QListWidget.SingleSelection)
        self.obj_list_widget.itemSelectionChanged.connect(self.obj_selected)
        #self.obj_list_widget.itemChanged.connect(self.obj_selected)

        # configure left layout
        self.left_layout.addWidget(self.open_button)
        self.left_layout.addWidget(self.status_line)
        self.left_layout.addLayout(self.grid_layout)
        self.left_layout.addWidget(self.obj_list_widget)

        # define figure
        self.traj_fig = MplCanvas(self, width=5, height=4, dpi=100)

        # define statistics figure
        self.stats_figs = QtWidgets.QVBoxLayout()
        self.obs_hist = MplCanvas(self, width=2, height=2, dpi=100, proj='2d')
        self.dist_hist = MplCanvas(self, width=2, height=2, dpi=100, proj='2d')
        self.stats_figs.addWidget(self.obs_hist)
        self.stats_figs.addWidget(self.dist_hist)

        # configure outer layout
        self.outer_layout.addLayout(self.left_layout, 1)
        self.outer_layout.addWidget(self.traj_fig, 4)
        # self.outer_layout.addLayout(self.stats_figs, 1)

        # set complete layout
        self.setLayout(self.outer_layout)

    def axes_select(self):
        buttons_state = [self.x_selector.isChecked(), self.y_selector.isChecked(), self.z_selector.isChecked()]
        axes = ['x', 'y', 'z']
        self.axes_to_filter = list(compress(axes, buttons_state))

        self.populate_list()

    def obj_selected(self):
        items = self.obj_list_widget.selectedItems()

        for item in items:
            obj_id = int(item.text())
            obj_idx = (self.df['obj_id'] == obj_id).values
            x = self.df[obj_idx]['x'].values
            y = self.df[obj_idx]['y'].values
            z = self.df[obj_idx]['z'].values

            if not self.keep_plot:
                self.traj_fig.axes.clear()

            self.traj_fig.plot_data(x, y, z)
        self.traj_fig.draw()

    def update_values(self):

        # get values from textboxes
        self.min_obs = fast_real(re.compile(r'\d+').findall(self.min_obs_widget.text())[0])

        p = re.compile(r'-?\d+\.?\d?')
        self.xlim = [fast_real(i) for i in p.findall(self.xlim_widget.text())]
        self.ylim = [fast_real(i) for i in p.findall(self.ylim_widget.text())]
        self.zlim = [fast_real(i) for i in p.findall(self.zlim_widget.text())]
        self.dist = fast_real(p.findall(self.dist_widget.text())[0])

        # and repopulate list
        self.populate_list()

    def populate_list(self):
        # a function to populate list with cleaned obj_ids
        # very inefficient

        self.obj_list_widget.clear()
        obj_ids = braid_slicing.get_long_obj_ids_fast_pandas(self.df, length=self.min_obs)

        #self.obs_hist.plot_hist(
        #    self.df[self.df['obj_id'].isin(obj_ids)].groupby('obj_id').size().to_numpy()
        #)

        obj_ids = braid_slicing.get_middle_of_tunnel_obj_ids_fast_pandas(
            self.df[self.df['obj_id'].isin(obj_ids)],
            zmin=self.zlim[0], zmax=self.zlim[1],
            ymin=self.ylim[0], ymax=self.ylim[1],
            xmin=self.xlim[0], xmax=self.xlim[1]
        )

        obj_ids, lens = braid_slicing.get_trajectories_that_travel_far(
            self.df[self.df['obj_id'].isin(obj_ids)],
            axis=self.axes_to_filter,
            dist_travelled=self.dist
        )

        # self.dist_hist.plot_hist(lens)

        # add the items to the list
        self.obj_list_widget.addItems([str(obj) for obj in sorted(obj_ids)])

        # and at this point, the list is full and we can allow setting limit values
        self.min_obs_widget.setDisabled(False)
        self.xlim_widget.setDisabled(False)
        self.ylim_widget.setDisabled(False)
        self.zlim_widget.setDisabled(False)
        self.dist_widget.setDisabled(False)
        self.x_selector.setDisabled(False)
        self.y_selector.setDisabled(False)
        self.z_selector.setDisabled(False)

    def open_file_callback(self):
        options = QtWidgets.QFileDialog.Options()
        self.file_name, _ = QtWidgets.QFileDialog.getOpenFileName(self,
                                                                  caption="Open File",
                                                                  filter="Braidz/flydra (*.braidz *.h5)",
                                                                  options=options)
        self.status_line.setText("Opening file...")
        worker = Worker(self.open_file, self.file_name)
        worker.signals.finished.connect(self.thread_complete)
        worker.signals.result.connect(self.get_data)
        self.thread_pool.start(worker)

    def thread_complete(self):
        self.status_line.setText("Finished opening")
        self.populate_list()

    def get_data(self, result):
        self.df = result

    def open_file(self, file_name):
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


if __name__ == '__main__':
    app = QtWidgets.QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())
