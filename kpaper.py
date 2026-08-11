import objc
import os
import json
import subprocess
import gc
from AppKit import NSWorkspace, NSWindowCollectionBehaviorCanJoinAllSpaces, NSWindowCollectionBehaviorStationary, NSWindowCollectionBehaviorIgnoresCycle
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QFileDialog, QApplication
from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput
from PyQt6.QtMultimediaWidgets import QVideoWidget
from PyQt6.QtCore import Qt, QUrl, QTimer
from PyQt6.QtGui import QAction
from main import WallpaperWindow

class KPaperWindow(WallpaperWindow):
    def __init__(self, ktools):
        super().__init__(ktools)
        
        kp = self.ktools.plugins.get("kpaper")
        screen = kp.get_target_screen_geometry() if kp and hasattr(kp, 'get_target_screen_geometry') else QApplication.primaryScreen().geometry()
        self.setGeometry(screen)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.video_widget = QVideoWidget(self)
        layout.addWidget(self.video_widget)
        
        self.player = QMediaPlayer(self)
        self.audio_output = QAudioOutput(self)
        self.audio_output.setVolume(0.0)
        self.player.setAudioOutput(self.audio_output)
        self.player.setVideoOutput(self.video_widget)
        self.player.mediaStatusChanged.connect(self._loop_video)

    def _loop_video(self, status):
        if status == QMediaPlayer.MediaStatus.EndOfMedia:
            self.player.setPosition(0)
            self.player.play()



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
        self.config_path = os.path.join(self.plugin_dir, "kpaper.json")
        self.config = {}
        self.widgets = []
        self.shell = None
        
        self._load_config()
        self.load_config_and_run() 

    def get_actions(self): 
        return []

    def update_theme(self): 
        pass

    def unload(self):
        try:
            self.workspace_center.removeObserver_(self)
        except Exception: 
            pass

        self.unload_wallpaper()

        for w in self.widgets:
            try:
                w.hide()
                w.setParent(None) 
                w.close()
                w.deleteLater()
            except Exception: 
                pass
        self.widgets.clear()

        gc.collect()

        if hasattr(self, 'action'):
            try:
                self.action.triggered.disconnect()
                self.ktools.menu.removeAction(self.action)
            except Exception: 
                pass
                
        print("kpaper: unloaded and video resources freed")

    def _load_config(self):
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, "r", encoding='utf-8') as f:
                    self.config = json.load(f)
            except Exception:
                self.config = {"enabled": True}
        else:
            self.config = {"enabled": True}
            self._save_config()

    def _save_config(self):
        try:
            with open(self.config_path, "w", encoding='utf-8') as f:
                json.dump(self.config, f, ensure_ascii=False, indent=4)
        except Exception as e:
            print(f"kpaper: failed to save config {e}")

    def ensure_shell(self):
        if not self.shell:
            self.shell = KPaperWindow(self.ktools)
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
            
            QTimer.singleShot(100, lambda: self._apply_widget_native_flags(widget))
            
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

                # wallpaper vanishes when switching spaces without these flags. makes sense tbh
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
        is_enabled = self.config.get("enabled", True)
        new_state = not is_enabled
        
        if new_state:
            last_wall = self.config.get('last_wallpaper')
            if last_wall and os.path.exists(last_wall):
                shell = self.ensure_shell()
                new_src = QUrl.fromLocalFile(last_wall)
                if shell.player.source() != new_src:
                    shell.player.setSource(new_src)
                shell.show()
                shell.player.play()
                self.ktools.notify("live wallpaper: ON")
            else:
                self.ktools.notify("no video selected")
                return
        else:
            self.unload_wallpaper()
            self.ktools.notify("live wallpaper: OFF")

        self.config["enabled"] = new_state
        self._save_config()

    def unload_wallpaper(self):
        if self.shell:
            print("kpaper: destructing player resources")
            self.shell.player.stop()
            self.shell.player.setVideoOutput(None) 
            self.shell.hide()
            self.shell.deleteLater()
            self.shell = None
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
        if not self.config.get("enabled", True): return
        
        last_wall = self.config.get('last_wallpaper')
        if last_wall and os.path.exists(last_wall):
            shell = self.ensure_shell()
            new_src = QUrl.fromLocalFile(last_wall)
            if shell.player.source() != new_src:
                shell.player.setSource(new_src)
            shell.setGeometry(self.get_target_screen_geometry())
            shell.show()
            shell.player.play()

    def get_target_screen_geometry(self):
        screens = QApplication.screens()
        idx = self.config.get("monitor_index", 0)
        if idx < len(screens):
            return screens[idx].geometry()
        return QApplication.primaryScreen().geometry()

    def change_monitor(self):
        screens = QApplication.screens()
        if not screens: return
        
        current_idx = self.config.get("monitor_index", 0)
        next_idx = (current_idx + 1) % len(screens)
        self.config["monitor_index"] = next_idx
        self._save_config()
        
        screen_name = screens[next_idx].name()
        self.ktools.notify(f"monitor changed: {screen_name}")
        
        target_geom = self.get_target_screen_geometry()
        
        if self.shell:
            self.shell.setGeometry(target_geom)
            
        alive_widgets = []
        for w in self.widgets:
            try:
                w.move(target_geom.x() + (target_geom.width() - w.width()) // 2, 
                       target_geom.y() + (target_geom.height() - w.height()) // 2)
                alive_widgets.append(w)
            except RuntimeError:
                pass
        self.widgets = alive_widgets

    def select_video_wallpaper(self):
        file_path, _ = QFileDialog.getOpenFileName(None, "Select Video", "", "Videos (*.mp4 *.mov)")
        if file_path:
            try:
                self.config["last_wallpaper"] = file_path
                self._save_config()
                
                self.ktools.notify("applying wallpaper...")
                QTimer.singleShot(100, lambda: self.apply_wallpaper(file_path))
            except Exception as e: 
                self.ktools.notify("error saving config")
                print(f"kpaper config error: {e}")

    def apply_wallpaper(self, path):
        import time
        shell = self.ensure_shell()
        new_src = QUrl.fromLocalFile(path)
        if shell.player.source() != new_src:
            shell.player.setSource(new_src)
        shell.show()
        shell.player.play()
        
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
                subprocess.run(['osascript', '-e', script], check=False, capture_output=True)
                subprocess.run(['killall', 'Dock'], check=False, capture_output=True)
                
                self.ktools.notify("wallpaper synced")
            except Exception as e:
                self.ktools.notify("failed to sync static frame")
                print(f"kpaper ffmpeg sync error: {e}")
        else:
            self.ktools.notify("ffmpeg not found, sync skipped")
