# -*- mode: python; coding: utf-8 -*-

import sublime
import sublime_plugin

# FIXME: Use lldb_wrappers
from lldb_wrappers import BIG_TIMEOUT, LldbListener, SublimeBroadcaster, start_listening_for_breakpoint_changes, \
    start_listening_for_process_events, interpret_command
import lldb_wrappers
import lldb
import lldbutil

import time
import Queue
import threading

from root_objects import lldb_instance, set_lldb_instance, \
                         lldb_view_send,  \
                         thread_created, show_lldb_panel,  \
                         window_ref

from utilities import stdout_msg, stderr_msg


def debug_thr():
    print ('thread id: ' + threading.current_thread().name)
    # traceback.print_stack()


def debug(string):
    print threading.current_thread().name + ' ' + str(string)


def debugif(b, str):
    if b:
        debug(str)


lldb_i_o_thread = None
lldb_event_monitor_thread = None
lldb_markers_thread = None
lldb_last_location_view = None
lldb_current_location = None
lldb_file_markers_queue = Queue.Queue()

def marker_update(marks, args=(), after=None):
    dict = {'marks': marks, 'args': args, 'after': after}
    lldb_file_markers_queue.put(dict)


def cleanup(window, full=True):
    debug('cleaning up the lldb plugin')

    sublime.set_timeout(lambda: update_code_view(window, None), 0)
    if lldb_instance() is not None:
        lldb_instance().destroy()
        lldb_wrappers.terminate()
        set_lldb_instance(None)

    # close the pipes
    # if broadcaster is not None:
    #     broadcaster.end()
    # broadcaster = None


def kill_monitors():
    global lldb_i_o_thread, lldb_event_monitor_thread, lldb_markers_thread

    cleanup(window_ref())
    if lldb_i_o_thread is not None and lldb_i_o_thread.is_alive():
        lldb_i_o_thread.kill()
        lldb_i_o_thread = None
    if lldb_event_monitor_thread is not None and lldb_event_monitor_thread.is_alive():
        lldb_event_monitor_thread.kill()
        lldb_event_monitor_thread = None
    if lldb_markers_thread is not None and lldb_markers_thread.is_alive():
        lldb_markers_thread.kill()
        lldb_markers_thread = None


def launch_monitor(fun, name='<monitor thread>', args=()):
    t = threading.Thread(target=fun, name=name, args=args)
    # t.daemon = True
    t.start()


def launch_i_o_monitor(*args):
    global lldb_i_o_thread
    if lldb_i_o_thread and not lldb_i_o_thread.is_alive():
        lldb_i_o_thread.join()

    lldb_i_o_thread = launch_monitor(lldb_i_o_monitor,
                                     name='<sublime-lldb i/o monitor>',
                                     args=args)


def launch_markers_monitor(*args):
    global lldb_markers_thread
    if lldb_markers_thread and not lldb_markers_thread.is_alive():
        lldb_markers_thread.join()

    lldb_markers_thread = launch_monitor(lldb_markers_monitor,
                                         name='<sublime-lldb file markers monitor>',
                                         args=args)


def launch_event_monitor(*args):
    global lldb_event_monitor_thread
    if lldb_event_monitor_thread is not None and \
        lldb_event_monitor_thread.is_alive():
        lldb_event_monitor_thread.join()

    lldb_event_monitor_thread = launch_monitor(lldb_event_monitor,
                                               name='<sublime-lldb event monitor>',
                                               args=args)


