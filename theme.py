"""
theme.py - Theme support.

Copyright (c) EDCD, All Rights Reserved
Licensed under the GNU General Public License.
See LICENSE file.

Believe us, this used to be much worse before ttk's theme support was properly leveraged.
"""
from __future__ import annotations

import os
import prefs
import sys
import tkinter as tk
import warnings
from tkinter import ttk
from ttkHyperlinkLabel import HyperlinkLabel
from typing import Callable
from config import appname, config
from EDMCLogging import get_main_logger

logger = get_main_logger()

if __debug__:
    from traceback import print_exc

if sys.platform == 'win32':
    import win32con
    import win32gui
    from winrt.microsoft.ui.interop import get_window_id_from_window
    from winrt.microsoft.ui.windowing import AppWindow
    from winrt.windows.ui import Color, Colors, ColorHelper
    from ctypes import windll
    FR_PRIVATE = 0x10
    fonts_loaded = windll.gdi32.AddFontResourceExW(str(config.respath_path / 'EUROCAPS.TTF'), FR_PRIVATE, 0)
    if fonts_loaded < 1:
        logger.error('Unable to load Euro Caps font for Transparent theme')

elif sys.platform == 'linux':
    from ctypes import POINTER, Structure, byref, c_char_p, c_int, c_long, c_uint, c_ulong, c_void_p, cdll
    XID = c_ulong 	# from X.h: typedef unsigned long XID
    Window = XID
    Atom = c_ulong
    Display = c_void_p  # Opaque

    PropModeReplace = 0
    PropModePrepend = 1
    PropModeAppend = 2

    # From xprops.h
    MWM_HINTS_FUNCTIONS = 1 << 0
    MWM_HINTS_DECORATIONS = 1 << 1
    MWM_HINTS_INPUT_MODE = 1 << 2
    MWM_HINTS_STATUS = 1 << 3
    MWM_FUNC_ALL = 1 << 0
    MWM_FUNC_RESIZE = 1 << 1
    MWM_FUNC_MOVE = 1 << 2
    MWM_FUNC_MINIMIZE = 1 << 3
    MWM_FUNC_MAXIMIZE = 1 << 4
    MWM_FUNC_CLOSE = 1 << 5
    MWM_DECOR_ALL = 1 << 0
    MWM_DECOR_BORDER = 1 << 1
    MWM_DECOR_RESIZEH = 1 << 2
    MWM_DECOR_TITLE = 1 << 3
    MWM_DECOR_MENU = 1 << 4
    MWM_DECOR_MINIMIZE = 1 << 5
    MWM_DECOR_MAXIMIZE = 1 << 6

    class MotifWmHints(Structure):
        """MotifWmHints structure."""

        _fields_ = [
            ('flags', c_ulong),
            ('functions', c_ulong),
            ('decorations', c_ulong),
            ('input_mode', c_long),
            ('status', c_ulong),
        ]

    # workaround for https://github.com/EDCD/EDMarketConnector/issues/568
    if not os.getenv("EDMC_NO_UI"):
        try:
            xlib = cdll.LoadLibrary('libX11.so.6')
            XInternAtom = xlib.XInternAtom
            XInternAtom.argtypes = [POINTER(Display), c_char_p, c_int]
            XInternAtom.restype = Atom
            XChangeProperty = xlib.XChangeProperty
            XChangeProperty.argtypes = [POINTER(Display), Window, Atom, Atom, c_int,
                                        c_int, POINTER(MotifWmHints), c_int]
            XChangeProperty.restype = c_int
            XFlush = xlib.XFlush
            XFlush.argtypes = [POINTER(Display)]
            XFlush.restype = c_int
            XOpenDisplay = xlib.XOpenDisplay
            XOpenDisplay.argtypes = [c_char_p]
            XOpenDisplay.restype = POINTER(Display)
            XQueryTree = xlib.XQueryTree
            XQueryTree.argtypes = [POINTER(Display), Window, POINTER(
                Window), POINTER(Window), POINTER(Window), POINTER(c_uint)]
            XQueryTree.restype = c_int
            dpy = xlib.XOpenDisplay(None)
            if not dpy:
                raise Exception("Can't find your display, can't continue")

            motif_wm_hints_property = XInternAtom(dpy, b'_MOTIF_WM_HINTS', False)
            motif_wm_hints_normal = MotifWmHints(
                MWM_HINTS_FUNCTIONS | MWM_HINTS_DECORATIONS,
                MWM_FUNC_RESIZE | MWM_FUNC_MOVE | MWM_FUNC_MINIMIZE | MWM_FUNC_CLOSE,
                MWM_DECOR_BORDER | MWM_DECOR_RESIZEH | MWM_DECOR_TITLE | MWM_DECOR_MENU | MWM_DECOR_MINIMIZE,
                0, 0
            )
            motif_wm_hints_dark = MotifWmHints(MWM_HINTS_FUNCTIONS | MWM_HINTS_DECORATIONS,
                                               MWM_FUNC_RESIZE | MWM_FUNC_MOVE | MWM_FUNC_MINIMIZE | MWM_FUNC_CLOSE,
                                               0, 0, 0)
        except Exception:
            if __debug__:
                print_exc()

            dpy = None


