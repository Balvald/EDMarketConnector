
"""
May be imported by plugins
"""
import tkinter as tk
from tkinter import ttk


class ScrollableFrame(ttk.Frame):
    """ Scrollable Frame - no idea if this can stay here of if needs to be in another/its own file.
    * Use the  ttk.Frame 'self.in_frame' of this ScrollableFrame thats inside the canvas (at self.canvas)
      so that everything can scroll within the ScrollableFrame.
    * It comes with working Scrollbars and all the bells and whistles.
      Scroll around via mousewheel, vertical even horizontal.
    * It supports resizing and vanishing the horizontral and vertical scrollbars if the window is bigger
      than what the canvas/interior frame requires for size.
    * The scrollbars and the canvas itself use pack() instead of grid() because of some the scrollbars
      vanishing when resizing the window and not being able to find an equivalent grid command to keep
      always visible when the window is smaller than the canvas/interior frame.
    * Though within the canvas, the in_frame we can again use grid() to our hearts content.
    """

    # vertical scrolling controls
    def _on_mousewheel_vert(self, event):
        if self.canvas.winfo_height() > self.in_frame.winfo_height():
            return
        self.canvas.yview_scroll(-1 * int(event.delta / 120), "units")

    def _set_yview(self, *args):
        if self.canvas.winfo_height() > self.in_frame.winfo_height():
            return
        self.canvas.yview(*args)
        self.in_frame.update_idletasks()

    # horizontal scrolling controls
    def _on_mousewheel_hori(self, event):
        # prevent horizontal scrolling if the window is wider than the canvas or the interior frame
        # canvas and interior frame are the same width at any point anyway
        if (self.winfo_toplevel().winfo_width()) > (self.canvas.winfo_reqwidth()+15):
            return
        self.canvas.xview_scroll(-1 * int(event.delta / 120), "units")

    def _set_xview(self, *args):
        if (self.winfo_toplevel().winfo_width()) > (self.canvas.winfo_reqwidth()+15):
            return
        self.canvas.xview(*args)
        self.in_frame.update_idletasks()

    def _theme(self, event):
        # get the background color and handle the colour of the canvas
        # Sometimes it does not want to change after theme.apply() so we encourage it a bit more.
        color = ttk.Style().lookup('TLabel', 'background')
        self.canvas.config(background=color)

    # constructor
    def __init__(self, parent, *args, **kw):
        ttk.Frame.__init__(self, parent, *args, **kw)

        # creating scrollbar and canvas
        vscrollbar = ttk.Scrollbar(self, orient=tk.VERTICAL, name='vertscroll')
        # grid for some reason seems to enable more weird behavior for the scrollbar than pack.
        vscrollbar.pack(fill=tk.Y, side=tk.RIGHT, expand=False, anchor=tk.E)
        # vscrollbar.grid(row=0, column=1, sticky=tk.NS+tk.E, rowspan=1, columnspan=1)

        # Horizontal Scrollbar could be used but when allowing scrolling while the window is
        # smaller than the requestedsize for the canvas/interior frame,
        # the stuff inside the frame gets cut off from whence we scrolled which is a bummer.
        hscrollbar = ttk.Scrollbar(self, orient=tk.HORIZONTAL, name='horiscroll')
        hscrollbar.pack(fill=tk.X, side=tk.BOTTOM, expand=False, anchor=tk.S)

        self.canvas = tk.Canvas(self,
                                bd=0,
                                highlightthickness=0,
                                yscrollcommand=vscrollbar.set,
                                xscrollcommand=hscrollbar.set,
                                name='cnv')
        # pack over grid.
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        # self.canvas.grid(row=0, column=0, sticky=tk.NSEW)
        # vscrollbar.lift(self.canvas)

        vscrollbar.config(command=self._set_yview)
        hscrollbar.config(command=self._set_xview)

        # reset view
        self.canvas.xview_moveto(0)
        self.canvas.yview_moveto(0)

        # interior frame that will scroll along
        self.in_frame = ttk.Frame(self.canvas, name='in')
        self.in_frame_id = self.canvas.create_window(0,
                                                     0,
                                                     window=self.in_frame,
                                                     anchor=tk.NW)

        self.grid(sticky=tk.NSEW)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        self.columnconfigure(1, weight=10)

        # adjust canvas upon changing size and scrollregion upon change in frame
        def _configure_in_frame(event):
            # match scroll region to requested frame size
            in_frame_size = (self.in_frame.winfo_reqwidth(),
                             self.in_frame.winfo_reqheight())
            self.canvas.config(scrollregion="0 0 %s %s" % in_frame_size)
            if self.in_frame.winfo_reqwidth() != self.canvas.winfo_width():
                self.canvas.config(width=self.in_frame.winfo_reqwidth())

        # adjust in_frame_id window size upon change in canvas
        def _configure_canvas(event):
            if self.in_frame.winfo_reqwidth() != self.canvas.winfo_width():
                # set the window width to fit the canvas
                self.canvas.itemconfigure(self.in_frame_id, width=self.canvas.winfo_reqwidth())

            # hide or show scroll bar as needed
            if self.in_frame.winfo_reqheight() > self.canvas.winfo_height():
                # pack over grid in this case. It stays put unlike when using grid.
                # I don't know how to make the equivalent call for grid so it won't vanish.
                vscrollbar.pack(fill=tk.Y, side=tk.RIGHT, expand=False, anchor=tk.E, before=self.canvas)
                # vscrollbar.grid(row=0, column=1, sticky=tk.NS+tk.E, rowspan=1, columnspan=1)
                # vscrollbar.lift(self.canvas)
            else:
                vscrollbar.pack_forget()
                # vscrollbar.grid_forget()

            if self.canvas.winfo_reqwidth() > self.canvas.winfo_width():
                hscrollbar.pack(fill=tk.X, side=tk.BOTTOM, expand=False, anchor=tk.S, before=self.canvas)
                self.canvas.config()
            else:
                hscrollbar.pack_forget()

        self.in_frame.bind('<Configure>', _configure_in_frame)
        self.canvas.bind('<Configure>', _configure_canvas)
        # enables scrolling while being over the canvas
        self.canvas.bind_all("<MouseWheel>", self._on_mousewheel_vert)
        self.canvas.bind_all("<Shift-MouseWheel>", self._on_mousewheel_hori)

        # WORKAROUND $elite-version-number | 2025/02/11 : Forcing color change in canvas
        # Always forcing the canvas to update its background color
        # technically a workaround.
        self.bind('<<ThemeChanged>>', self._theme)
