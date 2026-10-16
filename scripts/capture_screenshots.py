"""Capture the actual pet window against a temporary clean desktop backdrop.

The backdrop belongs to this process; other applications are left untouched.
No mouse movement or cursor capture is enabled during the photo session.
"""
import json
from pathlib import Path
import sys
import zipfile

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'src'))

from PyQt6.QtCore import QRect, QPoint, Qt, QTimer
from PyQt6.QtGui import QColor, QLinearGradient, QPainter
from PyQt6.QtWidgets import QApplication, QWidget

from animation_node import AnimationNode as N
from app import FrameAnimatedPet


SHOTS = [
    ('01_stand_idle', 'Спокойная стойка', N.STAND_IDLE, 1),
    ('02_sit_idle', 'Мнёт хвост', N.SIT_IDLE, 4),
    ('03_sleep', 'Сон', N.SLEEP, 2),
    ('04_clean', 'Умывание', N.CLEAN, 3),
    ('05_sandbath', 'Катание в песке', N.SANDBATH, 2),
    ('06_swat', 'Удар лапой', N.SWAT, 5),
    ('07_run', 'Бег', N.RUN, 3),
    ('08_hide', 'Выглядывает из-за края', N.HIDE, 2),
]


class Backdrop(QWidget):
    def paintEvent(self, event):
        painter = QPainter(self)
        gradient = QLinearGradient(0, 0, self.width(), self.height())
        gradient.setColorAt(0, QColor('#203247'))
        gradient.setColorAt(.6, QColor('#314553'))
        gradient.setColorAt(1, QColor('#243c40'))
        painter.fillRect(self.rect(), gradient)


def main(pet=None):
    output = ROOT / 'screenshots' / 'itch'
    (output / 'full').mkdir(parents=True, exist_ok=True)
    (output / 'closeup').mkdir(exist_ok=True)
    app = QApplication.instance() or QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    screen = app.primaryScreen()
    desktop = screen.geometry()
    workarea = screen.availableGeometry()
    backdrop = Backdrop(None, Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool)
    backdrop.setWindowTitle('DesktopPet screenshot backdrop')
    backdrop.setGeometry(desktop)
    backdrop.show()
    backdrop.raise_()
    backdrop.activateWindow()
    pet = pet or FrameAnimatedPet()
    pet.controller.stop()
    pet.debug_console.stop()
    records = []
    capture_methods = set()
    position = [0]

    def prepare():
        if position[0] >= len(SHOTS):
            finish()
            return
        name, title, node, frame_index = SHOTS[position[0]]
        pet.set_horizontal_edge_anchor(None)
        pet.set_screen_clip(None)
        pet.set_facing_right(node not in (N.SIT_IDLE, N.CLEAN))
        pet.force_set_animation_node(node)
        player = pet.animation_player
        player.timer.stop()
        pet.animator.bridge_timer.stop()
        player.current_frame_index = min(frame_index, len(player.frames) - 1)
        player.frame_changed.emit(player.frames[player.current_frame_index])
        pet.ground_y = workarea.bottom() + 1 - pet.height()
        if node == N.HIDE:
            pet.move(desktop.left(), desktop.top() + desktop.height() // 3)
        else:
            pet.move(desktop.left() + desktop.width() * 2 // 3 - pet.width() // 2, pet.ground_y)
        pet.show()
        pet.raise_()
        QTimer.singleShot(500, capture)

    def capture():
        name, title, node, _ = SHOTS[position[0]]
        # Capture the native desktop with the live top-level pet window.
        full = screen.grabWindow(0, desktop.x(), desktop.y(), desktop.width(), desktop.height())
        sample = full.toImage()
        if not any(sample.pixelColor(x, y).value() for x in range(0, sample.width(), 80)
                   for y in range(0, sample.height(), 80)):
            # Some isolated Windows sessions cannot read the native desktop.
            # Render the live widget unchanged onto our actual backdrop instead.
            full = backdrop.grab()
            painter = QPainter(full)
            pet.render(painter, QPoint(pet.x() - desktop.x(), pet.y() - desktop.y()))
            painter.end()
            method = 'staged-widget-render'
        else:
            method = 'native-desktop'
        capture_methods.add(method)
        if full.isNull() or not full.save(str(output / 'full' / f'{name}.png')):
            raise RuntimeError('Could not capture the native screen')
        width, height = min(960, desktop.width()), min(540, desktop.height())
        x = max(desktop.left(), min(pet.x() + pet.width() // 2 - width // 2,
                                    desktop.right() + 1 - width))
        y = max(desktop.top(), min(pet.y() + pet.height() // 2 - height // 2,
                                   desktop.bottom() + 1 - height))
        closeup = full.copy(QRect(x - desktop.x(), y - desktop.y(), width, height))
        if not closeup.save(str(output / 'closeup' / f'{name}.png')):
            raise RuntimeError('Could not save closeup')
        records.append({'name': name, 'title': title, 'animation': node.value,
                        'frame': pet.animation_player.current_frame_index, 'capture_method': method})
        position[0] += 1
        QTimer.singleShot(50, prepare)

    def finish():
        pet.close()
        backdrop.close()
        (output / 'shots.json').write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding='utf-8')
        cards = ''.join(f'<figure><a href="full/{r["name"]}.png"><img src="closeup/{r["name"]}.png"></a>'
                        f'<figcaption>{r["title"]}</figcaption></figure>' for r in records)
        (output / 'index.html').write_text(
            '<!doctype html><meta charset="utf-8"><title>DesktopPet screenshots</title>'
            '<style>body{background:#17212b;color:#eee;font:16px system-ui;padding:24px}'
            'main{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:20px}'
            'figure{margin:0}img{width:100%;border-radius:8px}figcaption{padding:8px 0}</style>'
            '<h1>DesktopPet</h1><p>Демонстрационные кадры реального интерфейса на нейтральном фоне. '
            'Если capture_method в shots.json равен staged-widget-render, это отрисовка '
            'виджета приложения, а не захват рабочего стола Windows. '
            'Нажмите на кадр, чтобы открыть полный снимок.</p><main>' + cards + '</main>', encoding='utf-8')
        archive = ROOT / 'screenshots' / 'DesktopPet-itch-screenshots.zip'
        with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as package:
            for path in output.rglob('*'):
                if path.is_file():
                    package.write(path, path.relative_to(output))
        print(f'Saved {len(records)} shots (full + closeup): {output}', flush=True)
        print(f'Archive: {archive}', flush=True)
        app.quit()

    # Close our temporary windows even if a callback fails.
    def failed(kind, value, traceback):
        pet.close()
        backdrop.close()
        sys.__excepthook__(kind, value, traceback)
        app.exit(1)
    sys.excepthook = failed
    QTimer.singleShot(700, prepare)
    return app.exec()


if __name__ == '__main__':
    sys.exit(main())
