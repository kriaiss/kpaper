<div align="center">
    <pre>
    ____  __.__________  _____ _______________________________ 
    |    |/ _|\______   \/  _  \\______   \_   _____/\______   \
    |      <   |     ___/  /_\  \|     ___/|    __)_  |       _/
    |    |  \  |    |  /    |    \    |    |        \ |    |   \
    |____|__ \ |____|  \____|__  /____|   /_______  / |____|_  /
            \/                 \/                 \/         \/ 
    </pre>
</div>
<p align="center">
    Desktop wallpaper and widget host for ktools. 
</p>
<p align="center">
    <img src="https://img.shields.io/badge/python-3.12+-blue?style=flat-square" alt="Python">
    <img src="https://img.shields.io/badge/platform-macOS-lightgrey?style=flat-square" alt="Platform">
</p>

⠀

## What is kpaper?

`kpaper` is a desktop backend plugin for `ktools`. It acts as a headless frame that hooks directly into the Darwin AppKit window server via PyObjC. By intercepting macOS window levels, it places video wallpapers and widgets directly on your desktop layer, safely behind all your active workspaces.

### Core Features
* **Native AppKit Placement**: Stays permanently pinned beneath active apps. It completely ignores Mission Control, Launchpad, and workspace switchers. 
* **Multi-Monitor Support**: Translates geometries and dynamically swaps wallpapers and widgets across connected displays without crashing.
* **Power Throttling**: Intercepts `NSWorkspaceWillSleepNotification` to automatically pause video playback and unmount widgets when your system goes to sleep, preventing battery drain.

⠀

## How to Use (For Users)

1. Download the `kpaper` `.zip` archive from the Releases page.
2. Open the **ktools Plugin Manager** from your menu bar and click **import plugins** to install it.
3. The plugin automatically registers itself. Click **kpaper: select video wallpaper**.
4. Choose an `.mp4` or `.mov` file. `kpaper` will instantly loop it on the desktop.
5. Click **kpaper: change monitor** to cycle the wallpaper and all attached widgets across your multiple displays.

⠀

## The API (For Addon Developers)

`kpaper` acts as a window layer injection engine. If you want to render custom overlay components (clocks, stats, audio visualizers) directly onto the desktop layer, do not build your own window logic. Use the `kpaper` spawning pipeline.

### 1. Connecting to kpaper

Your plugin must dynamically request the `kpaper` instance from the `ktools` core engine. Do this inside your plugin's event loop or UI generation phase, **not** in `__init__`, because `kpaper` might load after your plugin.

```python
kp = self.ktools.plugins.get('kpaper')
if kp and hasattr(kp, 'spawn_widget'):
    # kpaper is installed and ready
```

### 2. Spawning a Widget

To inject a custom PyQt6 widget onto the desktop, pass a constructor or lambda to `kp.spawn_widget()`. 

* `interactive=False`: The widget is pushed to the absolute bottom layer (`kCGDesktopWindowLevel - 1`). It ignores all mouse clicks and hovers. Perfect for clocks.
* `interactive=True`: The widget is placed slightly higher (`kCGDesktopWindowLevel + 1`). It can receive mouse clicks (e.g., a desktop music player).

```python
# Pass a lambda that returns your initialized QWidget
self.widget = kp.spawn_widget(lambda kt: MyCustomWidget(kt, self.config), interactive=False)
```

`kpaper` will automatically:
- Strip the Qt window frame.
- Inject the necessary `NSWindowCollectionBehaviorCanJoinAllSpaces` flags so it survives space switching.
- Make the background translucent.
- Track its lifecycle internally.

### 3. Positioning on the Correct Monitor

`kpaper` manages multi-monitor translations. If the user clicks "change monitor", `kpaper` will automatically move your widget, but you need to know where to place it initially. 

Use `kp.get_target_screen_geometry()` to get the `QRect` of the display `kpaper` is currently rendering on.

```python
if self.widget:
    screen = kp.get_target_screen_geometry()
    
    # Center the widget on the active monitor
    x = screen.x() + (screen.width() - self.widget.width()) // 2
    y = screen.y() + (screen.height() - self.widget.height()) // 2
    
    self.widget.move(x, y)
    self.widget.show()
```

### 4. Cleanup and Unloading

You **must** destroy your own widget when your plugin is unloaded, otherwise you will leave zombie C++ objects in memory. `kpaper` dynamically detects deleted widgets and safely drops them from its render loop by intercepting `RuntimeError`, so you don't need to notify `kpaper`—just delete your object.

```python
def unload(self):
    if self.widget:
        self.widget.close()
        self.widget.deleteLater()
        self.widget = None
```

by kriaiss.