def lldb_i_o_monitor():
    # thread_created(threading.current_thread().name)
    # debug_thr()
    # debug('started')

    # listener = LldbListener(lldb.SBListener('i/o listener'), lldb_instance())
    # listener.start_listening_for_events(broadcaster,
    #                                 SublimeBroadcaster.eBroadcastBitsSTDOUT |
    #                                 SublimeBroadcaster.eBroadcastBitsSTDERR |
    #                                 SublimeBroadcaster.eBroadcastBitDidExit |
    #                                 SublimeBroadcaster.eBroadcastBitShouldExit)

    # if listener.valid:
    #     done = False
    #     while not done:
    #         debug('listening at: ' + str(listener.SBListener))
    #         ev = listener.wait_for_event()
    #         if ev.valid:
    #             debug('Got event: ' + lldbutil.get_description(ev.SBEvent))
    #             if ev.broadcaster.valid:
    #                 if ev.type & SublimeBroadcaster.eBroadcastBitShouldExit \
    #                     or ev.type & SublimeBroadcaster.eBroadcastBitDidExit:
    #                     debug('leaving due to SublimeBroadcaster')
    #                     done = True
    #                     continue
    #                 elif ev.type & SublimeBroadcaster.eBroadcastBitsSTDOUT:
    #                     debug('stdout bits')
    #                     lldb_view_send(ev.string)
    #                 elif ev.type & SublimeBroadcaster.eBroadcastBitsSTDERR:
    #                     debug('stderr bits')
    #                     string = 'err> ' + ev.string
    #                     string.replace('\n', '\nerr> ')
    #                     lldb_view_send(string)
    debug('leaving...')


# def lldb_i_o_monitor():
#     thread_created(threading.current_thread().name)
#     debug_thr()
#     debug('started')

#     while lldb_instance() != None:
#         lldberr = lldb_output_fh()
#         lldbout = lldb_error_fh()

#         # debug('lldberr: ' + str(lldberr))
#         # debug('lldbout: ' + str(lldbout))

#         input = []
#         if lldbout:
#             input.append(lldbout.fileno())
#         if lldberr:
#             input.append(lldberr.fileno())

#         if len(input) > 0:
#             try:
#                 input, output, x = select.select(input, [], [])
#             except IOError as e:
#                 debug("I/O error({0}): {1}".format(e.errno, e.strerror))
#                 if e.errno == errno.EDABFD:
#                     debug('i/o monitor: ' + \
#                             'I suppose lldb error or output file was closed')
#                     debug('i/o: retrying')
#         else:
#             # debug('waiting for select (timeout)')
#             # We're not waiting for input, set a timeout
#             input, output, x = select.select([], [], [], 3.14)

#         for h in input:
#             debug('for h in input: ' + str(h))
#             fh = None
#             if h == lldbout.fileno():
#                 fh = lldbout
#             elif h == lldberr.fileno():
#                 fh = lldberr

#             debug('  ' + str(fh.closed))
#             if not fh.closed:
#                 string = fh.read()
#                 debug(string)
#                 if fh == lldbout:
#                     sublime.set_timeout(lambda: lldb_view_write(string), 0)
#                 if fh == lldberr:
#                     # We're sure we read something
#                     string.replace('\n', '\nerr> ')
#                     string = 'err> ' + string

#                 sublime.set_timeout(lambda: lldb_view_write(string), 0)

#     debug('stopped')


def lldb_markers_monitor(w):
    thread_created(threading.current_thread().name)
    debug_thr()
    debug('started')

    done = False
    while not done:
        v = lldb_file_markers_queue.get(True)
        m = v['marks']
        args = v['args']
        after = v['after']

        debug('got: ' + str(v))
        if 'pc' == m:
            f = lambda: update_code_view(w, *args)
        elif 'bp' == m:
            f = lambda: update_breakpoints(w, *args)
        elif 'all' == m:
            f = lambda: (update_breakpoints(w, *args), update_code_view(w, *args))
        elif 'delete' == m:
            done = True
            f = lambda: (update_breakpoints(w, *args), update_code_view(w, *args))

        if after:
            sublime.set_timeout(lambda: (f(), after()), 0)
        else:
            sublime.set_timeout(f, 0)

    debug('stopped')


def update_code_view(window, entry, scope='entity.name.class'):
    global lldb_last_location_view
    if lldb_last_location_view is not None:
        lldb_last_location_view.erase_regions("lldb-location")

    global lldb_current_location
    lldb_current_location = None

    if entry:
        (directory, file, line, column) = entry
        filename = directory + '/' + file
        lldb_current_location = (filename, line, column, scope)

        loc = filename + ':' + str(line) + ':' + str(column)

        window.focus_group(0)
        view = window.open_file(loc, sublime.ENCODED_POSITION)
        window.set_view_index(view, 0, 0)

        # If the view is already loaded:
        # (Otherwise, let the listener do the work)
        if not view.is_loading():
            lldb_last_location_view = view
            mark_code_loc(view, lldb_current_location)

    else:
        debug("No location info available")


