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
    native cocoa-level live wallpaper engine and widget injector for ktools. low-level desktop manipulation without the 1gb ram overhead.
</p>
<p align="center">
    <img src="https://img.shields.io/badge/python-3.12+-blue?style=flat-square" alt="Python">
    <img src="https://img.shields.io/badge/platform-macOS-lightgrey?style=flat-square" alt="Platform">
</p>

⠀

# what is this?

kpaper is a high-performance desktop backend plugin built to purge bloated standalone wallpaper apps and heavy web-view desktop wrappers from your system. instead of spawning an independent app that hogs your system memory just to loop a video, it initializes a headless frame, translates screen geometries, and hooks directly into the core darwin appkit window server via python-objc bridges.

it doesn't just fake a borderless background window. it forces the layout into the native -2147483623 desktop window level (kCGDesktopWindowLevel), positioning your live wallpaper exactly behind your active workspaces while acting as a core mounting matrix for external add-on widgets.

### features

* native appkit placement: injects directly into the macOS window subsystem. stays perfectly pinned beneath all active apps, completely ignoring mission control, launchpad, and workspace switchers.
* zero-daemon footprint: runs entirely inside the ktools lifecycle thread. no heavy background helper processes or battery-draining telemetry left behind in the system tree.
* ffmpeg static sync: automatically extracts the initial video frame using a local ffmpeg pipeline, syncing it to the native cocoa desktop image URL to prevent black flashes, rendering gaps, or wallpaper resets on display wake.
* smart power throttling: completely drops video engine registers and halts hardware acceleration player threads upon system sleep or screen lock, guaranteeing zero battery impact when you are away.

⠀

# how to use

* trigger the video path selection dialog from your ktools configuration setup.
* feed it any standard .mp4 or .mov asset. kpaper will automatically execute a fast background shell to spin up the sync frames and dock configurations.
* toggle the live state via your ktools action lists to seamlessly mount or completely destroy the active video stream layout on the fly.

⠀

# the code breakdown (most interest part :>)

## kpaper widget engine (kp.spawn_widget(widget_class, interactive=True))

kpaper isn't just a live wallpaper loops runner. it acts as a low-level window layer injection engine for macos. if u want to render custom overlay components (clocks, stats, visualizers) directly onto the desktop layer without spawning high-overhead standalone apps, use the kpaper spawning pipeline.

### about

* window architecture: widgets are decoupled from the core loop and wrapped into raw appkit window wrappers under the hood.
* native behavior: both interactive and passive layouts automatically strip system window shadows (setHasShadow_(False)) and lock themselves across all virtual workspaces using CanJoinAllSpaces | Stationary | IgnoresCycle behaviors.
* memory management: instances are stored in the engine's internal tracking array. when kpaper unloads, it automatically triggers .close() and .deleteLater() loops across all spawned components to prevent orphan carbon windows.

### usage

u don't instantiate windows manually via standard qt hooks. instead, grab the kpaper handle from the core plugins map and feed it ur widget class:

```python
"""query the engine and spawn a background frame"""
kp = self.ktools.plugins.get('kpaper')
if kp and hasattr(kp, 'spawn_widget'):
    self.widget = kp.spawn_widget(lambda kt: MyClockWidget(kt), interactive=False)
```

⠀

## interactive vs passive layers (window levels)

managing input routing on macos desktop layouts requires strict control over darwin window hierarchies. the interactive flag changes how appkit intercepts inputs.

### about
 
* interactive (true): injects window level -2147483601. the frame catches mouse clicks, tracks cursor hover ticks, and gets structural behavior 128 appended so it stays responsive above the wallpaper layer. use this for custom desktop docks, interactive terminals, or control decks.
* passive (false): injects window level -2147483622. forces setIgnoresMouseEvents_(True) and drops window activation focus hooks. clicks drop straight through the layout onto the desktop file manager or wallpaper. use this for clocks, status bars, and ambient graphs that must never steal focus.

