import objc
import os
import json
import subprocess
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QFileDialog, QApplication
from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput
from PyQt6.QtMultimediaWidgets import QVideoWidget
from PyQt6.QtCore import Qt, QUrl, QTimer
from PyQt6.QtGui import QAction
from AppKit import (NSApp, NSWindowCollectionBehaviorCanJoinAllSpaces, 
                    NSWindowCollectionBehaviorStationary, NSWindowCollectionBehaviorIgnoresCycle, NSView, NSWindow, NSWorkspace, NSWorkspaceDidWakeNotification)
from Foundation import NSNotificationCenter

kCGDesktopWindowLevel = -2147483623 

class WallpaperWindow(QWidget):
    def __init__(self, ktools):
        super().__init__()
        self.ktools = ktools
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint | 
            Qt.WindowType.Tool |
            Qt.WindowType.WindowDoesNotAcceptFocus
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        
        screen = QApplication.primaryScreen().geometry()
        self.setGeometry(screen)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        self.video_widget = QVideoWidget()
        layout.addWidget(self.video_widget)
        
        self.player = QMediaPlayer()
        self.player.setAudioOutput(None)
        self.player.setVideoOutput(self.video_widget)
        self.player.setLoops(QMediaPlayer.Loops.Infinite)

    def showEvent(self, event):
        QTimer.singleShot(200, self._apply_native_flags)
        super().showEvent(event)

    def _apply_native_flags(self):
        try:
            for window in NSApp.windows():
                if window.isVisible() and window.frame().size.width == self.width():
                    window.setLevel_(kCGDesktopWindowLevel)
                    window.setHidesOnDeactivate_(False)
                    window.setCanHide_(False)
                    behavior = (NSWindowCollectionBehaviorCanJoinAllSpaces | 
                                NSWindowCollectionBehaviorStationary | 
                                NSWindowCollectionBehaviorIgnoresCycle)
                    window.setCollectionBehavior_(behavior)
                    break
        except Exception as e:
            print(f"kpaper: failed to apply native flags: {e} {e}")

