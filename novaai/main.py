"""Nova AI - persoenlicher KI-Desktop-Assistent (PySide6 + Google Gemini)."""
import base64
import sys

from PySide6.QtCore import (QBuffer, QByteArray, QEasingCurve, QIODevice, QPoint,
                            QPropertyAnimation, QThread, QTimer, Qt, Signal)
from PySide6.QtGui import QColor, QGuiApplication, QLinearGradient, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (QApplication, QDialog, QFrame, QHBoxLayout, QLabel,
                               QLineEdit, QMessageBox, QPushButton, QScrollArea,
                               QVBoxLayout, QWidget)

APP_NAME = "NovaAI"
BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"
MODELS = ["gemini-3.8-flash", "gemini-flash-latest", "gemini-2.5-flash"]
SYSTEM_PROMPT = (
    "Du bist Nova AI, ein freundlicher persoenlicher Assistent auf dem Windows-Desktop. "
    "Antworte immer auf Deutsch, klar und verstaendlich. Wenn du einen Screenshot "
    "bekommst, erkenne die Aufgabe, erklaere den Loesungsweg Schritt fuer Schritt und "
    "nenne das Ergebnis."
)
SOLVE_TRIGGERS = ("löse das", "loese das", "löse die aufgabe", "loese die aufgabe")


# ---------------------------------------------------------------- Schluessel
def load_key():
    try:
        import keyring
        return keyring.get_password(APP_NAME, "gemini_api_key")
    except Exception:
        return None


def save_key(key):
    import keyring
    keyring.set_password(APP_NAME, "gemini_api_key", key)


# ------------------------------------------------------------------- Worker
class AIWorker(QThread):
    done = Signal(str)
    failed = Signal(str)

    def __init__(self, api_key, history, image_b64=None):
        super().__init__()
        self.api_key, self.history, self.image_b64 = api_key, history, image_b64

    def run(self):
        try:
            from openai import OpenAI
            client = OpenAI(api_key=self.api_key, base_url=BASE_URL, timeout=60)
            msgs = [{"role": "system", "content": SYSTEM_PROMPT}] + list(self.history)
            if self.image_b64:
                last = msgs[-1]
                msgs[-1] = {"role": "user", "content": [
                    {"type": "text", "text": last["content"]},
                    {"type": "image_url", "image_url": {
                        "url": "data:image/png;base64," + self.image_b64}},
                ]}
            last_err = None
            for model in MODELS:
                try:
                    r = client.chat.completions.create(model=model, messages=msgs)
                    self.done.emit(r.choices[0].message.content or "")
                    return
                except Exception as e:  # noqa: BLE001
                    last_err = e
                    t = str(e).lower()
                    if "404" not in t and "not found" not in t:
                        raise
            raise last_err
        except Exception as e:  # noqa: BLE001
            self.failed.emit(str(e))


# ------------------------------------------------------------------ Widgets
STYLE = """
QLabel { color: #e8e8f2; font-family: 'Segoe UI'; font-size: 13px; }
QLineEdit { background: rgba(255,255,255,18); border: 1px solid rgba(139,92,246,120);
  border-radius: 12px; padding: 8px 12px; color: #fff; font-family: 'Segoe UI';
  font-size: 13px; }
QLineEdit:focus { border: 1px solid #8b5cf6; }
QPushButton { background: rgba(255,255,255,18); color: #e8e8f2; border: 1px solid
  rgba(255,255,255,40); border-radius: 12px; padding: 8px 12px;
  font-family: 'Segoe UI'; font-size: 12px; }
QPushButton:hover { background: rgba(139,92,246,90); }
QPushButton#send { background: qlineargradient(x1:0,y1:0,x2:1,y2:1,
  stop:0 #8b5cf6, stop:1 #3b82f6); border: none; color: white; font-weight: bold; }
QPushButton#close { background: transparent; border: none; color: #bbb; font-size: 15px;
  padding: 0; }
QPushButton#close:hover { background: #e5484d; color: white; border-radius: 10px; }
QScrollArea { border: none; background: transparent; }
QScrollBar:vertical { width: 6px; background: transparent; }
QScrollBar::handle:vertical { background: rgba(139,92,246,150); border-radius: 3px; }
"""