### usage 

```python
"""interactive overlay entry point"""
self.widget = kp.spawn_widget(TerminalWidget, interactive=True)

"""non-interactive background panel"""
self.widget = kp.spawn_widget(HardwareMonitorWidget, interactive=False)
```

⠀

# good manners (best practices)

follow these rules or ur widget will lag the system compositor and leak memory registers.

### 1. async data workers (the thread rule)

blocking cli bindings or slow network pipes will freeze the core ktools ui loop if executed inside the main thread. offload all tracking loops.

### about

* the restriction: calling external tools like nowplaying-cli or scraping endpoints like curl wttr.in directly inside your drawing functions will stall the qt compositor frame rate.
* the fix: isolate telemetry routines inside a dedicated QThread pipeline. push string chunks back to your interface labels strictly via pyqtSignal events.
* cleanup duty: workers must be stoppable. implement an internal state flag (self._alive) so threads finish execution loops cleanly when the engine requests a shutdown.

### usage

```python
class TelemetryThread(QThread):
    data_ready = pyqtSignal(str)
    def __init__(self):
        super().__init__()
        self._alive = True

    def run(self):
        try:
            res = subprocess.check_output("nowplaying-cli get title", shell=True).decode("utf-8").strip()
            if self._alive and res:
                self.data_ready.emit(res)
        except:
            if self._alive: self.data_ready.emit("N/A")

    def stop(self):
        self._alive = False
        self.wait()
```

⠀

### 2. macos power management (app nap control)

darwin is ruthless with background loops and window server allocations. you must explicitly adapt to macos power states.

### about

* sleep trapping: listen to NSWorkspaceWillSleepNotification and com.apple.screenIsLocked. the millisecond they trigger, instantly drop widget pointers and execute close() to let macos suspend operations cleanly without corrupting window frames.
* wake buffer: trap NSWorkspaceDidWakeNotification to restore your layout space. always chain the initialization sequence within a QTimer.singleShot delay loop (2-3 seconds) to let the core window server rebuild graphics layers before mounting layouts.
* app nap bypass: prevent the system from throttling your worker threads into low-performance efficiency cores. initialize an NSProcessInfo tracking activity using power options (1 << 10) | (1 << 40) to lock active runtime execution privileges.

### usage

```python
"""prevent app nap throttling on setup"""
self.activity = NSProcessInfo.processInfo().beginActivityWithOptions_reason_(
    (1 << 10) | (1 << 40), "keep background worker alive"
)

"""sleep handler"""
def handleSleep_(self, notification):
    if self.widget:
        self.widget.close()
        self.widget = None
```

⠀

### 3. state verification & layout safety

avoid graphics pipeline desync loops when dealing with persistent configurations and layer mutations.

### about

* config separation: never do heavy file system IO loops when drawing layouts. read configs once on boot or track states using an isolated cache path (self.config_path).
* layout regeneration: if a user mutates layout sizes or toggles sub-components on the fly, don't attempt complex element geometry shifting. clear out layout item counts dynamically, destroy internal widget parents safely, and rebuild the interface map from scratch.
* existence check: before accessing external plugin interfaces via self.ktools.plugins.get(), always validate method availability (hasattr(kp, 'spawn_widget')) to prevent full engine crashes if a dependency gets unloaded mid-session.

### usage

```python
def refresh_layout(self):
    """clear old objects from tree safely"""
    for i in reversed(range(self.layout.count())): 
        self.layout.itemAt(i).widget().setParent(None)
    
    """re-instantiate elements using updated state matrices"""
    self.label = QLabel()
    self.layout.addWidget(self.label)
```

⠀

### 4. read the ktools api before building ur widget. otherwise, u'll just write absolute garbage that lags the system.

⠀

### final thoughts

i might have missed something. even though this is a full-blown api, i’m still just a human... (yes i just copied this from ktools readme, coz why not lol)

thanks for reading this btw.

by kriaiss.