class Plugin:
    def __init__(self, ktools):
        self.layer = "fixed"
        self.ktools = ktools
        self.name = "kpaper"
        self.workspace_center = NSWorkspace.sharedWorkspace().notificationCenter()
        self.workspace_center.addObserver_selector_name_object_(
            self, "handleSleep:", "NSWorkspaceWillSleepNotification", None
        )
        self.workspace_center.addObserver_selector_name_object_(
            self, "handleSleep:", "com.apple.screenIsLocked", None
        )
        self.workspace_center.addObserver_selector_name_object_(
            self, "handleWake:", "NSWorkspaceDidWakeNotification", None
        )
        self.workspace_center.addObserver_selector_name_object_(
            self, "handleWake:", "com.apple.screenIsUnlocked", None
        )
        self.plugin_dir = os.path.dirname(os.path.abspath(__file__))
        self.conf_path = os.path.join(self.plugin_dir, "kpaper.json")
        self.widgets = []
        self.shell = None
        self.load_config_and_run() 

    def load_config_only(self):
        if os.path.exists(self.conf_path):
            with open(self.conf_path, "r", encoding='utf-8') as f:
                return json.load(f)
        return {}

    def ensure_shell(self):
        if not self.shell:
            self.shell = WallpaperWindow(self.ktools)
        return self.shell

    def spawn_widget(self, widget_class, interactive=True):
        try:
            widget = widget_class(self.ktools)
            widget._is_interactive = interactive 
            
            flags = Qt.WindowType.FramelessWindowHint
            if not interactive:
                flags |= Qt.WindowType.WindowDoesNotAcceptFocus
                widget.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
            
            widget.setWindowFlags(flags)
            widget.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
            widget.show()
            
            QTimer.singleShot(300, lambda: self._apply_widget_native_flags(widget))
            
            self.widgets.append(widget)
            return widget
        except Exception as e:
            print(f"kpaper error spawning: {e}")
            return None

    def _apply_widget_native_flags(self, widget):
        try:
            view_ptr = int(widget.winId())
            ns_view = objc.objc_object(c_void_p=view_ptr)
            window = ns_view.window()

            if window:
                is_interactive = getattr(widget, '_is_interactive', True)
                
                if is_interactive:
                    window.setLevel_(-2147483601) 
                    window.setIgnoresMouseEvents_(False)
                    window.setAcceptsMouseMovedEvents_(True)
                else:
                    window.setLevel_(-2147483622)
                    window.setIgnoresMouseEvents_(True)
                    window.setAcceptsMouseMovedEvents_(True)

                behavior = (NSWindowCollectionBehaviorCanJoinAllSpaces | 
                            NSWindowCollectionBehaviorStationary | 
                            NSWindowCollectionBehaviorIgnoresCycle)
                window.setCollectionBehavior_(behavior)

                window.setHasShadow_(False)
                window.setHidesOnDeactivate_(False)
                window.setCanHide_(False)

                if is_interactive:
                    window.setCollectionBehavior_(behavior | 128)
                    
        except Exception as e:
            print(f"kpaper native error: {e}")

    def toggle_wallpaper(self):
        config = {}
        if os.path.exists(self.conf_path):
            with open(self.conf_path, "r", encoding='utf-8') as f:
                config = json.load(f)

        is_enabled = config.get("enabled", True)
        new_state = not is_enabled
        
        if new_state:
            last_wall = config.get('last_wallpaper')
            if last_wall and os.path.exists(last_wall):
                self.ensure_shell()
                self.shell.player.setSource(QUrl.fromLocalFile(last_wall))
                self.shell.show()
                self.shell.player.play()
                self.ktools.notify("live wallpaper: ON")
            else:
                self.ktools.notify("no video selected")
                return
        else:
            self.ensure_shell()
            self.shell.player.stop()
            self.shell.hide()
            self.ktools.notify("live wallpaper: OFF")

        config["enabled"] = new_state
        with open(self.conf_path, "w", encoding='utf-8') as f:
            json.dump(config, f, ensure_ascii=False, indent=4)

    def unload_wallpaper(self):
        if self.shell:
            print("kpaper: destructing player resources")
            self.shell.player.stop()
            self.shell.hide()
            self.shell.deleteLater()
            self.shell = None
            import gc
            gc.collect()

    @objc.python_method
    def handleSleep_(self, notification):
        print(f"kpaper: system lock/sleep detected via {notification.name()}")
        self.unload_wallpaper()

    @objc.python_method
    def handleWake_(self, notification):
        print(f"kpaper: system wake/unlock detected via {notification.name()}")
        QTimer.singleShot(2000, self.load_config_and_run)

    def load_config_and_run(self):
        config = self.load_config_only()
        if not config.get("enabled", True): return
        
        last_wall = config.get('last_wallpaper')
        if last_wall and os.path.exists(last_wall):
            shell = self.ensure_shell()
            shell.player.setSource(QUrl.fromLocalFile(last_wall))
            shell.show()
            shell.player.play()

    def select_video_wallpaper(self):
        file_path, _ = QFileDialog.getOpenFileName(None, "Select Video", "", "Videos (*.mp4 *.mov)")
        if file_path:
            try:
                with open(self.conf_path, "w", encoding='utf-8') as f:
                    json.dump({"last_wallpaper": file_path}, f, ensure_ascii=False, indent=4)
                self.ktools.notify("applying wallpaper...")
                QTimer.singleShot(100, lambda: self.apply_wallpaper(file_path))
            except: 
                self.ktools.notify("error saving config")
                pass

    def apply_wallpaper(self, path):
        import time
        self.ensure_shell()
        self.shell.player.setSource(QUrl.fromLocalFile(path))
        self.shell.show()
        self.shell.player.play()
        ffmpeg_bin = None
        for p in ["/opt/homebrew/bin/ffmpeg", "/usr/local/bin/ffmpeg", "/usr/bin/ffmpeg"]:
            if os.path.exists(p) and os.access(p, os.X_OK):
                ffmpeg_bin = p
                break
        if ffmpeg_bin:
            thumb_path = os.path.expanduser("~/.kpaper_static.jpg")
            try:
                subprocess.run([ffmpeg_bin, '-y', '-i', path, '-ss', '0', '-vframes', '1', '-q:v', '2', thumb_path], check=True, capture_output=True)
                time.sleep(0.3)
                from AppKit import NSWorkspace, NSURL, NSScreen
                from Foundation import NSDictionary
                workspace = NSWorkspace.sharedWorkspace()
                file_url = NSURL.fileURLWithPath_(thumb_path)
                options = NSDictionary.dictionary()
                for screen in NSScreen.screens():
                    workspace.setDesktopImageURL_forScreen_options_error_(file_url, screen, options, None)
                script = f'tell application "System Events" to set picture of every desktop to "{thumb_path}"'
                subprocess.run(['osascript', '-e', script], check=False)
                subprocess.run(['killall', 'Dock'], check=False)
                self.ktools.notify("wallpaper synced (restart system if not)")
            except:
                self.ktools.notify("failed to sync static frame")
                pass
        else:
            self.ktools.notify("ffmpeg not found, sync skipped")

    def unload(self):
        try:
            self.workspace_center.removeObserver_(self)
        except: pass

        if hasattr(self.shell, 'player'):
            self.shell.player.stop()
            self.shell.player.setVideoOutput(None)
            self.shell.player.deleteLater()

        for w in self.widgets:
            try:
                w.hide()
                w.setParent(None) 
                w.close()
                w.deleteLater()
            except: pass
        self.widgets.clear()

        if self.shell:
            self.shell.hide()
            self.shell.close()
            self.shell.deleteLater()

        import gc
        gc.collect()
        try:
            self.action.triggered.disconnect()
            self.ktools.menu.removeAction(self.action)
        except: pass
        print("kpaper: unloaded and video resources freed")

    def update_theme(self): pass
    def get_actions(self): return []