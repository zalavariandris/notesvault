"""Qt signal and timer adapter for application workflows."""
from PySide6.QtCore import QCoreApplication, QEvent, QObject, Qt, QTimer, Signal, Slot

from ..controller import BackupController


class NotesVaultController(BackupController, QObject):
    changed = Signal(object)
    progress = Signal(str)
    completed = Signal(object)

    def __init__(self, config_store=None, is_demo=False):
        QObject.__init__(self)
        BackupController.__init__(self, config_store, is_demo,
                                  on_change=self.changed.emit,
                                  on_progress=self.progress.emit,
                                  on_completed=self.completed.emit)
        self.window = None
        self.progress.connect(self._log_progress, Qt.ConnectionType.QueuedConnection)
        self.completed.connect(self._finish, Qt.ConnectionType.QueuedConnection)
        self.timer = QTimer(self)
        self.timer.setInterval(1000)
        self.timer.timeout.connect(self.tick)

    @Slot(str)
    def _log_progress(self, message):
        self.log_output(message)

    @Slot(object)
    def _finish(self, completion):
        self.finish_task(completion)

    def eventFilter(self, watched, event):
        if event.type() == QEvent.Type.Close and self.state.busy:
            self.log_output("Wait for the current task to finish before closing.")
            event.ignore()
            return True
        return QObject.eventFilter(self, watched, event)

    def cleanup(self):
        self.timer.stop()
        BackupController.cleanup(self)
        if self.window is not None:
            self.window.hide()
            self.window.deleteLater()
            QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
            self.window = None