class _Theme:
    # TODO ditch indexes, support additional themes in user folder
    THEME_DEFAULT = 0
    THEME_DARK = 1
    THEME_TRANSPARENT = 2
    packages = {
        THEME_DEFAULT: 'light',  # 'default' is the name of a builtin theme
        THEME_DARK: 'dark',
        THEME_TRANSPARENT: 'transparent',
    }
    style: ttk.Style
    root: tk.Tk
    binds: dict[str, str] = {}

    colors: dict[str, str] = {}
    prefsdialog_count: int = 0
    helpabout_count: int = 0
    force_skips: list = []

    def __init__(self) -> None:
        self.active: int | None = None  # Starts out with no theme
        self.active_transparent: bool | None = None
        self.minwidth: int | None = None
        self.default_ui_scale: float | None = None  # None == not yet known
        self.startup_ui_scale: int | None = None

    def load_additional_themes(self) -> None:
        pass

    def initialize(self, root: tk.Tk):
        self.style = ttk.Style()
        self.root = root
        if not config.get_bool('transparent'):
            config.set('transparent', False)
        self.transparent = tk.BooleanVar(value=config.get_bool('transparent'))
        # Default dark theme colors
        if not config.get_str('dark_text'):
            config.set('dark_text', '#ff8000')  # "Tangerine" in OSX color picker
        if not config.get_str('dark_highlight'):
            config.set('dark_highlight', 'white')

        for theme_file in config.internal_theme_dir_path.glob('*/pkgIndex.tcl'):
            try:
                self.root.tk.call('source', theme_file)
                logger.info(f'loading theme package from "{theme_file}"')
                if theme_file.parent.name not in self.packages.values():
                    self.packages[len(self.packages)] = theme_file.parent.name.lower()
            except tk.TclError:
                logger.exception(f'Failure loading theme package "{theme_file}"')

    def register(self, widget: tk.Widget | tk.BitmapImage) -> None:
        assert isinstance(widget, (tk.BitmapImage, tk.Widget)), widget
        warnings.warn('theme.register() is no longer necessary as theme attributes are set on tk level',
                      DeprecationWarning, stacklevel=2)

    def register_alternate(self, pair: tuple, gridopts: dict) -> None:
        ...  # does any plugin even use this?

    def button_bind(self, widget: tk.Widget, command: Callable) -> None:
        ...  # does any plugin even use this?

    def update(self, widget: tk.Widget) -> None:
        """
        Apply current theme to a widget and its children.

        Also, register it for future updates.
        :param widget: Target widget.
        """
        assert isinstance(widget, (tk.BitmapImage, tk.Widget)), widget
        warnings.warn('theme.update() is no longer necessary as theme attributes are set on tk level',
                      DeprecationWarning, stacklevel=2)

    def to_hex(self, hex_color) -> str:
        hex_color = str(hex_color)
        hex_color = hex_color.lstrip()
        if not hex_color.startswith('#'):
            hex_color = self.root.winfo_rgb(hex_color)
            hex_color = [int(hex_color[i] // 256) for i in range(len(hex_color))]
            hex_color = '#{:02x}{:02x}{:02x}'.format(*hex_color)  # noqa: FS002
        return hex_color

    if sys.platform == 'win32':
        def hex_to_rgb(self, hex_color) -> Color:
            hex_color = self.to_hex(hex_color)
            hex_color = hex_color.strip('#')
            return ColorHelper.from_argb(255, int(hex_color[0:2], 16), int(hex_color[2:4], 16), int(hex_color[4:6], 16))

        def set_title_buttons_background(self, color: Color) -> None:
            hwnd = win32gui.GetParent(self.root.winfo_id())
            window = AppWindow.get_from_window_id(get_window_id_from_window(hwnd))
            window.title_bar.button_background_color = color
            window.title_bar.button_inactive_background_color = color

    def transparent_move(self, event=None) -> None:
        # to make it adjustable for any style we need to give this the background color of the title bar
        # that should turn transparent, ideally as hex value
        # upper left corner of our window
        x, y = self.root.winfo_rootx(), self.root.winfo_rooty()
        # lower right corner of our window
        max_x = x + self.root.winfo_width()
        max_y = y + self.root.winfo_height()
        # mouse position
        mouse_x, mouse_y = self.root.winfo_pointerx(), self.root.winfo_pointery()

        if sys.platform == 'win32':
            hwnd = win32gui.GetParent(self.root.winfo_id())
            window = AppWindow.get_from_window_id(get_window_id_from_window(hwnd))

        # check if mouse is inside the window
        if x <= mouse_x <= max_x and y <= mouse_y <= max_y:
            # mouse is inside the window area
            self.root.attributes("-transparentcolor", '')
            if sys.platform == 'win32':
                self.set_title_buttons_background(self.hex_to_rgb(self.style.lookup('TButton', 'background')))
                window.title_bar.background_color = self.hex_to_rgb(self.style.lookup('TButton', 'background'))
                window.title_bar.inactive_background_color = self.hex_to_rgb(self.style.lookup('TButton', 'background'))
                window.title_bar.button_hover_background_color = self.hex_to_rgb(
                    self.style.lookup('TButton', 'selectbackground'))
        else:
            self.root.attributes("-transparentcolor", self.style.lookup('TButton', 'background'))
            if sys.platform == 'win32':
                self.set_title_buttons_background(Colors.transparent)
                window.title_bar.background_color = Colors.transparent
                window.title_bar.inactive_background_color = Colors.transparent
                window.title_bar.button_hover_background_color = Colors.transparent

    # WORKAROUND $elite-dangerous-version | 2025/02/11 : Because for some reason the theme is not applied to
    # all widgets upon the second theme change we have to force it

    def load_colors(self):
        # load colors from the current theme which is a *.tcl file
        # and store them in the colors dict

        # get the current theme
        theme = config.get_int('theme')
        theme_name = self.packages[theme]

        # get the path to the theme file
        theme_file = config.internal_theme_dir_path / theme_name / (theme_name + '.tcl')

        # load the theme file
        with open(theme_file, 'r') as f:
            lines = f.readlines()
            foundstart = False
            for line in lines:
                # logger.info(line)
                if line.lstrip().startswith('array set colors'):
                    foundstart = True
                    continue
                if line.lstrip().startswith('}'):
                    break
                if foundstart:
                    pair = line.lstrip().replace('\n', '').replace('"', '').split()
                    self.colors[pair[0]] = pair[1]

        logger.info(f'Loaded colors: {self.colors}')

    def _get_all_widgets(self) -> list:
        all_widgets = []
        all_widgets.append(self.root)

        for child in self.root.winfo_children():
            all_widgets.append(child)
            all_widgets.extend(child.winfo_children())

        oldlen = 0
        newlen = len(all_widgets)

        while newlen > oldlen:
            oldlen = newlen
            for widget in all_widgets:
                try:
                    widget_children = widget.winfo_children()
                    for child in widget_children:
                        if child not in all_widgets:
                            all_widgets.append(child)
                except Exception as e:
                    logger.error(f'Error getting children of {widget}: {e}')
            newlen = len(all_widgets)
        return all_widgets

    def _force_theme_menubutton(self, widget) -> None:
        # get colors from map
        background = self.style.map('TMenubutton', 'background')
        foreground = self.style.map('TMenubutton', 'foreground')
        self.style.configure('TMenubutton', background=self.style.lookup('TMenubutton', 'background'))
        self.style.configure('TMenubutton', foreground=self.style.lookup('TMenubutton', 'foreground'))
        self.style.map('TMenubutton', background=[('active', background[0][1])])
        self.style.map('TMenubutton', foreground=[('active', foreground[0][1])])

    def _force_theme_menu(self, widget) -> None:
        colors = self.colors
        widget.configure(background=self.style.lookup('TMenu', 'background'))
        widget.configure(foreground=self.style.lookup('TMenu', 'foreground'))
        widget.configure(activebackground=colors['-selectbg'])
        widget.configure(activeforeground=colors['-selectfg'])

    def _force_theme_button(self, widget) -> None:
        colors = self.colors
        widget.configure(background=self.style.lookup('TButton', 'background'))
        widget.configure(foreground=self.style.lookup('TButton', 'foreground'))
        widget.configure(activebackground=colors['-selectbg'])
        widget.configure(activeforeground=colors['-selectfg'])

    def _force_theme_label(self, widget) -> None:
        widget.configure(background=self.style.lookup('TLabel', 'background'))
        widget.configure(foreground=self.style.lookup('TLabel', 'foreground'))

    def _force_theme_frame(self, widget) -> None:
        widget.configure(background=self.style.lookup('TFrame', 'background'))

    def _force_theme_scale(self, widget) -> None:
        # get colors from the current theme
        # keys are -fg, -bg, -disabledfg, -selectfg, -selectbg -highlight
        colors = self.colors
        # logger.info('foreground')
        widget.configure(foreground=colors['-fg'])
        # logger.info('highlightbackground')
        widget.configure(highlightbackground=colors['-bg'])
        # logger.info('activebackground')
        widget.configure(activebackground=colors['-selectbg'])
        # logger.info('background')
        widget.configure(background=colors['-bg'])
        # logger.info('highlight')
        widget.configure(highlightcolor=colors['-highlight'])
        # logger.info('trough')
        widget.configure(troughcolor=colors['-bg'])

    def _force_theme_hyperlink(self, widget) -> None:
        widget.configure(background=self.style.lookup('Link.TLabel', 'background'))
        widget.configure(foreground=self.style.lookup('Link.TLabel', 'foreground'))

    def _force_theme_base_plugins(self) -> None:
        """Force widgets that are immediately part of the root frame in the main ui and have to be forced seperately."""
        labels = [f'{appname.lower()}.cnv.in.cmdr_label',
                  f'{appname.lower()}.cnv.in.cmdr',
                  f'{appname.lower()}.cnv.in.ship_label',
                  f'{appname.lower()}.cnv.in.suit_label',
                  f'{appname.lower()}.cnv.in.suit',
                  f'{appname.lower()}.cnv.in.system_label',
                  f'{appname.lower()}.cnv.in.station_label',
                  f'{appname.lower()}.cnv.in.status']

        for label in labels:
            self._force_theme_label(self.root.nametowidget(label))

    def _force_theme_get_skips(self):
        prefscount = self.prefsdialog_count
        if prefscount == 1:
            prefscount = ""

        # Skipping widgets that shall continue to use the dark theme that is assigned to them.

        all_skips = [
            f".!preferencesdialog{prefscount}.!frame.!notebook.!frame2.!button",
            f".!preferencesdialog{prefscount}.!frame.!notebook.!frame2.!button2",
            f".!preferencesdialog{prefscount}.!frame.!notebook.!frame2.!label3",
            f".!preferencesdialog{prefscount}.!frame.!notebook.!frame2.!label4"
        ]

        # Get skips that got registered by plugins
        for skip in self.force_skips:
            if str(skip).startswith('.!preferencesdialog'):
                skip = f".!preferencesdialog{prefscount}" + str(skip).replace('.!preferencesdialog', '')
            all_skips.append(skip)

        return all_skips

    def _force_theme(self):
        logger.info('Forcing theme change')

        if sys.platform == 'win32':
            title_label = self.root.nametowidget('.title_label')
            title_icon = self.root.nametowidget('.title_icon')
            self._force_theme_label(title_label)
            self._force_theme_label(title_icon)

        self._force_theme_base_plugins()

        all_skips = self._force_theme_get_skips()

        all_widgets = self._get_all_widgets()

        for widget in all_widgets:
            try:
                if str(widget) in all_skips:
                    continue
                elif isinstance(widget, tk.Button):
                    self._force_theme_button(widget)
                elif isinstance(widget, HyperlinkLabel):
                    self._force_theme_hyperlink(widget)
                elif isinstance(widget, ttk.Menubutton):
                    self._force_theme_menubutton(widget)
                elif isinstance(widget, tk.Menu):
                    self._force_theme_menu(widget)
                elif isinstance(widget, tk.Scale):
                    self._force_theme_scale(widget)
                elif isinstance(widget, tk.Label):
                    self._force_theme_label(widget)
                elif isinstance(widget, tk.Frame):
                    self._force_theme_frame(widget)
                elif isinstance(widget,
                                (tk.Tk,
                                 tk.Canvas,
                                 tk.Checkbutton,
                                 ttk.Checkbutton,
                                 ttk.Frame,
                                 ttk.Separator,
                                 ttk.Scrollbar,
                                 ttk.Notebook,
                                 ttk.Radiobutton,
                                 ttk.Button,
                                 prefs.PreferencesDialog)):
                    continue
                else:
                    self._force_theme_label(widget)
            except Exception as e:
                logger.debug(f'Error forcing theme for {widget} with type {type(widget)}: {e}')

    def register_skip(self, widget: tk.Widget, prefs: bool = False) -> None:
        """
        Idea is to let plugins register skips for widgets that the plugin wants to define its own styles for.

           * Because _force_theme will just assign the theme even if the plugin creator had something else in mind.
        """
        # If we are in prefs the widget needs to start with .!preferencesdialog{number}.!frame.!notebook
        # If we are looking at a widget that is part of the main ui it needs to start with:
        # .edmarketconnector.cnv.in.plugin_{number}.!frame
        logger.info(f'Registering skip for {widget}')
        if prefs:
            logger.info('this one is supposed to be a Prefs skip')
        else:
            logger.info('this one is supposed to be a main ui skip')
        # self.force_skips.append(str(widget))

    def apply(self) -> None:
        logger.info('Applying theme')
        theme = config.get_int('theme')
        transparent = config.get_bool('transparent')

        if theme >= len(self.packages.values()):
            # The theme that was used before must have been deleted
            theme = self.THEME_DEFAULT
            config.set('theme', self.THEME_DEFAULT)

        try:
            self.root.tk.call('ttk::setTheme', self.packages[theme])
            # WORKAROUND $elite-dangerous-version | 2025/02/11 : Because for some reason the theme is not applied to
            # all widgets upon the second theme change we have to force it
            self.load_colors()
            self._force_theme()
        except tk.TclError:
            logger.exception(f'Failure setting theme: {self.packages[theme]}')

        if self.active == theme and self.active_transparent == transparent:
            return  # Don't need to mess with the window manager
        self.active = theme
        self.active_transparent = transparent

        self.root.withdraw()
        self.root.update_idletasks()  # Size gets recalculated here
        if sys.platform == 'win32':
            hwnd = win32gui.GetParent(self.root.winfo_id())
            window = AppWindow.get_from_window_id(get_window_id_from_window(hwnd))
            title_gap: ttk.Frame = self.root.nametowidget('.alternate_menubar.title_gap')

            window.title_bar.extends_content_into_title_bar = True
            title_gap['height'] = window.title_bar.height

            if self.transparent.get():
                self.set_title_buttons_background(Colors.transparent)
                window.title_bar.background_color = Colors.transparent
                window.title_bar.inactive_background_color = Colors.transparent
                window.title_bar.button_hover_background_color = Colors.transparent
                # TODO prevent loss of focus when hovering the title bar area  # fixed by transparent_move,
                # we just don't regain focus when hovering over the title bar,
                # we have to hover over some visible widget first.
                win32gui.SetWindowLong(hwnd, win32con.GWL_EXSTYLE,
                                       win32con.WS_EX_APPWINDOW | win32con.WS_EX_LAYERED)  # Add to taskbar
                self.binds['<Enter>'] = self.root.bind('<Enter>', self.transparent_move)
                self.binds['<FocusIn>'] = self.root.bind('<FocusIn>', self.transparent_move)
                self.binds['<Leave>'] = self.root.bind('<Leave>', self.transparent_move)
                self.binds['<FocusOut>'] = self.root.bind('<FocusOut>', self.transparent_move)
            else:
                # window.title_bar.reset_to_default()  # This makes it crash when switchthing back to default
                self.set_title_buttons_background(self.hex_to_rgb(self.style.lookup('TButton', 'background')))
                window.title_bar.background_color = self.hex_to_rgb(self.style.lookup('TButton', 'background'))
                window.title_bar.inactive_background_color = self.hex_to_rgb(self.style.lookup('TButton', 'background'))
                window.title_bar.button_hover_background_color = self.hex_to_rgb(
                    self.style.lookup('TButton', 'selectbackground'))
                win32gui.SetWindowLong(hwnd, win32con.GWL_EXSTYLE, win32con.WS_EX_APPWINDOW)  # Add to taskbar
                for event, bind in self.binds.items():
                    self.root.unbind(event, bind)
                self.binds.clear()
        else:
            if dpy:
                xroot = Window()
                parent = Window()
                children = Window()
                nchildren = c_uint()
                XQueryTree(dpy, self.root.winfo_id(), byref(xroot), byref(parent), byref(children), byref(nchildren))
                if theme == self.THEME_DEFAULT:
                    wm_hints = motif_wm_hints_normal
                else:  # Dark *or* Transparent
                    wm_hints = motif_wm_hints_dark

                XChangeProperty(
                    dpy, parent, motif_wm_hints_property, motif_wm_hints_property, 32, PropModeReplace, wm_hints, 5
                )

                XFlush(dpy)

        self.root.deiconify()
        self.root.wait_visibility()  # need main window to be displayed before returning

        if not self.minwidth:
            self.minwidth = self.root.winfo_width()  # Minimum width = width on first creation
            self.root.minsize(self.minwidth, -1)


# singleton
theme = _Theme()
