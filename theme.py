"""
theme.py - Theme support.

Copyright (c) EDCD, All Rights Reserved
Licensed under the GNU General Public License.
See LICENSE file.

Believe us, this used to be much worse before ttk's theme support was properly leveraged.
"""
from __future__ import annotations

import os
import sys
import tkinter as tk
import warnings
from tkinter import ttk
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

    def __init__(self) -> None:
        self.active: int | None = None  # Starts out with no theme
        self.minwidth: int | None = None
        self.default_ui_scale: float | None = None  # None == not yet known
        self.startup_ui_scale: int | None = None

    def initialize(self, root: tk.Tk):
        self.style = ttk.Style()
        self.root = root

        # Default dark theme colors
        if not config.get_str('dark_text'):
            config.set('dark_text', '#ff8000')  # "Tangerine" in OSX color picker
        if not config.get_str('dark_highlight'):
            config.set('dark_highlight', 'white')

        for theme_file in config.internal_theme_dir_path.glob('*/pkgIndex.tcl'):
            try:
                self.root.tk.call('source', theme_file)
                logger.info(f'loading theme package from "{theme_file}"')
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
            hex_color = '#{:02x}{:02x}{:02x}'.format(*hex_color)
        return hex_color

    def hex_to_rgb(self, hex_color) -> Color:
        hex_color = self.to_hex(hex_color)
        hex_color = hex_color.strip('#')
        return ColorHelper.from_argb(255, int(hex_color[0:2], 16), int(hex_color[2:4], 16), int(hex_color[4:6], 16))

    def transparent_move(self, event=None):
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

    def set_title_buttons_background(self, color: Color):
        hwnd = win32gui.GetParent(self.root.winfo_id())
        window = AppWindow.get_from_window_id(get_window_id_from_window(hwnd))
        window.title_bar.button_background_color = color
        window.title_bar.button_inactive_background_color = color

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

    # WORKAROUND $elite-dangerous-version | 2025/02/11 : Because for some reason the theme is not applied to
    # all widgets upon the second theme change we have to force it

    def _get_all_widgets(self):
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

    def _force_theme_menubutton(self, widget):
        # get colors from map
        background = self.style.map('TMenubutton', 'background')
        foreground = self.style.map('TMenubutton', 'foreground')
        # logger.info(f'colors: {background} {foreground}')
        self.style.configure('TMenubutton', background=self.style.lookup('TMenubutton', 'background'))
        self.style.configure('TMenubutton', foreground=self.style.lookup('TMenubutton', 'foreground'))
        self.style.map('TMenubutton', background=[('active', background[0][1])])
        self.style.map('TMenubutton', foreground=[('active', foreground[0][1])])

    def _force_theme_menu(self, widget):
        colors = self.colors
        widget.configure(background=self.style.lookup('TMenu', 'background'))
        widget.configure(foreground=self.style.lookup('TMenu', 'foreground'))
        widget.configure(activebackground=colors['-selectbg'])
        widget.configure(activeforeground=colors['-selectfg'])

    def _force_theme_button(self, widget):
        # logger.info(f'Forcing theme change for {widget}')
        widget.configure(background=self.style.lookup('TButton', 'background'))
        widget.configure(foreground=self.style.lookup('TButton', 'foreground'))
        if type(widget) is ttk.Button:
            style_change = {'activebackground': self.style.lookup('TButton', 'activebackground'),
                            'activeforeground': self.style.lookup('TButton', 'activeforeground'),
                            'selectbackground': self.style.lookup('TButton', 'selectbackground'),
                            'selectforeground': self.style.lookup('TButton', 'selectforeground')}
            # logger.info(f'Forcing theme change for {widget} with {style_change}')
            widget.configure(**style_change)
        # find the color in the self.style for the pressed state
        # self.style.lookup()

    def _force_theme_label(self, widget):
        # logger.info(f'Forcing theme change for {widget}')
        widget.configure(background=self.style.lookup('TLabel', 'background'))
        widget.configure(foreground=self.style.lookup('TLabel', 'foreground'))

    def _force_theme_frame(self, widget):
        # logger.info(f'Forcing theme change for {widget}')
        widget.configure(background=self.style.lookup('TFrame', 'background'))
        # widget.configure(style=self.style.lookup('TFrame'))

    def _force_theme_optionmenu(self, widget):
        # destroy and rebuild the widget
        # get all options from options menu
        options = widget['menu'].entries()
        # get the current value
        value = widget.get()
        # get the current style
        style = widget.cget('style')
        # get the current command
        command = widget.cget('command')
        # get the current textvariable
        textvariable = widget.cget('textvariable')
        # get the current variable
        variable = widget.cget('variable')
        # get the current width
        width = widget.cget('width')
        # get the current height
        height = widget.cget('height')

    def _force_theme_scale(self, widget):
        # destroy and rebuild the widget
        """activebackground 	The color of the slider when the mouse is over it. See Section 5.3, “Colors”.
        bg or background 	The background color of the parts of the widget that are outside the trough.
        bd or borderwidth 	Width of the 3-d border around the trough and slider. Default is two pixels. For acceptable values, see Section 5.1, “Dimensions”.
        command 	A procedure to be called every time the slider is moved. This procedure will be passed one argument, the new scale value. If the slider is moved rapidly, you may not get a callback for every possible position, but you'll certainly get a callback when it settles.
        cursor 	The cursor that appears when the mouse is over the scale. See Section 5.8, “Cursors”.
        digits 	The way your program reads the current value shown in a scale widget is through a control variable; see Section 52, “Control variables: the values behind the widgets”. The control variable for a scale can be an IntVar, a DoubleVar (for type float), or a StringVar. If it is a string variable, the digits option controls how many digits to use when the numeric scale value is converted to a string.
        font 	The font used for the label and annotations. See Section 5.4, “Type fonts”.
        fg or foreground 	The color of the text used for the label and annotations.
        from_ 	A float value that defines one end of the scale's range. For vertical scales, this is the top end; for horizontal scales, the left end. The underbar (_) is not a typo: because from is a reserved word in Python, this option is spelled from_. The default is 0.0. See the to option, below, for the other end of the range.
        highlightbackground 	The color of the focus highlight when the scale does not have focus. See Section 53, “Focus: routing keyboard input”.
        highlightcolor 	The color of the focus highlight when the scale has the focus.
        highlightthickness 	The thickness of the focus highlight. Default is 1. Set highlightthickness=0 to suppress display of the focus highlight.
        label 	You can display a label within the scale widget by setting this option to the label's text. The label appears in the top left corner if the scale is horizontal, or the top right corner if vertical. The default is no label.
        length 	The length of the scale widget. This is the x dimension if the scale is horizontal, or the y dimension if vertical. The default is 100 pixels. For allowable values, see Section 5.1, “Dimensions”.
        orient 	Set orient=tk.HORIZONTAL if you want the scale to run along the x dimension, or orient=tk.VERTICAL to run parallel to the y-axis. Default is vertical.
        relief 	With the default relief=tk.FLAT, the scale does not stand out from its background. You may also use relief=tk.SOLID to get a solid black frame around the scale, or any of the other relief types described in Section 5.6, “Relief styles”.
        repeatdelay 	This option controls how long button 1 has to be held down in the trough before the slider starts moving in that direction repeatedly. Default is repeatdelay=300, and the units are milliseconds.
        repeatinterval 	This option controls how often the slider jumps once button 1 has been held down in the trough for at least repeatdelay milliseconds. For example, repeatinterval=100 would jump the slider every 100 milliseconds.
        resolution 	Normally, the user will only be able to change the scale in whole units. Set this option to some other value to change the smallest increment of the scale's value. For example, if from_=-1.0 and to=1.0, and you set resolution=0.5, the scale will have 5 possible values: -1.0, -0.5, 0.0, +0.5, and +1.0. All smaller movements will be ignored. Use resolution=-1 to disable any rounding of values.
        showvalue 	Normally, the current value of the scale is displayed in text form by the slider (above it for horizontal scales, to the left for vertical scales). Set this option to 0 to suppress that label.
        sliderlength 	Normally the slider is 30 pixels along the length of the scale. You can change that length by setting the sliderlength option to your desired length; see Section 5.1, “Dimensions”.
        sliderrelief 	By default, the slider is displayed with a tk.RAISED relief style. For other relief styles, set this option to any of the values described in Section 5.6, “Relief styles”.
        state 	Normally, scale widgets respond to mouse events, and when they have the focus, also keyboard events. Set state=tk.DISABLED to make the widget unresponsive.
        takefocus 	Normally, the focus will cycle through scale widgets. Set this option to 0 if you don't want this behavior. See Section 53, “Focus: routing keyboard input”.
        tickinterval 	Normally, no “ticks” are displayed along the scale. To display periodic scale values, set this option to a number, and ticks will be displayed on multiples of that value. For example, if from_=0.0, to=1.0, and tickinterval=0.25, labels will be displayed along the scale at values 0.0, 0.25, 0.50, 0.75, and 1.00. These labels appear below the scale if horizontal, to its left if vertical. Default is 0, which suppresses display of ticks.
        to 	A float value that defines one end of the scale's range; the other end is defined by the from_ option, discussed above. The to value can be either greater than or less than the from_ value. For vertical scales, the to value defines the bottom of the scale; for horizontal scales, the right end. The default value is 100.0.
        troughcolor 	The color of the trough.
        variable 	The control variable for this scale, if any; see Section 52, “Control variables: the values behind the widgets”. Control variables may be from class IntVar, DoubleVar (for type float), or StringVar. In the latter case, the numerical value will be converted to a string. See the the digits option, above, for more information on this conversion.
        width"""
        # get parent of widget
        parent = widget.master
        # get all values from the widget



        # destroy widget
        widget.destroy()
        # create new widget with values
        tk.Scale

    def _force_theme(self):
        logger.info('Forcing theme change')
        # get absolute top root

        if sys.platform == 'win32':
            title_label = self.root.nametowidget('.title_label')
            title_icon = self.root.nametowidget('.title_icon')
            self._force_theme_label(title_label)
            self._force_theme_label(title_icon)

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

        all_widgets = self._get_all_widgets()

        for widget in all_widgets:
            try:
                if isinstance(widget, tk.Button or ttk.Button):
                    self._force_theme_button(widget)
                elif isinstance(widget, tk.Label):
                    self._force_theme_label(widget)
                elif isinstance(widget, tk.Frame or ttk.Frame):
                    self._force_theme_frame(widget)
                elif isinstance(widget, ttk.OptionMenu):
                    self._force_theme_optionmenu(widget)
                elif isinstance(widget, ttk.Menubutton):
                    self._force_theme_menubutton(widget)
                elif isinstance(widget, tk.Menu):
                    self._force_theme_menu(widget)
                elif isinstance(widget, tk.Scale):
                    self.force_theme
                else:
                    self._force_theme_label(widget)
            except Exception as e:
                logger.warning(f'Error forcing theme for {widget}: {e}')

    def apply(self) -> None:
        logger.info('Applying theme')
        theme = config.get_int('theme')
        try:
            self.root.tk.call('ttk::setTheme', self.packages[theme])
            # WORKAROUND $elite-dangerous-version | 2025/02/11 : Because for some reason the theme is not applied to
            # all widgets upon the second theme change we have to force it
            self.load_colors()
            self._force_theme()
        except tk.TclError:
            logger.exception(f'Failure setting theme: {self.packages[theme]}')

        if self.active == theme:
            return  # Don't need to mess with the window manager
        self.active = theme

        self.root.withdraw()
        self.root.update_idletasks()  # Size gets recalculated here
        if sys.platform == 'win32':
            hwnd = win32gui.GetParent(self.root.winfo_id())
            window = AppWindow.get_from_window_id(get_window_id_from_window(hwnd))
            title_gap: ttk.Frame = self.root.nametowidget('.alternate_menubar.title_gap')

            window.title_bar.extends_content_into_title_bar = True
            title_gap['height'] = window.title_bar.height

            if theme != self.THEME_TRANSPARENT:
                # window.title_bar.reset_to_default()  # This makes it crash when switchthing back to default
                self.set_title_buttons_background(self.hex_to_rgb(self.style.lookup('TButton', 'background')))
                window.title_bar.background_color = self.hex_to_rgb(self.style.lookup('TButton', 'background'))
                window.title_bar.inactive_background_color = self.hex_to_rgb(self.style.lookup('TButton', 'background'))
                window.title_bar.button_hover_background_color = self.hex_to_rgb(
                    self.style.lookup('TButton', 'selectbackground'))
            else:
                self.set_title_buttons_background(Colors.transparent)
                window.title_bar.background_color = Colors.transparent
                window.title_bar.inactive_background_color = Colors.transparent
                window.title_bar.button_hover_background_color = Colors.transparent

            if theme == self.THEME_TRANSPARENT:
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
                win32gui.SetWindowLong(hwnd, win32con.GWL_EXSTYLE, win32con.WS_EX_APPWINDOW)  # Add to taskbar
                for event, bind in self.binds.items():
                    self.root.unbind(event, bind)
                self.binds.clear()

            # self.binds['<<ThemeChanged>>'] = self.root.bind('<<ThemeChanged>>', self._force_theme)
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
