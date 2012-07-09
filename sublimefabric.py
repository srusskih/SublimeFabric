import threading
import subprocess
import functools
import os
import sublime
import sublime_plugin


def main_thread(callback, *args, **kwargs):
    # sublime.set_timeout gets used to send things onto the main thread
    # most sublime.[something] calls need to be on the main thread
    sublime.set_timeout(functools.partial(callback, *args, **kwargs), 0)


def _make_text_safeish(text, fallback_encoding):
    # The unicode decode here is because sublime converts to unicode inside
    # insert in such a way that unknown characters will cause errors, which is
    # distinctly non-ideal... and there's no way to tell what's coming out of
    # git in output. So...
    try:
        unitext = text.decode('utf-8')
    except UnicodeDecodeError:
        unitext = text.decode(fallback_encoding)
    return unitext


class CommandThread(threading.Thread):
    def __init__(self, command, on_done, working_dir="", fallback_encoding="",
                                                                    **kwargs):
        threading.Thread.__init__(self)
        self.command = command
        self.on_done = on_done
        self.working_dir = working_dir

        self.stdin = kwargs.get("stdin", None)
        self.stdout = kwargs.get("stdout", subprocess.PIPE)
        self.stderr = subprocess.STDOUT

        self.fallback_encoding = fallback_encoding
        self.kwargs = kwargs

    def run(self):
        try:
            # Per http://bugs.python.org/issue8557 shell=True is required to
            # get $PATH on Windows. Yay portable code.
            shell = os.name == 'nt'
            if self.working_dir != "":
                os.chdir(self.working_dir)

            proc = subprocess.Popen(self.command,
                stdout=self.stdout,
                stderr=self.stderr,
                stdin=self.stdin,
                shell=shell,
                universal_newlines=True
            )

            output = proc.communicate(self.stdin)[0]
            if not output:
                output = ''
            # if sublime's python gets bumped to 2.7 we can just do:
            # output = subprocess.check_output(self.command)
            main_thread(self.on_done,
                _make_text_safeish(output, self.fallback_encoding),
                **self.kwargs
            )

        except subprocess.CalledProcessError, e:
            main_thread(self.on_done, e.returncode)

        except OSError, e:
            if e.errno == 2:
                main_thread(sublime.error_message, "Fabric not found")
            else:
                raise e

        except Exception, e:
            raise e


class BaseFabCommand:
    def get_window(self):
        return self.view.window() or sublime.active_window()

    def active_view(self):
        return sublime.active_window().active_view()

    def get_working_dir(self):
        return os.path.dirname(self.view.file_name())

    def quick_panel(self, *args, **kwargs):
        self.get_window().show_quick_panel(*args, **kwargs)

    def panel(self, output, **kwargs):
        self.panel_name = 'sublimefabric'

        if not hasattr(self, 'output_view'):
            self.output_view = self.get_window().\
                                        get_output_panel(self.panel_name)

        self.output_view.set_read_only(False)
        self._output_to_view(self.output_view, output, clear=True, **kwargs)
        self.output_view.set_read_only(True)

        self.get_window().run_command("show_panel",
                                      {"panel": 'output.' + self.panel_name})

    def _output_to_view(self, output_file, output, clear=False):
        edit = output_file.begin_edit()
        if clear:
            region = sublime.Region(0, self.output_view.size())
            output_file.erase(edit, region)
        output_file.insert(edit, 0, output)
        output_file.end_edit(edit)

    def run_command(self, command, callback, show_status=True, **kwargs):
        assert isinstance(command, list), \
                "Command should looks like: ['fab', 'deploy']"

        # remove empty args from the command
        command = [i for i in command if i]

        if 'working_dir' not in kwargs:
            kwargs['working_dir'] = self.get_working_dir()

        if 'fallback_encoding' not in kwargs and\
                 self.active_view() and\
                 self.active_view().settings().get('fallback_encoding'):

            kwargs['fallback_encoding'] = self.active_view().settings().\
                get('fallback_encoding').rpartition('(')[2].rpartition(')')[0]

        thread = CommandThread(command, callback, **kwargs)
        thread.start()

        # show status message in the status line
        if show_status:
            message = kwargs.get('status_message', False) or ' '.join(command)
            sublime.status_message(message)


class FabCustomCommand(BaseFabCommand, sublime_plugin.TextCommand):
    def run(self, edit=None):
        # show input panel, on enter do `self.on_input`
        self.get_window().show_input_panel("Fabric command: fab ", "",
            self.on_input, None, None)

    def on_input(self, command):
        command = str(command)  # avoiding unicode

        # if command empty
        if command.strip() == "":
            self.panel("No command was entered!")
            return

        command = ['fab'] + command.split(' ')
        self.run_command(command, self.on_done)

    def on_done(self, result):
        self.panel(result)


class FabQuickCommand(BaseFabCommand, sublime_plugin.TextCommand):
    def run(self, edit=None):
        self.get_fabric_commands()

    def get_fabric_commands(self):
        """ get available fabric commands from the fabfile """
        self.fab_commands = []
        self.run_command(['fab', '-l'], self._parse_commands)

    def _parse_commands(self, output):
        """ parce returned result with commands """
        output = output.split('\n')[2:]
        for i, command in enumerate(output):
            if not command.strip():
                # we don't need empty rows
                continue
            # split command descrpitions in to words
            command = [c for c in command.split(' ') if c.strip()]
            # first word is our command, the next words is descrption
            command_name, description = command[0], ' '.join(command[1:])
            # add command and description to list
            self.fab_commands.append([command_name, description.title()])

        # show quick panel with commands
        self.quick_panel(self.fab_commands, self.on_select)

    def on_select(self, command_id):
        """ if user selected one of commands from quick pannel """
        if command_id >= 0:
            command = ['fab', self.fab_commands[command_id][0]]
            self.run_command(command, self.panel)