def mark_code_loc(view, loc):
    line = loc[1]
    column = loc[2]
    scope = loc[3]

    debug('marking loc at: ' + str(view))
    region = [view.full_line(
                view.text_point(line - 1, column - 1))]
    view.add_regions("lldb-location",
                     region,
                     scope, "bookmark",
                     sublime.HIDDEN)
    show_lldb_panel()


class MarkersListener(sublime_plugin.EventListener):
    def on_load(self, view):
        global lldb_last_location_view
        if lldb_current_location and view.file_name() == lldb_current_location[0]:
            lldb_last_location_view = view
            mark_code_loc(view, lldb_current_location)


def update_breakpoints(window):
    debug_thr()

    if lldb_instance():
        breakpoints = lldb_instance().breakpoints()
    else:
        # Just erase the current bp markers
        breakpoints = []

    seen = []
    for w in sublime.windows():
        for v in w.views():
            debug('marking view: ' + str(v.file_name()) + ' (' + str(v.name()) + ')')
            if v in seen:
                continue
            else:
                seen.append(v)

            v.erase_regions("lldb-breakpoint")
            regions = []
            for bp in breakpoints:
                for bp_loc in bp.line_entries():
                    debug('bp entries: ' + str(bp.line_entries()))
                    if bp_loc and v.file_name() == bp_loc[0] + '/' + bp_loc[1]:
                        debug('marking: ' + str(bp_loc) + ' at: ' + v.file_name() + ' (' + v.name() + ')')
                        debug('regions: ' + str(regions))
                        regions.append(
                            v.full_line(
                              v.text_point(bp_loc[2] - 1, bp_loc[3] - 1)))
                        debug('regions (after): ' + str(regions))

            if len(regions) > 0:
                debug('marking regions:')
                debug(regions)
                v.add_regions("lldb-breakpoint", regions, \
                             "string", "circle",          \
                             sublime.HIDDEN)


# event_monitor mimics the Driver class, in Driver.cpp
def lldb_event_monitor(driver, sublime_broadcaster):
    thread_created(threading.current_thread().name)
    debug_thr()
    debug('started')

    debugger = driver.debugger
    listener = LldbListener('event listener')

    listener.StartListeningForEvents(sublime_broadcaster,
                                     SublimeBroadcaster.eBroadcastBitDidStart |         \
                                     SublimeBroadcaster.eBroadcastBitHasCommandInput |  \
                                     SublimeBroadcaster.eBroadcastBitShouldExit |       \
                                     SublimeBroadcaster.eBroadcastBitDidExit)

    debug('waiting for SublimeBroadcaster')
    event = lldb.SBEvent()
    listener.WaitForEventForBroadcasterWithType(400000,
                                                sublime_broadcaster,
                                                SublimeBroadcaster.eBroadcastBitDidStart,
                                                event)

    start_listening_for_breakpoint_changes(listener, debugger)
    start_listening_for_process_events(listener, debugger)

    interpreter_broadcaster = debugger.GetCommandInterpreter().GetBroadcaster()
    listener.StartListeningForEvents(interpreter_broadcaster,
                                     lldb.SBCommandInterpreter.eBroadcastBitQuitCommandReceived |    \
                                     lldb.SBCommandInterpreter.eBroadcastBitAsynchronousOutputData | \
                                     lldb.SBCommandInterpreter.eBroadcastBitAsynchronousErrorData)

    if listener.valid:
        done = False
        while not done:
            debug('listening at: ' + str(listener.SBListener))
            ev = lldb.SBEvent()
            listener.WaitForEvent(BIG_TIMEOUT, ev)
            if ev.IsValid():
                debug('Got event: ' + lldbutil.get_description(ev))
                if ev.GetBroadcaster().IsValid():
                    type = ev.GetType()
                    string = lldb.SBEvent.GetCStringFromEvent(ev)
                    if lldb.SBProcess.EventIsProcessEvent(ev):
                        handle_process_event(ev)
                    elif lldb.SBBreakpoint.EventIsBreakpointEvent(ev):
                        handle_breakpoint_event(ev)
                    elif ev.BroadcasterMatchesRef(interpreter_broadcaster):
                        if type & lldb.SBCommandInterpreter.eBroadcastBitQuitCommandReceived:
                            done = True
                            debug('quit received')
                        elif type & lldb.SBCommandInterpreter.eBroadcastBitAsynchronousErrorData:
                            debug('got async error data')
                            lldb_view_send(stderr_msg(string))
                        elif type & lldb.SBCommandInterpreter.eBroadcastBitAsynchronousOutputData:
                            debug('got async output data')
                            lldb_view_send(stdout_msg(string))
                    elif ev.BroadcasterMatchesRef(sublime_broadcaster):
                        if type & SublimeBroadcaster.eBroadcastBitHasCommandInput:
                            if string is None:
                                debug('ev.string is None: ' + 'SublimeBroadcaster.eBroadcastBitHasCommandInput')
                                string = ''

                            result, r = interpret_command(debugger, string, True)
                            err_str = stderr_msg(result.GetError())
                            out_str = stdout_msg(result.GetOutput())

                            lldb_view_send(out_str)

                            if len(err_str) != 0:
                                lldb_view_send(err_str)
                            continue

                        elif type & SublimeBroadcaster.eBroadcastBitShouldExit \
                            or type & SublimeBroadcaster.eBroadcastBitDidExit:
                            done = True
                            continue
    debug('exiting')
    set_lldb_instance(None)
    kill_monitors()


