import sys
import os
from PySide6.QtWidgets import QApplication, QMessageBox
from PySide6.QtCore import QLockFile, QDir
from ui.main_window import MainWindow

def main():
    app = QApplication(sys.argv)
    # 解决托盘后台保活的核心：防止最后一个窗口关闭/隐藏时 QApplication 自动退出
    app.setQuitOnLastWindowClosed(False)

    # 强制单例锁，防止多开导致本地 Web 托管服务器端口冲突或剪贴板重复监控
    lock_file = QLockFile(os.path.join(QDir.tempPath(), "ai_preview_studio.lock"))
    if not lock_file.tryLock(100):
        QMessageBox.warning(None, "运行提示", "AI Preview Studio 已经在后台运行中！\n请检查右下角系统托盘。")
        sys.exit(0)

    # 声明锁文件的强引用防止被垃圾回收
    app.lock_file = lock_file

    window = MainWindow()
    window.show()

    sys.exit(app.exec())

if __name__ == "__main__":
    main()