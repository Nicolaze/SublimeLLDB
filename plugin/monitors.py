# -*- mode: python; coding: utf-8 -*-

import os
import fcntl
import Queue
import select
import threading

import sublime
import sublime_plugin

from lldb_wrappers import thread_created
from debug import debug, debugMonitors
from root_objects import lldb_views_update, del_lldb_view,              \
                         lldb_views_destroy,                            \
                         get_lldb_view_for, maybe_get_lldb_output_view


class LLDBUIUpdater(threading.Thread):
    _done = False

    eProcessStopped = 1 << 0
    eBreakpointAdded = 1 << 1
    eBreakpointChanged = 1 << 2
    # eBreakpointEnabled = 1 << 2
    eBreakpointRemoved = 1 << 3
    # eBreakpointDisabled = 1 << 4
    eUIUpdaterExit = 1 << 4

    def __init__(self):
        super(LLDBUIUpdater, self).__init__(name='sublime.lldb.UIUpdater')
        self.daemon = True
        self.__queue = Queue.Queue()
        self.start()

    def stop(self):
        self.__queue.put(self.packet(self.eUIUpdaterExit))

    def process_stopped(self, state, epilogue):
        self.__queue.put(self.packet(self.eProcessStopped, state, epilogue))

    def breakpoint_added(self, file, line, is_enabled):
        packet = self.packet(self.eBreakpointAdded, file, line, is_enabled)
        self.__queue.put(packet)

    def breakpoint_removed(self, file, line, is_enabled):
        packet = self.packet(self.eBreakpointRemoved, file, line, is_enabled)
        self.__queue.put(packet)

    def breakpoint_changed(self, file, line, is_enabled):
        packet = self.packet(self.eBreakpointChanged, file, line, is_enabled)
        self.__queue.put(packet)

    def get_next_packet(self):
        packet = self.__queue.get()
        self.__queue.task_done()
        return packet

    def packet(self, *args):
        return args

    def maybe_get_view_for_file(self, filename):
        return maybe_get_lldb_output_view(None, filename)

    def run(self):
        thread_created('<' + self.name + '>')

        packet = self.get_next_packet()
        while packet:
            debug(debugMonitors, 'LLDBUIUpdater: ' + str(packet))
            if packet[0] == self.eProcessStopped:
                # state = packet[1]
                epilogue = packet[2]
                lldb_views_update(epilogue)
                # Should we wait or signal ourselves from lldb_views_refresh?
                # We'll have to signal ourselves if we find that the views get marked,
                # instead of the input box

                # Focus the best view
                # Ask for input, if appropriate (epilogue)
            elif packet[0] == self.eBreakpointAdded:
                filename = packet[1]
                line = packet[2]
                is_enabled = packet[3]

                v = self.maybe_get_view_for_file(filename)
                if v is not None:
                    sublime.set_timeout(lambda: v.mark_bp(line, is_enabled), 0)

            elif packet[0] == self.eBreakpointChanged:
                filename = packet[1]
                line = packet[2]
                is_enabled = packet[3]

                v = self.maybe_get_view_for_file(filename)
                if v is not None:
                    # Create a new scope so we don't get the line changed
                    # before change_bp is executed.
                    def scope(view, line):
                        sublime.set_timeout(lambda: view.change_bp(line, is_enabled), 0)
                    scope(v, line)

            elif packet[0] == self.eBreakpointRemoved:
                filename = packet[1]
                line = packet[2]
                is_enabled = packet[3]

                v = self.maybe_get_view_for_file(filename)
                if v is not None:
                    sublime.set_timeout(lambda: v.unmark_bp(line, is_enabled), 0)

            elif packet[0] == self.eUIUpdaterExit:
                lldb_views_destroy()
                return

            packet = self.get_next_packet()


class FileMonitor(threading.Thread):
    TIMEOUT = 10  # Our default select timeout is 10 secs

    def __init__(self, callback, *files):
        super(FileMonitor, self).__init__(name='sublime.lldb.debugger.out.monitor')
        self._callback = callback
        self._files = list(files)
        self._done = False
        self.start()

    def isDone(self):
        return self._done

    def setDone(self, done=True):
        self._done = done

    def run(self):
        thread_created('<' + self.name + '>')

        def fun(file):
            # make stdin a non-blocking file
            fd = file.fileno()
            fl = fcntl.fcntl(fd, fcntl.F_GETFL)
            fcntl.fcntl(fd, fcntl.F_SETFL, fl | os.O_NONBLOCK)

        rlist = self._files
        map(fun, rlist)

        while not self.isDone() and rlist is not []:
            r, w, x = select.select(rlist, [], [], FileMonitor.TIMEOUT)
            if len(r) == 0:
                # Timeout occurred: check for self.isDone()
                continue
            for f in r:
                data = f.read()
                if data == '':
                    debug(debugMonitors, 'removing ' + str(f) + ' from FileMonitor')
                    rlist.remove(f)
                self._callback(data)

        self.setDone(True)


class LLDBUIListener(sublime_plugin.EventListener):
    def __init__(self):
        super(LLDBUIListener, self).__init__()
        debug(debugMonitors, 'Started UIListener')

    def on_close(self, v):
        lldb_view = get_lldb_view_for(v)
        # TODO: Check if there are other views for the same buffer
        # I blame Sublime Text for mixing both concepts into “something”.
        if lldb_view:
            del_lldb_view(lldb_view)

    def on_load(self, v):
        lldb_view = get_lldb_view_for(v)
        if lldb_view:
            debug(debugMonitors, 'on_load: isloading: %s, %s' % (str(v.is_loading()), str((repr(lldb_view), lldb_view.file_name()))))
            # TODO: Instead of updating it here (pre_update will execute
            # on the main thread), send a message to the LLDBUIUpdater
            lldb_view.full_update()