def handle_process_event(ev):
    debug('process event: ' + str(ev))
    type = ev.GetType()
    if type & lldb.SBProcess.eBroadcastBitSTDOUT:
        get_process_stdout()
    elif type & lldb.SBProcess.eBroadcastBitSTDOUT:
        get_process_stderr()
    elif type & lldb.SBProcess.eBroadcastBitStateChanged:
        get_process_stdout()
        get_process_stderr()

        # only after printing the std* can we print our prompts
        state = lldb.SBProcess.GetStateFromEvent(ev)
        if state == lldb.eStateInvalid:
            debug('invalid process state')
            return

        process = lldb.SBProcess.GetProcessFromEvent(ev)
        assert process.IsValid()

        if state == lldb.eStateInvalid       \
            or state == lldb.eStateUnloaded  \
            or state == lldb.eStateConnected \
            or state == lldb.eStateAttaching \
            or state == lldb.eStateLaunching \
            or state == lldb.eStateStepping  \
            or state == lldb.eStateDetached:
            lldb_view_send("Process %llu %s\n", process.GetProcessID(),
                lldb_instance().StateAsCString(state))

        elif state == lldb.eStateRunning:
            None  # Don't be too chatty
        elif state == lldb.eStateExited:
            r = interpret_command(lldb_instance().debugger, 'process status')
            lldb_view_send(stdout_msg(r[0].GetOutput()))
            lldb_view_send(stderr_msg(r[0].GetError()))
            marker_update('pc', (lldb_instance().line_entry,))
        elif state == lldb.eStateStopped     \
            or state == lldb.eStateCrashed   \
            or state == lldb.eStateSuspended:
            if lldb.SBProcess.GetRestartedFromEvent(ev):
                lldb_view_send('Process %llu stopped and was programmatically restarted.' %
                    process.GetProcessID())
                marker_update('pc', (lldb_instance().line_entry,))
            else:
                debug('updating selected thread')
                update_selected_thread(lldb_instance().debugger)
                debug('updated selected thread')
                debugger = lldb_instance().debugger
                entry = lldb_instance().line_entry
                if entry:
                    # We don't need to run 'process status' like Driver.cpp
                    # Since we open the file and show the source line.
                    r = interpret_command(debugger, 'thread list')
                    lldb_view_send(stdout_msg(r[0].GetOutput()))
                    lldb_view_send(stderr_msg(r[0].GetError()))
                    r = interpret_command(debugger, 'frame info')
                    lldb_view_send(stdout_msg(r[0].GetOutput()))
                    lldb_view_send(stderr_msg(r[0].GetError()))
                else:
                    # Give us some assembly to check the crash/stop
                    r = interpret_command(debugger, 'process status')
                    lldb_view_send(stdout_msg(r[0].GetOutput()))
                    lldb_view_send(stderr_msg(r[0].GetError()))
                    entry = lldb_instance().first_line_entry_with_source

                scope = 'bookmark'
                if state == lldb.eStateCrashed:
                    scope = 'invalid'
                debug('updating marker')
                marker_update('pc', (entry, scope))