class Bubble(QLabel):
    def __init__(self, text, user):
        super().__init__(text)
        self.setWordWrap(True)
        self.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.setMaximumWidth(300)
        bg = ("qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 #7c3aed,stop:1 #3b82f6)"
              if user else "rgba(255,255,255,22)")
        self.setStyleSheet(f"background:{bg}; border-radius:14px; padding:9px 12px;")


class KeyDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Nova AI - API-Schluessel")
        self.setStyleSheet("QDialog{background:#14141c;}" + STYLE)
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel("Bitte gib deinen kostenlosen Gemini-API-Schluessel ein\n"
                             "(aistudio.google.com -> Get API key).\n"
                             "Er wird sicher in den Windows-Anmeldeinformationen gespeichert."))
        self.edit = QLineEdit()
        self.edit.setEchoMode(QLineEdit.Password)
        self.edit.setPlaceholderText("AIza...")
        lay.addWidget(self.edit)
        ok = QPushButton("Speichern")
        ok.setObjectName("send")
        ok.clicked.connect(self.accept)
        lay.addWidget(ok)
        self.setMinimumWidth(380)


class Nova(QWidget):
    def __init__(self, api_key):
        super().__init__()
        self.api_key = api_key
        self.history = []
        self.worker = None
        self._drag = None
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setStyleSheet(STYLE)
        self.resize(360, 520)
        geo = QGuiApplication.primaryScreen().availableGeometry()
        self.move(geo.right() - self.width() - 20, geo.top() + 20)

        root = QVBoxLayout(self)
        root.setContentsMargins(14, 10, 14, 14)
        top = QHBoxLayout()
        title = QLabel("✦  Nova AI")
        title.setStyleSheet("font-size:15px; font-weight:bold; color:#c4b5fd;")
        top.addWidget(title)
        top.addStretch()
        x = QPushButton("✕")
        x.setObjectName("close")
        x.setFixedSize(24, 24)
        x.setCursor(Qt.PointingHandCursor)
        x.clicked.connect(self.close)
        top.addWidget(x)
        root.addLayout(top)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.box = QWidget()
        self.box.setStyleSheet("background:transparent;")
        self.vl = QVBoxLayout(self.box)
        self.vl.addStretch()
        self.scroll.setWidget(self.box)
        root.addWidget(self.scroll, 1)

        self.status = QLabel("")
        self.status.setStyleSheet("color:#a78bfa; font-size:11px;")
        root.addWidget(self.status)

        row = QHBoxLayout()
        self.edit = QLineEdit()
        self.edit.setPlaceholderText("Nachricht an Nova ...")
        self.edit.returnPressed.connect(self.send)
        row.addWidget(self.edit, 1)
        btn = QPushButton("Senden")
        btn.setObjectName("send")
        btn.clicked.connect(self.send)
        row.addWidget(btn)
        root.addLayout(row)
        self.screen_btn = QPushButton("🖥  Bildschirm ansehen")
        self.screen_btn.clicked.connect(lambda: self.look_at_screen("Beschreibe, was auf "
                                        "meinem Bildschirm zu sehen ist, und hilf mir."))
        root.addWidget(self.screen_btn)

        self.dots = 0
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.add("Hallo! Ich bin Nova. Schreib mir etwas oder klicke auf "
                 "„Bildschirm ansehen“.", False)

        self.setWindowOpacity(0)
        self.anim = QPropertyAnimation(self, b"windowOpacity")
        self.anim.setDuration(500)
        self.anim.setStartValue(0.0)
        self.anim.setEndValue(0.97)
        self.anim.setEasingCurve(QEasingCurve.OutCubic)

    def showEvent(self, e):
        super().showEvent(e)
        self.anim.start()

    # --- Zeichnen (Glas-Optik)
    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        path = QPainterPath()
        path.addRoundedRect(self.rect().adjusted(1, 1, -1, -1), 20, 20)
        g = QLinearGradient(0, 0, self.width(), self.height())
        g.setColorAt(0, QColor(30, 27, 46, 235))
        g.setColorAt(1, QColor(12, 12, 18, 240))
        p.fillPath(path, g)
        p.setPen(QPen(QColor(139, 92, 246, 140), 1.2))
        p.drawPath(path)

    # --- Verschieben
    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._drag = e.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, e):
        if self._drag is not None and e.buttons() & Qt.LeftButton:
            self.move(e.globalPosition().toPoint() - self._drag)

    def mouseReleaseEvent(self, _):
        self._drag = None

    # --- Chat
    def add(self, text, user):
        b = Bubble(text, user)
        row = QHBoxLayout()
        if user:
            row.addStretch()
        row.addWidget(b)
        if not user:
            row.addStretch()
        w = QWidget()
        w.setLayout(row)
        self.vl.addWidget(w)
        QTimer.singleShot(50, lambda: self.scroll.verticalScrollBar().setValue(
            self.scroll.verticalScrollBar().maximum()))

    def _tick(self):
        self.dots = (self.dots + 1) % 4
        self.status.setText("Nova denkt nach" + "." * self.dots)

    def busy(self, on):
        self.edit.setEnabled(not on)
        self.screen_btn.setEnabled(not on)
        if on:
            self.timer.start(350)
        else:
            self.timer.stop()
            self.status.setText("")
            self.edit.setFocus()

    def send(self):
        text = self.edit.text().strip()
        if not text or self.worker:
            return
        self.edit.clear()
        if any(t in text.lower() for t in SOLVE_TRIGGERS):
            self.add(text, True)
            self.look_at_screen(text, echo=False)
            return
        self.add(text, True)
        self.history.append({"role": "user", "content": text})
        self.run_ai(None)

    def look_at_screen(self, prompt, echo=True):
        ans = QMessageBox.question(
            self, "Bildschirm freigeben?",
            "Nova AI moechte JETZT einen Screenshot deines Bildschirms aufnehmen und zur "
            "Analyse an Google Gemini senden.\n\nFreigeben?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if ans != QMessageBox.Yes:
            self.add("Okay, ich habe keinen Screenshot gemacht.", False)
            return
        if echo:
            self.add("🖥 Bildschirm ansehen", True)
        self.hide()
        QApplication.processEvents()
        QTimer.singleShot(350, lambda: self._grab(prompt))

    def _grab(self, prompt):
        pix = QGuiApplication.primaryScreen().grabWindow(0)
        self.show()
        if pix.width() > 1600:
            pix = pix.scaledToWidth(1600, Qt.SmoothTransformation)
        ba = QByteArray()
        buf = QBuffer(ba)
        buf.open(QIODevice.WriteOnly)
        pix.save(buf, "PNG")
        b64 = base64.b64encode(bytes(ba)).decode()
        self.history.append({"role": "user", "content": prompt})
        self.run_ai(b64)

    def run_ai(self, image_b64):
        self.busy(True)
        self.worker = AIWorker(self.api_key, self.history[-20:], image_b64)
        self.worker.done.connect(self.on_done)
        self.worker.failed.connect(self.on_fail)
        self.worker.start()

    def on_done(self, text):
        self.history.append({"role": "assistant", "content": text})
        self.add(text, False)
        self.worker = None
        self.busy(False)

    def on_fail(self, err):
        self.add("Fehler: " + err, False)
        if self.history and self.history[-1]["role"] == "user":
            self.history.pop()
        self.worker = None
        self.busy(False)


def main():
    app = QApplication(sys.argv)
    key = load_key()
    if not key:
        dlg = KeyDialog()
        if dlg.exec() != QDialog.Accepted or not dlg.edit.text().strip():
            return 0
        key = dlg.edit.text().strip()
        try:
            save_key(key)
        except Exception as e:  # noqa: BLE001
            QMessageBox.warning(None, "Nova AI", f"Schluessel konnte nicht gespeichert "
                                f"werden: {e}\nEr gilt nur fuer diese Sitzung.")
    w = Nova(key)
    w.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