def get_process_stdout():
    string = stdout_msg(lldb_instance().debugger.GetSelectedTarget(). \
        GetProcess().GetSTDOUT(1024))
    while len(string) > 0:
        lldb_view_send(string)
        string = stdout_msg(lldb_instance().debugger.GetSelectedTarget(). \
            GetProcess().GetSTDOUT(1024))


def get_process_stderr():
    string = stderr_msg(lldb_instance().debugger.GetSelectedTarget(). \
        GetProcess().GetSTDOUT(1024))
    while len(string) > 0:
        lldb_view_send(string)
        string = stderr_msg(lldb_instance().debugger.GetSelectedTarget(). \
            GetProcess().GetSTDOUT(1024))


def update_selected_thread(debugger):
    proc = debugger.GetSelectedTarget().GetProcess()
    if proc.IsValid():
        curr_thread = proc.GetSelectedThread()
        current_thread_stop_reason = curr_thread.GetStopReason()

        debug('thread stop reason: ' + str(current_thread_stop_reason))
        other_thread = lldb.SBThread()
        plan_thread = lldb.SBThread()
        if not curr_thread.IsValid() \
            or current_thread_stop_reason == lldb.eStopReasonInvalid \
            or current_thread_stop_reason == lldb.eStopReasonNone:
            for t in proc:
                t_stop_reason = t.GetStopReason()
                if t_stop_reason == lldb.eStopReasonInvalid \
                    or t_stop_reason == lldb.eStopReasonNone:
                    pass
                elif t_stop_reason == lldb.eStopReasonTrace \
                    or t_stop_reason == lldb.eStopReasonBreakpoint \
                    or t_stop_reason == lldb.eStopReasonWatchpoint \
                    or t_stop_reason == lldb.eStopReasonSignal \
                    or t_stop_reason == lldb.eStopReasonException:
                    if not other_thread:
                        other_thread = t
                    elif t_stop_reason == lldb.eStopReasonPlanComplete:
                        if not plan_thread:
                            plan_thread = t

            if plan_thread:
                proc.SetSelectedThread(plan_thread)
            elif other_thread:
                proc.SetSelectedThread(other_thread)
            else:
                if curr_thread:
                    thread = curr_thread
                else:
                    thread = proc.GetThreadAtIndex(0)

                proc.SetSelectedThread(thread)


def handle_breakpoint_event(ev):
    type = lldb.SBBreakpoint.GetBreakpointEventTypeFromEvent(ev)
    debug('breakpoint event: ' + str(type))

    if type & lldb.eBreakpointEventTypeAdded                \
        or type & lldb.eBreakpointEventTypeRemoved          \
        or type & lldb.eBreakpointEventTypeEnabled          \
        or type & lldb.eBreakpointEventTypeDisabled         \
        or type & lldb.eBreakpointEventTypeCommandChanged   \
        or type & lldb.eBreakpointEventTypeConditionChanged \
        or type & lldb.eBreakpointEventTypeIgnoreChanged    \
        or type & lldb.eBreakpointEventTypeLocationsResolved:
        None
    elif type & lldb.eBreakpointEventTypeLocationsAdded:
        new_locs = lldb.SBBreakpoint.GetNumBreakpointLocationsFromEvent(ev)
        if new_locs > 0:
            bp = lldb.SBBreakpoint.GetBreakpointFromEvent(ev)
            lldb_view_send("%d locations added to breakpoint %d\n" %
                (new_locs, bp.GetID()))
    elif type & lldb.eBreakpointEventTypeLocationsRemoved:
        None
